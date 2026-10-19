"""Importação agendada de atrasos/cancelamentos informados pela Aviationstack.

Usa HTTPS, uma página por consulta, cota persistida e reserva no PostgreSQL para
não repetir chamadas ao reiniciar ou iniciar mais de um worker. A chave nunca
é enviada ao navegador nem incluída em mensagens de erro.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import math
import os
from pathlib import Path
import re
from threading import Event, Thread

import requests
from flask import current_app
from db import transacao

class ErroFornecedor(RuntimeError):
    """Mensagem controlada, sem URL, credencial ou corpo bruto do fornecedor."""


FONTE = 'aviationstack'
URL = 'https://api.aviationstack.com/v1/flights'
# urllib3 em DEBUG registra a query string, que contém a chave exigida pela API.
logging.getLogger('urllib3').setLevel(logging.WARNING)


@dataclass(frozen=True)
class ConfigImportacao:
    chave: str = field(default='', repr=False)
    aeroporto: str = 'GRU'
    intervalo: int = 43200
    limite_diario: int = 2
    atraso_minimo: int = 15

    @classmethod
    def ambiente(cls):
        aeroporto = os.getenv('AVIATIONSTACK_AIRPORT', 'GRU').strip().upper()
        if not re.fullmatch(r'[A-Z]{3}', aeroporto):
            raise ValueError('AVIATIONSTACK_AIRPORT deve ser um código IATA de três letras')
        return cls(
            chave=os.getenv('AVIATIONSTACK_API_KEY', '').strip(), aeroporto=aeroporto,
            intervalo=max(300, int(os.getenv('AVIATIONSTACK_INTERVAL_SECONDS', '43200'))),
            limite_diario=max(1, int(os.getenv('AVIATIONSTACK_DAILY_REQUEST_LIMIT', '2'))),
            atraso_minimo=max(1, int(os.getenv('AVIATIONSTACK_MIN_DELAY_MINUTES', '15'))),
        )


def preparar_banco():
    with transacao() as conn:
        if not current_app.config.get('TESTING'):
            conn.execute('SELECT pg_advisory_xact_lock(5739101)')
        sql = (Path(__file__).parent / 'migrations' / 'aviationstack.sql').read_text()
        if current_app.config.get('TESTING'):
            conn._conexao.executescript(sql)
        else:
            conn.execute(sql)


def _iso(agora):
    return agora.astimezone(timezone.utc).isoformat()


def _reservar(cfg, agora):
    """Conta a chamada antes da rede, inclusive se houver erro ou queda do processo."""
    with transacao() as conn:
        if not current_app.config.get('TESTING'):
            if not conn.execute('SELECT pg_try_advisory_xact_lock(5739102) AS ok').fetchone()['ok']:
                return False
        linha = conn.execute('SELECT * FROM importacao_voos_estado WHERE fonte = %s', (FONTE,)).fetchone()
        if linha and datetime.fromisoformat(linha['proxima_consulta']) > agora:
            return False
        dia = agora.date().isoformat()
        chamadas = linha['chamadas_dia'] if linha and linha['dia_cota'] == dia else 0
        if chamadas >= cfg.limite_diario:
            proxima = (agora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            conn.execute('UPDATE importacao_voos_estado SET proxima_consulta = %s, ultimo_erro = %s WHERE fonte = %s',
                         (_iso(proxima), 'Limite diário configurado atingido.', FONTE))
            return False
        conn.execute('''INSERT INTO importacao_voos_estado
            (fonte, proxima_consulta, ultima_tentativa, dia_cota, chamadas_dia)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (fonte) DO UPDATE SET
            proxima_consulta = excluded.proxima_consulta, ultima_tentativa = excluded.ultima_tentativa,
            dia_cota = excluded.dia_cota, chamadas_dia = excluded.chamadas_dia''',
            (FONTE, _iso(agora + timedelta(seconds=cfg.intervalo)), _iso(agora), dia, chamadas + 1))
    return True


def consultar(cfg):
    try:
        resposta = requests.get(URL, params={
            'access_key': cfg.chave, 'dep_iata': cfg.aeroporto, 'limit': 100, 'offset': 0,
        }, timeout=(5, 20))
        if resposta.status_code != 200:
            raise ErroFornecedor('Fornecedor respondeu HTTP ' + str(resposta.status_code))
        dados = resposta.json()
    except requests.RequestException:
        raise ErroFornecedor('Não foi possível conectar à Aviationstack.') from None
    except ValueError:
        raise ErroFornecedor('Aviationstack retornou JSON inválido.') from None
    if not isinstance(dados, dict):
        raise ErroFornecedor('Resposta inválida da Aviationstack.')
    if dados.get('error'):
        tipo = dados['error'].get('type') if isinstance(dados['error'], dict) else None
        mensagens = {
            'invalid_access_key': 'Chave Aviationstack inválida.',
            'usage_limit_reached': 'Cota do plano Aviationstack atingida.',
            'function_access_restricted': 'Operação indisponível no plano Aviationstack.',
            'rate_limit_reached': 'Limite de frequência da Aviationstack atingido.',
        }
        raise ErroFornecedor(mensagens.get(tipo, 'Aviationstack recusou a consulta. Verifique seu plano.'))
    if not isinstance(dados.get('data'), list):
        raise ErroFornecedor('Aviationstack não retornou uma lista de voos válida.')
    pag = dados.get('pagination') or {}
    try:
        parcial = int(pag.get('total', len(dados['data']))) > len(dados['data'])
    except (ValueError, TypeError):
        parcial = True
    return dados['data'], parcial


def normalizar(voo, cfg):
    if not isinstance(voo, dict):
        return None
    partida, chegada, ident = (voo.get(k) or {} for k in ('departure', 'arrival', 'flight'))
    if not all(isinstance(v, dict) for v in (partida, chegada, ident)):
        return None
    codigo = ident.get('iata') or ident.get('icao')
    data, previsto = voo.get('flight_date'), partida.get('scheduled')
    if not all(isinstance(v, str) and v for v in (codigo, data, previsto)):
        return None
    # Rejeita dados incompletos e voos fora do aeroporto configurado.
    if partida.get('iata') != cfg.aeroporto:
        return None
    try:
        datetime.strptime(data, '%Y-%m-%d')
        datetime.fromisoformat(previsto.replace('Z', '+00:00'))
    except ValueError:
        return None
    cancelado = voo.get('flight_status') == 'cancelled'
    atraso = partida.get('delay')
    atraso = float(atraso) if isinstance(atraso, (int, float)) and not isinstance(atraso, bool) else 0
    if not math.isfinite(atraso):
        return None
    if not cancelado and not (atraso >= cfg.atraso_minimo):
        return None
    chave = hashlib.sha256(f'{FONTE}|{codigo}|{data}|{cfg.aeroporto}'.encode()).hexdigest()
    descricao = ('Cancelamento informado' if cancelado else f'Atraso de partida de {atraso:g} minuto(s) informado')
    descricao += f' pela Aviationstack para o voo {codigo}, data {data}. Informação do fornecedor; causa não informada.'
    return {
        'chave': chave, 'voo': codigo, 'descricao': descricao,
        'risco': 'alto' if cancelado or atraso >= 60 else 'medio',
        'rota': ' → '.join(v for v in [partida.get('iata'), chegada.get('iata')] if isinstance(v, str) and v),
        'horario': previsto, 'base': cfg.aeroporto,
    }


def _persistir(eventos, agora, parcial):
    with transacao() as conn:
        for evento in eventos:
            vinculo = conn.execute('SELECT disrupcao_id FROM importacao_voos_eventos WHERE chave = %s', (evento['chave'],)).fetchone()
            valores = tuple(evento[k] for k in ('voo', 'descricao', 'risco', 'rota', 'horario', 'base'))
            if vinculo:
                conn.execute('''UPDATE disrupcoes SET voo=%s, descricao=%s, risco=%s, rota=%s, horario=%s, base=%s WHERE id=%s''', valores + (vinculo['disrupcao_id'],))
                conn.execute('UPDATE importacao_voos_eventos SET observado_em = %s WHERE chave = %s', (_iso(agora), evento['chave']))
            else:
                linha = conn.execute('''INSERT INTO disrupcoes (voo, descricao, risco, rota, horario, base)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING id''', valores).fetchone()
                conn.execute('INSERT INTO importacao_voos_eventos (chave, disrupcao_id, observado_em) VALUES (%s,%s,%s)',
                             (evento['chave'], linha['id'], _iso(agora)))
        conn.execute('''UPDATE importacao_voos_estado SET ultimo_sucesso=%s, ultimo_erro=NULL, parcial=%s WHERE fonte=%s''',
                     (_iso(agora), parcial, FONTE))


def executar_ciclo(cfg=None, agora=None):
    cfg = cfg or ConfigImportacao.ambiente()
    agora = agora or datetime.now(timezone.utc)
    if not cfg.chave:
        return {'executado': False, 'motivo': 'Configure AVIATIONSTACK_API_KEY no servidor.'}
    if not _reservar(cfg, agora):
        return {'executado': False, 'motivo': 'Aguardando próxima consulta ou cota diária.'}
    try:
        voos, parcial = consultar(cfg)
        eventos = [e for voo in voos if (e := normalizar(voo, cfg))]
        _persistir(eventos, agora, parcial)
        return {'executado': True, 'ocorrencias': len(eventos), 'parcial': parcial}
    except Exception as exc:
        # Mensagens de transporte podem incluir a URL com a chave: nunca propagá-las.
        erro = str(exc) if isinstance(exc, ErroFornecedor) else 'Falha na importação. Verifique conexão, chave e cota na Aviationstack.'
        with transacao() as conn:
            conn.execute('UPDATE importacao_voos_estado SET ultimo_erro=%s WHERE fonte=%s', (erro, FONTE))
        current_app.logger.warning(erro)
        return {'executado': True, 'erro': erro}


def status_importacao():
    cfg = ConfigImportacao.ambiente()
    with transacao() as conn:
        linha = conn.execute('SELECT * FROM importacao_voos_estado WHERE fonte=%s', (FONTE,)).fetchone()
    return {
        'fonte': FONTE, 'configurada': bool(cfg.chave), 'aeroporto': cfg.aeroporto,
        'agendador_ativo': bool(current_app.extensions.get('importador_voos_ativo')),
        'intervalo_segundos': cfg.intervalo, 'limite_diario': cfg.limite_diario,
        **(dict(linha) if linha else {}),
    }


def iniciar(app):
    if app.config.get('TESTING'):
        return None
    with app.app_context():
        preparar_banco()
    parar = Event()
    def loop():
        while not parar.is_set():
            with app.app_context():
                try:
                    executar_ciclo()
                except Exception:
                    app.logger.warning('Importador indisponível. Verifique configuração e banco.')
            parar.wait(60)
    thread = Thread(target=loop, daemon=True, name='importacao-aviationstack')
    thread.start()
    app.extensions["importador_voos_ativo"] = True
    return parar
