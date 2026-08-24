"""
Camada Gold - Modelagem Dimensional (AWS)

Le a Silver do S3, enriquece com diretorios territoriais e materializa um
modelo dimensional (fato + dimensoes) em Parquet no S3, pronto para
dashboards, analise estatistica e treino de modelos.
"""
import awswrangler as wr
import pandas as pd

from config.logger import get_logger
from config.settings import S3_SILVER, S3_GOLD, validar_config
from quality.validations import relatorio_consolidado, validar_tabela

log = get_logger("gold")

ANO_ULTIMO_RESULTADO = 2024
REDE_MUNICIPAL = "3"  # codigo 3 = Municipal (dicionario Base dos Dados)

FAIXAS_NIVEL = {
    0: ("Critico", "0 a 39,9%"),
    1: ("Muito baixo", "40 a 49,9%"),
    2: ("Baixo", "50 a 59,9%"),
    3: ("Medio", "60 a 69,9%"),
    4: ("Alto", "70 a 79,9%"),
    5: ("Muito alto", "80 a 100%"),
}


def ler_silver(tabela: str) -> pd.DataFrame:
    """Le uma tabela da camada Silver no S3."""
    df = wr.s3.read_parquet(path=f"{S3_SILVER}/{tabela}/", dataset=True)
    log.info(f"[silver/{tabela}] {len(df)} linhas lidas")
    return df


def construir_dim_uf(municipio: pd.DataFrame) -> pd.DataFrame:
    """Dimensao de UF a partir dos municipios."""
    regioes = {
        "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
        "RO": "Norte", "RR": "Norte", "TO": "Norte",
        "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
        "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
        "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
        "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
        "PR": "Sul", "RS": "Sul", "SC": "Sul",
    }
    ufs = sorted(municipio["sigla_uf"].dropna().unique())
    return pd.DataFrame({
        "sigla_uf": ufs,
        "nome_uf": ufs,
        "regiao": [regioes.get(u, "Desconhecida") for u in ufs],
    })


def construir_dim_nivel() -> pd.DataFrame:
    """Dimensao de nivel de alfabetizacao."""
    return pd.DataFrame([
        {"nivel_alfabetizacao": k, "descricao_nivel": v[0], "faixa_taxa": v[1]}
        for k, v in FAIXAS_NIVEL.items()
    ])


def classificar_nivel(taxa: float) -> int:
    """Mapeia taxa de alfabetizacao para faixa de nivel (0-5)."""
    if pd.isna(taxa):
        return None
    for nivel, (_, faixa) in FAIXAS_NIVEL.items():
        limites = faixa.replace("%", "").replace(",", ".").split(" a ")
        if float(limites[0]) <= taxa <= float(limites[1]):
            return nivel
    return 5


def gravar_gold(df: pd.DataFrame, tabela: str) -> None:
    """Grava uma tabela na camada Gold do S3."""
    wr.s3.to_parquet(df=df, path=f"{S3_GOLD}/{tabela}/", dataset=True,
                     mode="overwrite", compression="snappy")
    log.info(f"[gold] {tabela} gravado ({len(df)} linhas)")


def main() -> None:
    validar_config()
    log.info("=== Iniciando construcao da camada Gold ===")
    resultados = []

    municipio = ler_silver("municipio_resultado")
    meta_mun = ler_silver("meta_municipio")

    # Dimensoes
    dim_uf = construir_dim_uf(municipio)
    dim_nivel = construir_dim_nivel()
    dim_municipio = municipio[["id_municipio", "sigla_uf"]].drop_duplicates()

    # Fato: resultados municipais (rede municipal) x metas
    fato = municipio[municipio.get("rede", REDE_MUNICIPAL) == REDE_MUNICIPAL].copy()
    fato = fato.merge(
        meta_mun[["id_municipio", "ano_meta", "meta_alfabetizacao"]],
        left_on=["id_municipio", "ano"], right_on=["id_municipio", "ano_meta"],
        how="left",
    )
    if "taxa_alfabetizacao" in fato.columns:
        fato["nivel_alfabetizacao"] = fato["taxa_alfabetizacao"].apply(classificar_nivel)

    dim_tempo = pd.DataFrame({"ano": sorted(fato["ano"].dropna().unique())})

    # Validacoes
    resultados.append(validar_tabela(dim_uf, "dim_uf", ["sigla_uf"]))
    resultados.append(validar_tabela(dim_municipio, "dim_municipio", ["id_municipio"]))
    resultados.append(validar_tabela(dim_nivel, "dim_nivel", ["nivel_alfabetizacao"]))
    resultados.append(validar_tabela(fato, "fato_alfabetizacao", ["id_municipio", "ano"]))

    # Escrita
    gravar_gold(dim_uf, "dim_uf")
    gravar_gold(dim_municipio, "dim_municipio")
    gravar_gold(dim_tempo, "dim_tempo")
    gravar_gold(dim_nivel, "dim_nivel")
    gravar_gold(fato, "fato_alfabetizacao")

    log.info("=== Relatorio de qualidade ===")
    print(relatorio_consolidado(resultados).to_string(index=False))
    log.info("=== Gold concluida ===")


if __name__ == "__main__":
    main()
