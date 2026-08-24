"""Exporta a camada Gold do BigQuery (GCP) para o S3 (AWS) em Parquet.

Documenta a migracao batch: le cada tabela Gold via pandas_gbq e grava em
s3://tc2-fiap-datalake/gold/ usando awswrangler, como dataset que o
Athena/Glue le nativamente.
"""
import pandas_gbq
import awswrangler as wr
from config.settings import GCP_PROJECT_ID, BQ_DATASET_GOLD

S3_GOLD = "s3://tc2-fiap-datalake/gold"
TABELAS = ["dim_uf", "dim_municipio", "dim_tempo", "dim_nivel", "fato_alfabetizacao"]

def exportar(tabela):
    print(f"[{tabela}] lendo do BigQuery...", flush=True)
    df = pandas_gbq.read_gbq(
        f"SELECT * FROM {BQ_DATASET_GOLD}.{tabela}",
        project_id=GCP_PROJECT_ID, progress_bar_type=None,
    )
    destino = f"{S3_GOLD}/{tabela}/"
    print(f"[{tabela}] {len(df)} linhas -> {destino}", flush=True)
    wr.s3.to_parquet(df=df, path=destino, dataset=True,
                     mode="overwrite", compression="snappy")
    print(f"[{tabela}] OK", flush=True)

def main():
    print("=== Export Gold BigQuery -> S3 ===", flush=True)
    for t in TABELAS:
        exportar(t)
    print("=== Concluido ===", flush=True)

if __name__ == "__main__":
    main()
