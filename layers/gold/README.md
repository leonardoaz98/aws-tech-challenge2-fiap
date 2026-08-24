# Camada Gold — Modelo Dimensional (Kimball)

Star schema pronto para dashboards, analise estatistica e ML. Materializado em `s3://tc2-fiap-datalake/gold/` e consultado via Athena (database `tc2_gold`).

## Tabelas

| Tabela | Grao / Chave | Linhas |
|---|---|---|
| dim_uf | sigla_uf | 27 |
| dim_municipio | id_municipio | 5.571 |
| dim_tempo | ano | 8 |
| dim_nivel | nivel_alfabetizacao | 6 |
| fato_alfabetizacao | id_municipio + ano | 43.008 |

## Views analiticas (consumidas pelo dashboard)

- `vw_uf_ano` — indicadores por UF e ano (taxa, meta, gap, % atingiu)
- `vw_regiao_ano` — agregacao por regiao e ano
- `vw_municipio` — detalhe municipal com gap e status de meta

Scripts: `layers/gold/build_views.py` (views no Athena). A materializacao das tabelas a partir da Silver segue a logica dimensional documentada; a carga inicial no S3 e feita por `export_gold_to_s3.py`.
