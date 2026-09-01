# Ingestão Streaming

Ingestão de eventos em tempo quase real na zona de streaming da Bronze,
complementando a carga batch anual do Saeb.

## Por que streaming aqui

O Saeb é anual, mas o dado não para de se mover entre as ondas: secretarias
municipais e estaduais enviam correções de cadastro, revisões de meta e novas
medições ao longo do ano. Modelar isso como batch significaria esperar o
próximo ciclo para refletir uma correção — inaceitável para uma política com
meta anual até 2030.

## Por que não há broker

A conta AWS do projeto opera dentro do free tier, que **não cobre Kinesis Data
Streams**. Em vez de introduzir custo, o producer grava micro-batches direto
em `s3://<bucket>/bronze/streaming/`, preservando a semântica de ingestão
contínua a custo zero.

É um trade-off consciente, não um atalho: o que se perde é o desacoplamento
entre produtor e consumidor e a garantia de entrega do broker. O que se
mantém é o essencial — chegada contínua, particionamento temporal,
deduplicação e promoção controlada para a Silver. A decisão está registrada em
[`docs/decisoes_arquiteturais.md`](../../docs/decisoes_arquiteturais.md).

No repositório GCP equivalente, onde o Pub/Sub cabe no free tier, o mesmo
fluxo usa broker de verdade — a diferença é de plataforma, não de desenho.

## Componentes

| Arquivo | Papel |
|---|---|
| `producer.py` | Simula eventos das secretarias e grava micro-batches na Bronze |

A promoção para a Silver fica em `layers/silver/build_streaming.py`.

## Esquema do evento

```json
{
  "id_evento": "uuid",
  "tipo_evento": "atualizacao_indicador | nova_medicao | revisao_meta",
  "origem": "secretaria_municipal | secretaria_estadual | inep",
  "id_municipio": "3550308",
  "sigla_uf": "SP",
  "ano_referencia": 2024,
  "taxa_alfabetizacao": 76.4,
  "timestamp_evento": "2026-03-11T14:02:31+00:00"
}
```

Os municípios sorteados vêm da própria `dim_municipio` via Athena. Um gerador
com identificadores sintéticos produziria órfãs na validação de integridade
referencial e mascararia o comportamento real do pipeline.

## Decisões de design

**Micro-batch em vez de um arquivo por evento.** O S3 cobra por operação, e
milhares de objetos minúsculos degradam a leitura analítica — o clássico
*small files problem*. Cada lote agrupa 25 eventos por padrão.

**Particionamento por data e hora.** Os arquivos vão para
`dt=YYYY-MM-DD/hora=HH/`, permitindo que a promoção leia apenas as partições
necessárias.

**Deduplicação por `id_evento` na Silver.** Garante semântica exactly-once na
camada analítica mesmo que um lote seja reescrito após falha.

**Zona separada da Bronze.** Origens com contratos e cadências diferentes não
compartilham prefixo.

## Execução

```bash
# 1. Gera 8 lotes de 25 eventos, com 3 s de intervalo
python -m ingestion.streaming.producer --batches 8 --intervalo 3

# 2. Promove os eventos para a Silver
python -m layers.silver.build_streaming
```

Use `--batches 0` para execução contínua até `Ctrl+C`.

## Observabilidade

O producer reporta ao final: eventos gerados, gravados e número de
micro-batches, com alerta quando os dois primeiros divergem. A promoção para a
Silver emite o relatório consolidado de qualidade, com contagem de duplicatas
e nulos em chave.
