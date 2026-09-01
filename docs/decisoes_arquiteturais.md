# Decisões Arquiteturais

## 2026-08-28 — Critério unificado de média (taxa/meta realizada)

### Problema

O mesmo indicador (taxa de alfabetização realizada) aparecia com valores
diferentes no dashboard dependendo de qual caminho de agregação era usado
para chegar ao número nacional/regional. Exemplo com os dados de 2024:

| Caminho | Cálculo | Valor |
|---|---|---|
| KPI do topo do dashboard | média não ponderada das 25 linhas de `vw_uf_ano` | 59,5% |
| Gráficos por região | média não ponderada das 5 linhas de `vw_regiao_ano` | 62,4% |
| Card "Trajetória até 2030" | `AVG(taxa_realizada)` direto sobre os 5.448 municípios do fato | 62,8% |

O mesmo padrão já estava registrado no `CLAUDE.md` (pendência 3) para 2023
(56,8% vs 59,6%), e foi reproduzido aqui: `56,8% / 59,6% / 60,3%`.

### Causa raiz

**Não é bug de JOIN ou de SQL.** Foi verificado que:
- `dim_municipio` não tem `id_municipio` duplicado (5.571 linhas = 5.571 IDs distintos).
- O join `fato_alfabetizacao ⋈ dim_municipio ⋈ dim_uf` não gera fan-out
  (5.448 linhas em 2024 antes e depois do join).
- Não há órfãos (`fato` sem correspondência em `dim_municipio`).

A causa é estatística: `vw_uf_ano` e `vw_regiao_ano` calculam corretamente a
média municipal *dentro de cada grupo* (cada UF, cada região), mas UFs e
regiões têm quantidades muito desiguais de municípios (ex.: SP ~645
municípios vs. RR 15). Tirar uma média **não ponderada** entre essas médias
de grupo (uma linha = um voto, independente de quantos municípios ela
representa) é o clássico problema de "média das médias": o resultado não
reproduz a média direta no nível do município.

### Critério oficial

**Média simples no nível do município.**

Justificativa: o Compromisso Nacional Criança Alfabetizada pactua metas
**por município**, então a unidade de agregação correta é o município — não
a UF nem a região. Isso também preserva a leitura de equidade territorial
(um município pequeno não desaparece silenciosamente numa média ponderada
por matrícula).

**Trade-off documentado**: essa métrica responde "qual a taxa do município
*típico*", **não** "qual percentual das crianças brasileiras está
alfabetizado" — essa segunda pergunta exigiria ponderar por número de
alunos/matrículas, o que não é viável hoje: `fato_alfabetizacao` não tem
coluna de contagem de alunos (colunas disponíveis: `id_municipio`, `ano`,
`taxa_realizada`, `media_portugues`, `meta`, `percentual_participacao`,
`rede`, `gap_meta`, `meta_atingida`, `nivel_alfabetizacao`). Adotar esse
critério exigiria uma nova fonte de dados.

### Consequência prática: como reagregar corretamente

`vw_uf_ano.taxa_media` e `vw_regiao_ano.taxa_media` (e `meta_media`,
`gap_medio`) continuam sendo a média municipal **dentro do grupo** — isso já
estava correto. O que muda é como um consumidor deve **reagregar** essas
linhas para obter um número regional/nacional consistente com a média
municipal direta:

```sql
-- CORRETO: ponderado por qtd_com_taxa (ou qtd_com_meta para meta_media)
SELECT SUM(taxa_media * qtd_com_taxa) / SUM(qtd_com_taxa) FROM vw_uf_ano WHERE ano = 2024;

-- ERRADO: media nao ponderada entre linhas ja agregadas ("media das medias")
SELECT AVG(taxa_media) FROM vw_uf_ano WHERE ano = 2024;
```

`qtd_com_taxa` e `qtd_com_meta` já existiam nas views como colunas de
transparência de cobertura; agora também servem como peso de reagregação.

### Mudança aplicada

Em `layers/gold/build_views.py`, nas views `vw_uf_ano` e `vw_regiao_ano`:
- Removido o `ROUND(...,1)` interno de `taxa_media`, `meta_media` e
  `gap_medio`. Arredondar antes de reagregar introduzia um resíduo (~0,005
  p.p. em 2024) que impedia a reconciliação exata com a média municipal
  direta. `pct_atingiu` manteve o arredondamento (não faz parte deste bug —
  já é uma proporção de contagens, não uma média-de-médias).
- Aproveitado para sincronizar o script com o SQL que já estava implantado
  no Athena (estava desatualizado no repo): `INNER JOIN dim_uf`, colunas
  `qtd_com_taxa`/`qtd_com_meta`, sem o antigo `WHERE gap_meta IS NOT NULL`
  (que já tinha sido removido no Athena mas não no repo). `vw_municipio`
  também foi sincronizada (remoção do mesmo `WHERE` obsoleto, sem mudança de
  comportamento — o Athena já não tinha esse filtro).

### Validação (antes/depois)

Reconciliação entre os 3 caminhos, usando a fórmula ponderada acima, para
2023 e 2024:

| Ano | Município (direto) | UF (ponderado) | Região (ponderado) |
|---|---|---|---|
| 2023 | 60,278465491923775% | 60,278465491923626% | 60,278465491923654% |
| 2024 | 62,79976688693113% | 62,799766886931% | 62,79976688693098% |

