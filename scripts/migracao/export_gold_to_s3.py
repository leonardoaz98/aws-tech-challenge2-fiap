"""
Exporta a camada Gold do BigQuery (GCP) para o S3 (AWS) em Parquet.

Script historico da migracao de plataforma: le cada tabela Gold via
pandas_gbq e grava em `s3://<bucket>/gold/` com awswrangler, como dataset
que o Athena/Glue le nativamente.

Nao faz parte do pipeline corrente - a Gold hoje e construida direto na
AWS por `layers/gold/build_gold.py`. Fica versionado como registro do
caminho de migracao e como referencia caso o export precise ser refeito.

Requer as variaveis do lado GCP no .env (GCP_PROJECT_ID e BQ_DATASET_GOLD),
que nao sao usadas pelo restante do projeto. Por isso sao lidas aqui em vez
de virem de config.settings, que descreve apenas a configuracao AWS.

Uso:
    python -m scripts.migracao.export_gold_to_s3
"""
import os

import awswrangler as wr
import pandas_gbq
from dotenv import load_dotenv

from config.settings import S3_GOLD

load_dotenv()

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
BQ_DATASET_GOLD = os.getenv("BQ_DATASET_GOLD", "gold")

TABELAS = ["dim_uf", "dim_municipio", "dim_tempo", "dim_nivel", "fato_alfabetizacao"]


def validar_origem() -> None:
    """Falha cedo se a configuracao do lado GCP estiver ausente."""
    if not GCP_PROJECT_ID:
        raise EnvironmentError(
            "GCP_PROJECT_ID nao definido. Este script le do BigQuery e exige "
            "a configuracao do projeto de origem no .env."
        )

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
    validar_origem()
    print("=== Export Gold BigQuery -> S3 ===", flush=True)
    for t in TABELAS:
        exportar(t)
    print("=== Concluido ===", flush=True)

if __name__ == "__main__":
    main()
