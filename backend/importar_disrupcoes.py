"""Executa uma consulta respeitando agendamento e cota, para cron ou diagnóstico."""
import json
from app import create_app
from importador_voos import preparar_banco, executar_ciclo

if __name__ == '__main__':
    with create_app().app_context():
        preparar_banco()
        resultado = executar_ciclo()
        print(json.dumps(resultado, ensure_ascii=False))
        if resultado.get('erro'):
            raise SystemExit(1)
