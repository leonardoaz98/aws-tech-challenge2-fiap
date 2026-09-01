"""
Promocao da zona de streaming: Bronze -> Silver.

Le os Parquet gravados pelo producer no S3, deduplica por `id_evento`,
aplica a mesma padronizacao do caminho batch e materializa a tabela
`evento_indicador` na Silver.

A deduplicacao e o que garante semantica exactly-once na camada analitica:
o producer pode reescrever um lote apos falha, e o `id_evento` resolve.

A carga e idempotente: apenas eventos ainda nao presentes na Silver sao
gravados, entao a promocao pode rodar em agenda sem estragar a tabela.
"""

import awswrangler as wr
import pandas as pd

from config.logger import get_logger
from config.settings import (
    ATHENA_DATABASE,
    ATHENA_S3_OUTPUT,
    S3_BRONZE_STREAMING,
    S3_SILVER,
    validar_config,
)
from quality.validations import relatorio_consolidado, validar_tabela

log = get_logger("streaming")

TABELA = "evento_indicador"
DESTINO = f"{S3_SILVER}/{TABELA}/"


def ler_bronze_streaming() -> pd.DataFrame:
    """Concatena todos os micro-batches da zona de streaming."""
    try:
        df = wr.s3.read_parquet(path=S3_BRONZE_STREAMING, dataset=False)
    except Exception as erro:
        log.warning(f"[streaming] nada lido da Bronze: {erro}")
        return pd.DataFrame()

    if df.empty:
        log.warning("[streaming] zona de streaming vazia")
        return df

    log.info(f"[streaming] {len(df)} evento(s) lidos da Bronze")
    return df


def padronizar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica as mesmas regras de tipagem do caminho batch.

    O codigo IBGE de municipio tem 7 digitos e alguns comecam com zero.
    Tratado como inteiro, o join falha silenciosamente para os municipios
    afetados - por isso e sempre string com zfill.
    """
    df = df.copy()
    df["id_municipio"] = df["id_municipio"].astype(str).str.strip().str.zfill(7)
    df["sigla_uf"] = df["sigla_uf"].astype(str).str.strip().str.upper()
    df["ano_referencia"] = pd.to_numeric(
        df["ano_referencia"], errors="coerce"
    ).astype("Int64")
    df["timestamp_evento"] = pd.to_datetime(df["timestamp_evento"], utc=True)
    return df.drop(columns=["_fonte"], errors="ignore")


def deduplicar(df: pd.DataFrame) -> pd.DataFrame:
    """Mantem a ultima ocorrencia de cada id_evento."""
    antes = len(df)
    df = (
        df.sort_values("_ingestao_timestamp")
        .drop_duplicates(subset=["id_evento"], keep="last")
        .reset_index(drop=True)
    )
    if len(df) < antes:
        log.info(f"[streaming] {antes - len(df)} reescrita(s) deduplicada(s)")
    return df


def filtrar_novos(df: pd.DataFrame) -> pd.DataFrame:
    """Descarta eventos ja materializados, tornando a carga idempotente."""
    try:
        existentes = wr.athena.read_sql_query(
            sql=f"SELECT id_evento FROM {TABELA}",
            database=ATHENA_DATABASE,
            s3_output=ATHENA_S3_OUTPUT,
            ctas_approach=False,
        )["id_evento"]
    except Exception:
        log.info("[streaming] tabela ainda nao existe — carga inicial")
        return df

    novos = df[~df["id_evento"].isin(set(existentes))]
    log.info(f"[streaming] {len(novos)} evento(s) novos de {len(df)} lidos")
    return novos


def main() -> None:
    validar_config()
    log.info("=== Promovendo streaming Bronze -> Silver ===")

    bruto = ler_bronze_streaming()
    if bruto.empty:
        log.info("=== Nada a promover ===")
        return

    eventos = filtrar_novos(deduplicar(padronizar(bruto)))
    if eventos.empty:
        log.info("=== Silver ja esta atualizada ===")
        return

    resultado = validar_tabela(eventos, TABELA, ["id_evento"])

    wr.s3.to_parquet(
        df=eventos,
        path=DESTINO,
        dataset=True,
        mode="append",
        compression="snappy",
        database=ATHENA_DATABASE,
        table=TABELA,
    )
    log.info(f"[silver] {TABELA} atualizado (+{len(eventos)} linhas)")

    print(relatorio_consolidado([resultado]).to_string(index=False))
    log.info("=== Promocao concluida ===")


if __name__ == "__main__":
    main()
