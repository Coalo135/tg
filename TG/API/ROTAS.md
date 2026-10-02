# Rotas da API — referência para o front-end

> **Nota de atualização.** Este documento foi escrito na época do backend Supabase.
> O banco passou a ser **SQLite local** e a divulgação de **2025** foi importada.
> O contrato das rotas descritas aqui continua valendo; mudou o que está marcado
> abaixo, e foram acrescentadas as rotas `/ufs`, `/escolas`, `/anos` e `/planilhas`
> (ver README.md). A rota `/baixar` passou a receber `chave=` em vez de `indice=`.

## Sobre o projeto

Este é o backend de um **TCC (Trabalho de Graduação)** que analisa o **IDEB** — Índice de
Desenvolvimento da Educação Básica, o indicador oficial do governo brasileiro (INEP) que mede a
qualidade da educação básica em cada escola, município, estado e no país. O IDEB é calculado a
cada 2 anos (ciclos bienais, 2005 a 2023) e combina duas coisas numa nota de 0 a 10:

- **Fluxo escolar** — taxa de aprovação dos alunos (não repetem/não abandonam).
- **Aprendizado** — nota do SAEB (a prova padronizada aplicada nas escolas).

O projeto tem um pipeline de dados completo:

1. **Coleta** — baixa as planilhas oficiais do INEP.
2. **Limpeza** — trata o formato bruto (cabeçalho mesclado, dados ausentes) e carrega num banco
   SQLite local (tabela `ideb_resultados`, com 1,41 milhão de linhas — escola/município/UF/Brasil,
   2005–2025).
3. **Estatísticas** — médias, comparação do IDEB observado com a meta que o INEP projeta pra
   cada escola/município, evolução histórica.
4. **Estudo de caso** — o foco final é o Ceará (Sobral é citado como referência na literatura
   sobre o tema, por ter saído de notas baixas pra se tornar destaque nacional).

**Esta API** (FastAPI) expõe esse pipeline via HTTP pra alimentar um front-end (dashboard) que
vai visualizar esses dados: gráficos de evolução e comparação com metas.

---

## Como usar esta referência

Base local: `http://127.0.0.1:8000` (rodando `uvicorn API.main:app --reload` de dentro de `TG/`).
CORS está liberado (`*`), então qualquer origem consegue chamar durante o desenvolvimento.
Documentação interativa automática em `/docs`.

Todas as rotas são `GET`, sem autenticação. Todos os exemplos abaixo são respostas **reais**,
capturadas rodando a API contra o banco de verdade.

---

## Parâmetros de filtro compartilhados

`/resultados`, `/estatisticas` e `/comparacao-meta` aceitam os mesmos filtros (todos opcionais,
mas **pelo menos um é obrigatório** — sem filtro nenhum a rota devolve `400`):

| Parâmetro | Tipo | Exemplo | Observação |
|---|---|---|---|
| `nivel_ensino` | string | `anos_iniciais`, `anos_finais`, `ensino_medio` | |
| `abrangencia` | string | `escola`, `municipio`, `brasil` | quase sempre use `municipio` |
| `ano` | integer | `2023` | ciclo do IDEB (anos ímpares, bienal) |
| `sigla_uf` | string | `DF`, `CE` | |
| `codigo_municipio` | string | `5300108` | código IBGE de 7 dígitos |
| `codigo_escola` | string | | |
| `rede` | string | `Pública`, `Estadual`, `Municipal` | `Pública` é o agregado |

---

## `GET /municipios`

Lista municípios — pra popular um seletor/dropdown.

**Query params:** `sigla_uf` (opcional).

```
GET /municipios?sigla_uf=DF
```
```json
[
  { "codigo_municipio": "5300108", "nome_municipio": "Brasília", "sigla_uf": "DF" }
]
```

---

## `GET /resultados`

Linhas brutas do IDEB, sem processamento. Útil pra tabela detalhada; pra gráfico, prefira as
rotas abaixo.

```
GET /resultados?sigla_uf=DF&abrangencia=municipio&ano=2023
```
Devolve uma lista de objetos (uma linha do banco por item) com os campos: `id`, `abrangencia`,
`nivel_ensino`, `ano`, `rede`, `codigo_entidade`, `nome_entidade`, `sigla_uf`,
`codigo_municipio`, `codigo_escola`, `taxa_aprovacao_total`, `indicador_rendimento_p`,
`nota_saeb_matematica`, `nota_saeb_portugues`, `nota_saeb_media_padronizada_n`, `ideb`,
`meta_projetada`, `taxa_aprovacao_por_serie` (objeto ou `null`).

**Sem nenhum filtro:**
```
GET /resultados
```
```json
{ "detail": "Informe ao menos um filtro (ex.: sigla_uf, codigo_municipio, ano)." }
```
`HTTP 400`

---

## `GET /estatisticas`

Médias agregadas — pronto pra cards/gráfico de barra.

```
GET /estatisticas?sigla_uf=DF&abrangencia=municipio
```
```json
{
  "taxa_aprovacao_por_serie": {
    "1º": 97.51, "2º": 95.45, "3º": 83.62, "4º": 93.04, "5º": 92.06,
    "6º": 85.05, "7º": 85.14, "8º": 89.05, "9º": 85.8,
    "1ª série": 79.33, "2ª série": 85.1, "3ª série": 90.52
  },
  "saeb_matematica": 253.99,
  "saeb_portugues": 244.92,
  "saeb_nota_padronizada": 5.54,
  "aprovacao_geral": 87.53
}
```

- `taxa_aprovacao_por_serie` → direto num gráfico de **barra** (uma barra por série).
- Se você passar `codigo_municipio` no filtro, a resposta ganha mais um campo:
  `"media_municipio": 87.53` (taxa de aprovação média só daquele município).