Os três caminhos batem até a 10ª casa decimal (a diferença residual é ruído
de ponto flutuante, não de arredondamento). Antes da mudança, a versão
arredondada tinha um resíduo de ~0,005 p.p. em 2024.

Para referência, os valores **não ponderados** (o que uma média simples
entre linhas de `vw_uf_ano`/`vw_regiao_ano` ainda produz) continuam
divergindo, como esperado — isso é uma característica da agregação
não ponderada, não um defeito nas views:

| Ano | KPI topo (UF, não ponderado) | Região (não ponderado) | Município (direto) |
|---|---|---|---|
| 2023 | 56,8% | 59,6% | 60,3% |
| 2024 | 59,5% | 62,4% | 62,8% |

### Pendência explícita: `dashboard/app.py`

O dashboard **não foi alterado** nesta tarefa (fora de escopo combinado).
O card de KPI do topo (`dados['taxa_media'].mean()` em `dashboard/app.py`)
continua fazendo a média **não ponderada** sobre as linhas de `vw_uf_ano` —
ou seja, o número exibido na tela **continua sendo 59,5%/56,8%** (o valor
"errado" da tabela acima), mesmo com a correção aplicada nas views.

**Follow-up necessário**: trocar `dados['taxa_media'].mean()` (e o
equivalente nos gráficos por região) por uma média ponderada por
`qtd_com_taxa`/`qtd_com_meta` — ou substituir por uma consulta direta a
`fato_alfabetizacao` — para que o dashboard exiba o número unificado
(62,8% em 2024, não 59,5%).

## Pendências em aberto herdadas do `CLAUDE.md`

1. RR (UF) tem 15 municípios em `dim_municipio` e 0 em `fato_alfabetizacao`
   — diagnosticado como lacuna de origem (RR está ausente em
   `municipio_resultado`, `uf_resultado` e `meta_municipio` na Silver,
   antes de qualquer filtro; não há órfãos nem mismatch de chave). Não
   confirmado 100% contra a fonte bruta porque a Bronze batch
   (`bronze/municipio`, `bronze/uf`, etc.) não existe mais no S3 no momento
   desta investigação — só `bronze/streaming/`.
2. 2023 tem 24 UFs contra 25 dos demais anos — terceira UF ausente ainda não
   identificada.


---

## 2026-08-31 — Follow-up do dashboard concluído

O follow-up registrado acima foi executado. O `dashboard/app.py` deixou de
usar `dados['taxa_media'].mean()` e passou a reagregar a partir de
`soma_taxa`/`qtd_com_taxa`, através da função `media_municipal()`. O número
exibido no topo agora coincide com a média municipal em qualquer recorte de
ano e região.

As views também perderam o `WHERE f.gap_meta IS NOT NULL`, que reduzia toda
a série temporal a 2024 — o mesmo silent-drop identificado e corrigido no
repositório GCP. Os joins com as dimensões passaram a `LEFT JOIN` para não
descartar município ausente do diretório do IBGE.

### Diagnóstico de cobertura como alarme

`build_views.py` passa a logar a distribuição de linhas por ano após criar
cada view. Silent-drop é a classe de bug mais cara deste projeto porque não
gera exceção: um filtro mal colocado produz um dashboard que parece
funcionar. Logar a cobertura torna a perda visível na hora.

### Nota de portabilidade SQL

O Athena roda sobre Trino, que não possui `COUNTIF`. As contagens
condicionais usam `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`, equivalente e
portável entre engines. Esta é a única divergência sintática relevante em
relação às views do repositório GCP, que rodam sobre BigQuery.

### Tipo do ano derivado na view

A `dim_tempo` da Gold guarda apenas o ano, sem a coluna `tipo_ano`. Em vez
de exigir rebuild da dimensão, o tipo é derivado no SQL da view a partir de
`ANO_ULTIMO_RESULTADO`, preservando a mesma semântica dos três casos
temporais usada no outro repositório.

---

## 2026-08-31 — Leitura do painel

Três problemas encontrados em inspeção visual do dashboard renderizado, sem
relação com correção de dados mas com impacto direto em como o número é
interpretado.

**Trajetória sugerindo continuidade inexistente.** Realizado e meta usavam
a mesma cor e o mesmo traçado. Como as séries se encostam em 2024, o
resultado visual era uma única linha subindo até 80%, dando a entender que
a trajetória futura já estava contratada. A meta passa a usar traçado
tracejado em cor própria, com área sombreada e marco vertical em 2024
separando medido de pactuado.

**Ordenação padrão destacando o dado menos confiável.** A tabela municipal
abria por superávit, cujo topo é dominado por gaps acima de 50 p.p. —
exatamente o que a nota metodológica do rodapé classifica como meta mal
calibrada. Déficit passa a ser o padrão, que é também onde mora a decisão de
política pública.

**Ordenações divergentes entre gráficos lado a lado.** Os dois gráficos
regionais usavam critérios diferentes de ordenação, forçando o leitor a
reprocessar a sequência das regiões ao comparar. Passam a compartilhar uma
ordem categórica única, derivada da taxa realizada.
