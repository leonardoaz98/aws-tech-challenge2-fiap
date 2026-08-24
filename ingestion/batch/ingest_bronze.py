"""
Ingestao Batch - Camada Bronze (AWS)

Baixa as tabelas do dataset br_inep_avaliacao_alfabetizacao da Base dos
Dados (fonte publica de microdados educacionais) e grava em Parquet no
S3 (s3://BUCKET/bronze/), sem transformacoes.
"""
import awswrangler as wr
import basedosdados as bd
import pandas as pd
from datetime import datetime, timezone

from config.logger import get_logger
from config.settings import (
    BD_DATASET,
    BD_BILLING_PROJECT,
    S3_BRONZE,
    TABELAS_BRONZE,
    validar_config,
)

log = get_logger("bronze")


def extrair(tabela: str) -> pd.DataFrame:
    """Le a tabela completa da Base dos Dados (fonte publica)."""
    query = f"SELECT * FROM `basedosdados.{BD_DATASET}.{tabela}`"
    log.info(f"[{tabela}] extraindo...")
    df = bd.read_sql(query=query, billing_project_id=BD_BILLING_PROJECT)
    log.info(f"[{tabela}] {df.shape[0]} linhas x {df.shape[1]} colunas")
    return df


def gravar_s3(df: pd.DataFrame, tabela: str, particoes: list) -> None:
    """
    Grava em Parquet no S3, particionado quando aplicavel.
    Adiciona metadados de rastreabilidade exigidos pela governanca.
    """
    df = df.copy()
    df["_ingestao_timestamp"] = datetime.now(timezone.utc).isoformat()
    df["_fonte"] = f"basedosdados.{BD_DATASET}.{tabela}"

    destino = f"{S3_BRONZE}/{tabela}/"
    particoes_validas = [c for c in particoes if c in df.columns]

    wr.s3.to_parquet(
        df=df,
        path=destino,
        dataset=True,
        mode="overwrite",
        partition_cols=particoes_validas if particoes_validas else None,
        compression="snappy",
    )
    if particoes_validas:
        log.info(f"[{tabela}] gravado no S3 particionado por {particoes_validas}")
    else:
        log.info(f"[{tabela}] gravado no S3 sem particao")


def main() -> None:
    validar_config()
    log.info(f"Iniciando ingestao Bronze -> {S3_BRONZE}")
    sucesso, falha = [], []

    for tabela, particoes in TABELAS_BRONZE.items():
        try:
            df = extrair(tabela)
            gravar_s3(df, tabela, particoes)
            sucesso.append(tabela)
        except Exception as erro:
            log.error(f"[{tabela}] FALHOU: {erro}")
            falha.append(tabela)

    log.info(f"Concluido | sucesso={len(sucesso)} | falha={len(falha)}")
    if falha:
        log.warning(f"Tabelas com falha: {falha}")


if __name__ == "__main__":
    main()
