# Qualidade de Dados

Validacoes reutilizaveis aplicadas na promocao entre camadas (Bronze → Silver → Gold). Cada checagem devolve um relatorio estruturado; falhas podem bloquear a promocao.

## Regras implementadas

- **Duplicidade:** verifica registros duplicados na chave de negocio
- **Valores ausentes:** detecta nulos em colunas-chave e calcula % nulo medio
- **Integridade referencial:** confere se chaves da tabela filha existem na dimensao
- **Consistencia entre tabelas:** validacao cruzada fato × dimensoes

## Principio

Falha de qualidade em chave (duplicata ou nulo) **bloqueia a promocao** entre camadas (`bloquear_se_reprovado`). O relatorio consolidado registra o status de cada tabela.

Script: `quality/validations.py`
