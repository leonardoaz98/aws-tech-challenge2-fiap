# Camada Bronze — Dados Brutos

Ingestao das tabelas da Base dos Dados (`br_inep_avaliacao_alfabetizacao`) em Parquet no S3, **sem transformacoes**, preservando o historico completo.

- **Fonte:** Base dos Dados (microdados educacionais publicos INEP/IBGE)
- **Destino:** `s3://tc2-fiap-datalake/bronze/<tabela>/`
- **Formato:** Parquet + Snappy, particionado por `ano` quando aplicavel
- **Rastreabilidade:** cada registro recebe `_ingestao_timestamp` e `_fonte`
- **Streaming:** eventos em tempo quase real chegam em `bronze/streaming/` (ver `streaming_producer.py`)

Script: `ingestion/batch/ingest_bronze.py`
