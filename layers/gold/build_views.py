"""Cria as views analiticas da camada Gold no Athena, usadas pelo dashboard."""
import awswrangler as wr
from config.logger import get_logger
from config.settings import ATHENA_DATABASE, ATHENA_S3_OUTPUT

log = get_logger("views")

VIEWS = {
    "vw_regiao_ano": """
        SELECT u.regiao, f.ano,
          COUNT(*) AS qtd_municipios,
          ROUND(AVG(f.taxa_realizada), 1) AS taxa_media,
          ROUND(AVG(f.meta), 1) AS meta_media,
          ROUND(AVG(f.gap_meta), 1) AS gap_medio,
          ROUND(100 * AVG(CAST(f.meta_atingida AS INTEGER)), 1) AS pct_atingiu
        FROM fato_alfabetizacao f
        JOIN dim_municipio m ON f.id_municipio = m.id_municipio
        JOIN dim_uf u ON m.sigla_uf = u.sigla_uf
        WHERE f.gap_meta IS NOT NULL
        GROUP BY u.regiao, f.ano
    """,
    "vw_uf_ano": """
        SELECT u.sigla_uf, u.regiao, f.ano,
          COUNT(*) AS qtd_municipios,
          ROUND(AVG(f.taxa_realizada), 1) AS taxa_media,
          ROUND(AVG(f.meta), 1) AS meta_media,
          ROUND(AVG(f.gap_meta), 1) AS gap_medio,
          ROUND(100 * AVG(CAST(f.meta_atingida AS INTEGER)), 1) AS pct_atingiu
        FROM fato_alfabetizacao f
        JOIN dim_municipio m ON f.id_municipio = m.id_municipio
        JOIN dim_uf u ON m.sigla_uf = u.sigla_uf
        WHERE f.gap_meta IS NOT NULL
        GROUP BY u.sigla_uf, u.regiao, f.ano
    """,
    "vw_municipio": """
        SELECT m.nome_municipio, m.sigla_uf, u.regiao, f.ano,
          f.taxa_realizada, f.meta, f.gap_meta, f.meta_atingida
        FROM fato_alfabetizacao f
        JOIN dim_municipio m ON f.id_municipio = m.id_municipio
        JOIN dim_uf u ON m.sigla_uf = u.sigla_uf
        WHERE f.gap_meta IS NOT NULL
    """,
}

def main():
    log.info("=== Criando views da camada Gold (Athena) ===")
    for nome, corpo in VIEWS.items():
        ddl = f"CREATE OR REPLACE VIEW {nome} AS {corpo}"
        wr.athena.start_query_execution(
            sql=ddl, database=ATHENA_DATABASE,
            s3_output=ATHENA_S3_OUTPUT, wait=True,
        )
        log.info(f"[view] {nome} criada")
    log.info("=== Views concluidas ===")

if __name__ == "__main__":
    main()