- Filtro sem nenhum resultado → `HTTP 404` com `{"detail": "Nenhum registro encontrado..."}`.

---

## `GET /comparacao-meta`

IDEB observado vs. meta projetada do INEP.

```
GET /comparacao-meta?sigla_uf=DF&abrangencia=municipio
```
```json
{
  "resumo": { "total": 40, "atingiram_meta": 18, "nao_atingiram_meta": 22 },
  "detalhes": [
    {
      "codigo_municipio": "5300108",
      "rede": "Estadual",
      "ano": 2019,
      "ideb": 4.9,
      "meta_projetada": 5.2,
      "atingiu_meta": false,
      "diferenca": -0.3
    }
  ]
}
```

- `resumo` → KPI simples ou gráfico de pizza/donut (atingiram × não atingiram).
- `detalhes` → tabela ou gráfico de dispersão (um ponto por linha).
- Linhas sem `ideb` **ou** sem `meta_projetada` (dado ausente no banco) não entram em `detalhes`.

---

## `GET /evolucao`

Série histórica do IDEB médio por ano — pronto pra gráfico de **linha**.

**Query params:** `anos` (**obrigatório**, repetido — `anos=2019&anos=2021&anos=2023`) + os
mesmos filtros opcionais (`sigla_uf`, `codigo_municipio`, `nivel_ensino`, `abrangencia`,
`codigo_escola`, `rede` — mas sem `ano` singular, use `anos`).

```
GET /evolucao?anos=2017&anos=2019&anos=2021&anos=2023&sigla_uf=DF&abrangencia=municipio&codigo_municipio=5300108
```
```json
[
  { "ano": 2017, "ideb_medio": 5.0 },
  { "ano": 2019, "ideb_medio": 4.9 },
  { "ano": 2021, "ideb_medio": 5.26 },
  { "ano": 2023, "ideb_medio": 5.09 }
]
```
Já vem ordenado por ano — plote direto, `x = ano`, `y = ideb_medio`.

---

## `GET /baixar` (não é pro front-end)

Baixa uma planilha bruta do INEP pro disco do servidor e deixa o `.xlsx` pronto. É uma rotina
de ingestão interna, não devolve dado nenhum pra exibir — pode ignorar essa rota na hora de
montar as telas. As chaves válidas (IDEB e INSE) estão em `GET /planilhas`, que também diz o
`layout` de cada uma e se o `.zip`/`.xlsx` já está em disco.

---

## Resumo rápido — o que importar pra cada tela

| Tela / gráfico | Rota |
|---|---|
| Seletor de município | `GET /municipios?sigla_uf=` |
| Tabela de resultados brutos | `GET /resultados?...` |
| Gráfico de barra (aprovação por série) | `GET /estatisticas?...` → campo `taxa_aprovacao_por_serie` |
| Cards de SAEB / aprovação geral | `GET /estatisticas?...` → `saeb_matematica`, `saeb_portugues`, `saeb_nota_padronizada`, `aprovacao_geral` |
| KPI/pizza "quantos atingiram a meta" | `GET /comparacao-meta?...` → `resumo` |
| Tabela/dispersão IDEB × meta | `GET /comparacao-meta?...` → `detalhes` |
| Gráfico de linha (evolução temporal) | `GET /evolucao?anos=...` |
| Grupos de municípios (clusters) | `GET /modelos/agrupamento?nivel_ensino=` |

---

## Modelos — `GET /modelos/*`

O K-means de `Modelos/` (ver `Modelos/MODELOS.md`), calculado sob demanda e em cache por
(nível, ano). Só existe para os anos com INSE — hoje **2021 e 2023**; `GET /modelos/anos` diz
quais. `ano` é opcional: sem ele, vale o mais recente. `nivel_ensino` é obrigatório. `sigla_uf`
recorta só a lista `municipios`; os grupos, os `outliers` e o `total` são sempre nacionais.

**Primeira chamada de cada (nível, ano) demora ~1,5 s** (é o K-means rodando); as seguintes
respondem em ~20 ms.

### `GET /modelos/agrupamento?nivel_ensino=`

K-means com o `k` escolhido pela silhueta (2 nos dois níveis). Clusters numerados
por IDEB médio crescente (0 = pior desempenho).

```json
{
  "nivel_ensino": "anos_finais", "ano": 2023, "k": 2,
  "avaliacao": [ { "k": 2, "inercia": 11847.4, "silhueta": 0.3938 }, ... ],
  "perfil": [
    { "cluster": 0, "municipios": 2246, "media_inse": 4.49, "ideb": 4.1,
      "indicador_rendimento_p": 0.89, "nota_saeb_media_padronizada_n": 4.61 },
    { "cluster": 1, "municipios": 3135, "media_inse": 5.11, "ideb": 5.24,
      "indicador_rendimento_p": 0.96, "nota_saeb_media_padronizada_n": 5.44 }
  ],
  "outliers": [ "...os 5 municípios mais acima do IDEB médio de cada cluster, mesmas colunas de municipios" ],
  "total": 5381,
  "municipios": [
    { "cluster": 1, "codigo_municipio": "1100015", "nome_municipio": "Alta Floresta D'Oeste",
      "sigla_uf": "RO", "media_inse": 4.9904, "ideb": 4.7, "indicador_rendimento_p": 0.9317,
      "nota_saeb_media_padronizada_n": 5.0053, "acima_do_grupo": -0.54 }
  ]
}
```

- `perfil` → tabela/cards de cada grupo. `municipios` → dispersão colorida por `cluster`.
- `outliers` → "quem entrega mais dentro do seu grupo".
- `acima_do_grupo` = IDEB do município − IDEB médio do seu cluster. Positivo = acima do grupo.
