"""
Views analiticas da camada Gold no Athena, consumidas pelo dashboard.

Principios de modelagem aplicados aqui:

1. Nenhum filtro que descarte linha estruturalmente valida. A fato cobre
   tres casos temporais distintos - 2023 tem resultado sem meta, 2024 tem
   os dois, 2025-2030 tem meta sem resultado. Um `WHERE gap_meta IS NOT
   NULL` reduziria a serie inteira a 2024 silenciosamente.

2. Toda view agregada carrega `soma_*` e `qtd_*` alem da media. Media de
   media nao e reagregavel: a media nacional calculada a partir das medias
   por UF diverge da media calculada sobre os municipios. Com soma e
   contagem, o consumidor reagrega em qualquer nivel sem perder precisao.

3. Os joins com as dimensoes sao LEFT. Um municipio ausente do diretorio
   do IBGE deve aparecer com regiao nula, nao sumir da contagem.

Criterio oficial do indicador: a media e sempre municipal. O municipio e a
unidade de gestao da politica publica, entao UF e regiao sao agregacoes de
municipios - nunca medias de medias.

Nota de portabilidade: o Athena roda sobre Trino, que nao possui `COUNTIF`.
As contagens condicionais usam `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`, que
funciona em qualquer engine SQL.
"""
import awswrangler as wr

from config.logger import get_logger
from config.settings import ANO_ULTIMO_RESULTADO, ATHENA_DATABASE, ATHENA_S3_OUTPUT, validar_config

log = get_logger("views")


# Bloco de metricas reutilizado pelas views agregadas.
# soma_* / qtd_* permitem reagregacao correta em qualquer nivel.
METRICAS = """
          COUNT(*) AS municipios,

          SUM(f.taxa_realizada) AS soma_taxa,
          SUM(CASE WHEN f.taxa_realizada IS NOT NULL THEN 1 ELSE 0 END) AS qtd_com_taxa,

          SUM(f.meta) AS soma_meta,
          SUM(CASE WHEN f.meta IS NOT NULL THEN 1 ELSE 0 END) AS qtd_com_meta,

          SUM(CASE WHEN f.meta_atingida THEN 1 ELSE 0 END) AS qtd_atingiu,
          SUM(CASE WHEN f.meta_atingida IS NOT NULL THEN 1 ELSE 0 END) AS qtd_comparavel,

          ROUND(AVG(f.taxa_realizada), 1) AS taxa_media,
          ROUND(AVG(f.meta), 1) AS meta_media,
          ROUND(AVG(f.gap_meta), 1) AS gap_medio
"""

# dim_tempo na Gold guarda apenas o ano. O tipo do ano e derivado aqui para
# nao exigir rebuild da dimensao, mantendo a mesma semantica do outro repo.
TIPO_ANO = f"""
          CASE
            WHEN f.ano < {ANO_ULTIMO_RESULTADO} THEN 'resultado'
            WHEN f.ano = {ANO_ULTIMO_RESULTADO} THEN 'resultado_e_meta'
            ELSE 'projecao'
          END AS tipo_ano
"""

JOINS = """
        FROM fato_alfabetizacao f
        LEFT JOIN dim_municipio m ON f.id_municipio = m.id_municipio
        LEFT JOIN dim_uf u ON m.sigla_uf = u.sigla_uf
"""

VIEWS = {
    "vw_uf_ano": """
        SELECT
          u.sigla_uf,
          u.regiao,
          f.ano,
""" + TIPO_ANO + "," + METRICAS + JOINS + """
        GROUP BY u.sigla_uf, u.regiao, f.ano
    """,

    "vw_regiao_ano": """
        SELECT
          u.regiao,
          f.ano,
""" + TIPO_ANO + "," + METRICAS + JOINS + """
        GROUP BY u.regiao, f.ano
    """,

    "vw_municipio": """
        SELECT
          f.id_municipio,
          m.nome_municipio,
          m.sigla_uf,
          u.regiao,
          f.ano,
""" + TIPO_ANO + """,
          f.taxa_realizada,
          f.meta,
          f.gap_meta,
          f.meta_atingida
""" + JOINS,
}


def diagnosticar(nome: str) -> None:
    """
    Loga a cobertura da view por ano.

    Alarme contra silent-drop: se um ano conhecido sumir da contagem,
    aparece aqui antes de chegar ao dashboard.
    """
    if nome == "vw_municipio":
        sql = f"""
            SELECT ano,
                   COUNT(*) AS linhas,
                   SUM(CASE WHEN taxa_realizada IS NOT NULL THEN 1 ELSE 0 END) AS com_taxa,
                   SUM(CASE WHEN meta IS NOT NULL THEN 1 ELSE 0 END) AS com_meta
            FROM {nome} GROUP BY ano ORDER BY ano
        """
    else:
        sql = f"""
            SELECT ano,
                   SUM(municipios) AS linhas,
                   SUM(qtd_com_taxa) AS com_taxa,
                   SUM(qtd_com_meta) AS com_meta
            FROM {nome} GROUP BY ano ORDER BY ano
        """

    df = wr.athena.read_sql_query(
        sql=sql,
        database=ATHENA_DATABASE,
        s3_output=ATHENA_S3_OUTPUT,
        ctas_approach=False,
    )
    log.info(f"[view] {nome} - cobertura por ano:")
    for _, linha in df.iterrows():
        log.info(
            f"         {linha['ano']}: {linha['linhas']} linhas | "
            f"com taxa: {linha['com_taxa']} | com meta: {linha['com_meta']}"
        )


def main() -> None:
    validar_config()
    log.info("=== Criando views da camada Gold (Athena) ===")

    for nome, corpo in VIEWS.items():
        ddl = f"CREATE OR REPLACE VIEW {nome} AS {corpo}"
        wr.athena.start_query_execution(
            sql=ddl,
            database=ATHENA_DATABASE,
            s3_output=ATHENA_S3_OUTPUT,
            wait=True,
        )
        log.info(f"[view] {nome} criada")
        diagnosticar(nome)

    log.info("=== Views concluidas ===")


if __name__ == "__main__":
    main()
