# Contorno do Brasil

`brasil.json` contém somente a geometria MultiPolygon do Brasil (ISO 076),
extraída de `countries-10m.json` do pacote `world-atlas@2.0.2`.
Fonte: Natural Earth 4.1.0, Admin 0 Countries, escala 1:10.000.000.
Os arcos TopoJSON foram expandidos com sua transformação original em coordenadas
longitude/latitude, arredondadas a cinco casas. Foram preservados os 43 polígonos,
as ilhas e os anéis internos, com 11.087 pontos.

Referências:
- https://github.com/topojson/world-atlas/tree/v2.0.2
- https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/

Natural Earth disponibiliza os dados em domínio público. A redistribuição pelo
world-atlas usa licença ISC; a cópia está em `LICENSE-world-atlas` e também nos
metadados dos SVGs gerados.

Na raiz do repositório, com as dependências do backend instaladas:

```sh
python backend/dados/geografia/gerar_mapa.py
```

O script usa exatamente `_projetar` do backend para gerar `docs/assets/brasil.svg`
e `backend/static/assets/brasil.svg`. Qualquer alteração da projeção exige gerar
novamente ambos os arquivos. O navegador os carrega como imagens locais cacheáveis;
o contorno completo não é enviado a cada consulta de cinco segundos da operação.

Os testes verificam Belém, capitais costeiras, Florianópolis e Fernando de Noronha
contra o SVG publicado, além do enquadramento de todos os aeroportos cadastrados.
