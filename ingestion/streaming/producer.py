"""
Producer - simulacao de eventos de atualizacao do indicador.

Reproduz o cenario real em que estados e municipios enviam correcoes e
novas medicoes fora do ciclo anual do Saeb, gravando micro-batches direto
na zona de streaming da Bronze.

Por que nao ha broker: a conta AWS do projeto opera dentro do free tier,
que nao cobre Kinesis Data Streams. A gravacao direta em S3 preserva a
semantica de ingestao continua sem custo, e a decisao esta registrada em
`docs/decisoes_arquiteturais.md` como trade-off consciente de FinOps.

Os municipios sorteados sao lidos da propria Gold, entao os eventos
referenciam chaves que existem de fato - um gerador com IDs sinteticos
produziria orfas na validacao de integridade e mascararia o comportamento
real do pipeline.

Uso:
    python -m ingestion.streaming.producer --batches 8 --intervalo 3
"""

import argparse
import random
import time
import uuid
from datetime import datetime, timezone

import awswrangler as wr
import pandas as pd

from config.logger import get_logger
from config.settings import (
    ATHENA_DATABASE,
    ATHENA_S3_OUTPUT,
    S3_BRONZE_STREAMING,
    validar_config,
)

log = get_logger("producer")

TIPOS_EVENTO = ["atualizacao_indicador", "nova_medicao", "revisao_meta"]
ORIGENS = ["secretaria_municipal", "secretaria_estadual", "inep"]

METRICAS = {"gerados": 0, "gravados": 0, "lotes": 0}


def amostrar_municipios(limite: int = 500) -> list:
    """Sorteia municipios reais da dimensao para lastrear os eventos."""
    df = wr.athena.read_sql_query(
        sql=f"""
            SELECT m.id_municipio, m.sigla_uf
            FROM dim_municipio m
            ORDER BY RANDOM()
            LIMIT {limite}
        """,
        database=ATHENA_DATABASE,
        s3_output=ATHENA_S3_OUTPUT,
        ctas_approach=False,
    )
    log.info(f"[producer] {len(df)} municipios carregados para amostragem")
    return df.to_dict("records")


def gerar_evento(municipios: list) -> dict:
    """Monta um evento com esquema estavel e chave de deduplicacao."""
    municipio = random.choice(municipios)

    return {
        "id_evento": str(uuid.uuid4()),
        "tipo_evento": random.choice(TIPOS_EVENTO),
        "origem": random.choice(ORIGENS),
        "id_municipio": municipio["id_municipio"],
        "sigla_uf": municipio["sigla_uf"],
        "ano_referencia": random.choice([2023, 2024, 2025]),
        "taxa_alfabetizacao": round(random.uniform(25.0, 98.0), 2),
        "timestamp_evento": datetime.now(timezone.utc).isoformat(),
    }


def gravar_lote(eventos: list, seq: int) -> str:
    """
    Materializa o micro-batch como um unico Parquet na Bronze.

    Um arquivo por evento geraria milhares de objetos minusculos: o S3
    cobra por operacao e a leitura analitica degrada - o classico small
    files problem.
    """
    df = pd.DataFrame(eventos)
    agora = datetime.now(timezone.utc)
    df["_ingestao_timestamp"] = agora
    df["_fonte"] = "streaming_simulado"

    prefixo = agora.strftime("dt=%Y-%m-%d/hora=%H")
    nome = agora.strftime(f"%Y%m%dT%H%M%S_batch{seq:04d}.parquet")
    destino = f"{S3_BRONZE_STREAMING}/{prefixo}/{nome}"

    wr.s3.to_parquet(df=df, path=destino, compression="snappy")

    METRICAS["gravados"] += len(df)
    METRICAS["lotes"] += 1
    return destino


def relatorio() -> None:
    """Resumo de observabilidade da execucao."""
    log.info("=== Relatorio da ingestao streaming ===")
    log.info(f"  eventos gerados  : {METRICAS['gerados']}")
    log.info(f"  eventos gravados : {METRICAS['gravados']}")
    log.info(f"  micro-batches    : {METRICAS['lotes']}")

    if METRICAS["gerados"] != METRICAS["gravados"]:
        log.warning(
            f"[alerta] {METRICAS['gerados'] - METRICAS['gravados']} evento(s) "
            "gerados mas nao gravados"
        )


def main() -> None:
    validar_config()
    parser = argparse.ArgumentParser(description="Simulador de eventos do indicador")
    parser.add_argument("--batches", type=int, default=8, help="0 = continuo")
    parser.add_argument("--intervalo", type=float, default=3.0, help="segundos entre lotes")
    parser.add_argument("--tamanho", type=int, default=25, help="eventos por lote")
    args = parser.parse_args()

    municipios = amostrar_municipios()
    log.info(f"[producer] gravando em {S3_BRONZE_STREAMING}")

    seq = 0
    try:
        while True:
            seq += 1
            eventos = [gerar_evento(municipios) for _ in range(args.tamanho)]
            METRICAS["gerados"] += len(eventos)
            destino = gravar_lote(eventos, seq)

            log.info(
                f"[producer] lote {seq}: {len(eventos)} evento(s) -> "
                f"{destino.split('/')[-1]}"
            )

            if args.batches and seq >= args.batches:
                break
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        log.info("[producer] interrompido pelo usuario")

    relatorio()


if __name__ == "__main__":
    main()
