"""
Camada Silver - Tratamento e Integracao (AWS)

Le a Bronze do S3, aplica limpeza e padronizacao, converte as metas de
formato wide para long, valida qualidade e grava a Silver no S3.
"""
import re
import awswrangler as wr
import pandas as pd

from config.logger import get_logger
from config.settings import (
    ANOS_META, S3_BRONZE, S3_SILVER, TABELAS_SEM_ANO, validar_config,
)
from quality.validations import (
    relatorio_consolidado, validar_integridade_referencial, validar_tabela,
)

log = get_logger("silver")


def ler_bronze(tabela: str) -> pd.DataFrame:
    """Le os Parquet de uma tabela da Bronze no S3."""
    caminho = f"{S3_BRONZE}/{tabela}/"
    df = wr.s3.read_parquet(path=caminho, dataset=True)
    if tabela in TABELAS_SEM_ANO:
        df = df.drop_duplicates().reset_index(drop=True)
    log.info(f"[bronze/{tabela}] {df.shape[0]} linhas lidas")
    return df


def padronizar(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos e valores de texto das chaves e categorias."""
    df = df.copy()
    if "id_municipio" in df.columns:
        df["id_municipio"] = df["id_municipio"].astype(str).str.strip().str.zfill(7)
    if "sigla_uf" in df.columns:
        df["sigla_uf"] = df["sigla_uf"].astype(str).str.strip().str.upper()
    if "ano" in df.columns:
        df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    for col in ["rede", "serie"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.lower()
    return df


def remover_colunas_constantes(df: pd.DataFrame, protegidas: list) -> pd.DataFrame:
    """Descarta colunas com um unico valor, exceto as protegidas."""
    constantes = [c for c in df.columns
                  if c not in protegidas and df[c].nunique(dropna=False) <= 1]
    if constantes:
        log.info(f"  removendo colunas constantes: {constantes}")
    return df.drop(columns=constantes)


def limpar_metadados(df: pd.DataFrame) -> pd.DataFrame:
    """Remove as colunas tecnicas de rastreabilidade da Bronze."""
    return df.drop(columns=["_ingestao_timestamp", "_fonte"], errors="ignore")


def unpivot_metas(df: pd.DataFrame, chaves: list, nivel: str) -> pd.DataFrame:
    """Converte meta_alfabetizacao_2024..2030 de colunas para linhas."""
    cols_meta = [f"meta_alfabetizacao_{a}" for a in ANOS_META
                 if f"meta_alfabetizacao_{a}" in df.columns]
    id_vars = [c for c in chaves if c in df.columns]
    longo = df.melt(id_vars=id_vars, value_vars=cols_meta,
                    var_name="ano_meta", value_name="meta_alfabetizacao")
    longo["ano_meta"] = longo["ano_meta"].str.replace("meta_alfabetizacao_", "").astype(int)
    longo["nivel_territorial"] = nivel
    log.info(f"[metas/{nivel}] unpivot: {df.shape[0]} -> {longo.shape[0]} linhas")
    return longo


def gravar_s3(df: pd.DataFrame, tabela: str) -> None:
    """Grava a tabela na camada Silver do S3."""
    destino = f"{S3_SILVER}/{tabela}/"
    wr.s3.to_parquet(df=df, path=destino, dataset=True,
                     mode="overwrite", compression="snappy")
    log.info(f"[silver] {tabela} gravado no S3 ({len(df)} linhas)")


def main() -> None:
    validar_config()
    log.info("=== Iniciando construcao da camada Silver ===")
    resultados = []

    municipio = limpar_metadados(padronizar(ler_bronze("municipio")))
    municipio = remover_colunas_constantes(municipio, ["id_municipio", "ano"])
    resultados.append(validar_tabela(municipio, "municipio", ["id_municipio", "ano", "rede"]))

    uf = limpar_metadados(padronizar(ler_bronze("uf")))
    uf = remover_colunas_constantes(uf, ["sigla_uf", "ano"])
    resultados.append(validar_tabela(uf, "uf", ["sigla_uf", "rede", "ano"]))

    chaves_comuns = ["rede", "taxa_alfabetizacao", "percentual_participacao"]
    chaves_mun = ["id_municipio", "nivel_alfabetizacao"] + chaves_comuns
    meta_mun = unpivot_metas(padronizar(ler_bronze("meta_alfabetizacao_municipio")), chaves_mun, "municipio")
    meta_uf = unpivot_metas(padronizar(ler_bronze("meta_alfabetizacao_uf")), ["sigla_uf"] + chaves_comuns, "uf")
    meta_br = unpivot_metas(padronizar(ler_bronze("meta_alfabetizacao_brasil")), chaves_comuns, "brasil")

    resultados.append(validar_tabela(meta_mun, "meta_municipio", ["id_municipio", "ano_meta"]))
    resultados.append(validar_tabela(meta_uf, "meta_uf", ["sigla_uf", "ano_meta"]))

    validar_integridade_referencial(meta_mun, "meta_municipio", municipio, "id_municipio")
    validar_integridade_referencial(meta_uf, "meta_uf", uf, "sigla_uf")

    gravar_s3(municipio, "municipio_resultado")
    gravar_s3(uf, "uf_resultado")
    gravar_s3(meta_mun, "meta_municipio")
    gravar_s3(meta_uf, "meta_uf")
    gravar_s3(meta_br, "meta_brasil")

    log.info("=== Relatorio de qualidade ===")
    print(relatorio_consolidado(resultados).to_string(index=False))
    log.info("=== Silver concluida ===")


if __name__ == "__main__":
    main()
