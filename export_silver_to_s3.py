"""
Materializa a camada Silver no S3 (approach pragmatico).

Traz as 5 tabelas Silver ja processadas para o S3 em Parquet, populando
a camada s3://tc2-fiap-datalake/silver/. Alternativa rapida a reprocessar
todo o pipeline Bronze->Silver na AWS; a logica de construcao esta
documentada em layers/silver/build_silver.py.
"""
import pandas_gbq
import awswrangler as wr
import os

PROJETO = os.getenv("BD_BILLING_PROJECT") or os.getenv("GCP_PROJECT_ID")
S3_SILVER = "s3://tc2-fiap-datalake/silver"
TABELAS = ["municipio_resultado", "uf_resultado", "meta_municipio", "meta_uf", "meta_brasil"]

def exportar(tabela):
    print(f"[{tabela}] lendo Silver...", flush=True)
    df = pandas_gbq.read_gbq(f"SELECT * FROM silver.{tabela}",
                             project_id=PROJETO, progress_bar_type=None)
    destino = f"{S3_SILVER}/{tabela}/"
    print(f"[{tabela}] {len(df)} linhas -> {destino}", flush=True)
    wr.s3.to_parquet(df=df, path=destino, dataset=True,
                     mode="overwrite", compression="snappy")
    print(f"[{tabela}] OK", flush=True)

def main():
    print("=== Materializando Silver no S3 ===", flush=True)
    for t in TABELAS:
        exportar(t)
    print("=== Concluido ===", flush=True)

if __name__ == "__main__":
    main()
