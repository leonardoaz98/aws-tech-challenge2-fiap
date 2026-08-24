"""Streaming simulado - ingestao de eventos na Bronze do S3."""
import argparse, random, time
from datetime import datetime, timezone
import awswrangler as wr
import pandas as pd

S3_BRONZE_STREAMING = "s3://tc2-fiap-datalake/bronze/streaming"
MUNICIPIOS = [f"{random.randint(1100015, 5300108):07d}" for _ in range(200)]
REDES = ["1", "2", "3"]

def gerar_evento():
    return {"id_municipio": random.choice(MUNICIPIOS), "ano": 2024,
            "rede": random.choice(REDES),
            "taxa_realizada": round(random.uniform(45.0, 99.0), 2),
            "media_portugues": round(random.uniform(4.0, 9.0), 2),
            "event_ts": datetime.now(timezone.utc).isoformat()}

def gravar_lote(eventos, seq):
    df = pd.DataFrame(eventos)
    agora = datetime.now(timezone.utc)
    prefixo = agora.strftime("dt=%Y-%m-%d/hora=%H")
    nome = agora.strftime(f"%Y%m%dT%H%M%S_batch{seq:04d}.parquet")
    destino = f"{S3_BRONZE_STREAMING}/{prefixo}/{nome}"
    wr.s3.to_parquet(df=df, path=destino, compression="snappy")
    return destino

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--batches", type=int, default=0)
    p.add_argument("--intervalo", type=float, default=3.0)
    p.add_argument("--tamanho", type=int, default=25)
    a = p.parse_args()
    print("=== Streaming simulado -> Bronze/S3 ===", flush=True)
    seq = total = 0
    try:
        while True:
            seq += 1
            eventos = [gerar_evento() for _ in range(a.tamanho)]
            destino = gravar_lote(eventos, seq)
            total += len(eventos)
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"[{ts}] lote #{seq:04d} | {len(eventos)} eventos | total={total} | -> {destino.split('/')[-1]}", flush=True)
            if a.batches and seq >= a.batches:
                break
            time.sleep(a.intervalo)
    except KeyboardInterrupt:
        print("\n--- Interrompido ---", flush=True)
    print(f"=== Encerrado: {seq} lotes, {total} eventos ===", flush=True)

if __name__ == "__main__":
    main()
