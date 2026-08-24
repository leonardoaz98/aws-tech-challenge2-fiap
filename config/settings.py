"""
Configuracao central do projeto (AWS).

Le variaveis de ambiente do .env uma unica vez e expoe como constantes.
Camadas materializadas em S3, consultadas via Athena/Glue.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Raiz do projeto ---
ROOT_DIR = Path(__file__).resolve().parent.parent

# --- AWS ---
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "tc2-fiap-datalake")
S3_BRONZE = f"s3://{S3_BUCKET}/bronze"
S3_SILVER = f"s3://{S3_BUCKET}/silver"
S3_GOLD = f"s3://{S3_BUCKET}/gold"
ATHENA_DATABASE = os.getenv("ATHENA_DATABASE", "tc2_gold")
ATHENA_S3_OUTPUT = os.getenv("ATHENA_S3_OUTPUT", "s3://tc2-fiap-athena-results/")

# --- Base dos Dados (fonte publica dos microdados) ---
BD_DATASET = "br_inep_avaliacao_alfabetizacao"
BD_BILLING_PROJECT = os.getenv("BD_BILLING_PROJECT")  # billing p/ consultar a fonte publica

# --- Caminhos locais (staging temporario da ingestao) ---
DATA_DIR = ROOT_DIR / "data"
BRONZE_DIR = DATA_DIR / "bronze"

# --- Dominio ---
ANOS_META = [2024, 2025, 2026, 2027, 2028, 2029, 2030]

# Tabela -> colunas de particionamento na Bronze (lista vazia = sem particao)
TABELAS_BRONZE = {
    "uf": ["ano"],
    "municipio": ["ano"],
    "alunos": ["ano"],
    "meta_alfabetizacao_brasil": [],
    "meta_alfabetizacao_uf": [],
    "meta_alfabetizacao_municipio": [],
    "dicionario": [],
}

TABELAS_SEM_ANO = {
    "meta_alfabetizacao_brasil",
    "meta_alfabetizacao_uf",
    "meta_alfabetizacao_municipio",
    "dicionario",
}


def validar_config() -> None:
    """Falha cedo se alguma variavel obrigatoria estiver ausente."""
    obrigatorias = {"S3_BUCKET": S3_BUCKET, "AWS_REGION": AWS_REGION}
    faltando = [k for k, v in obrigatorias.items() if not v]
    if faltando:
        raise EnvironmentError(
            f"Variaveis ausentes no .env: {', '.join(faltando)}. "
            f"Copie .env.example para .env e preencha."
        )
