# Módulo de Regressão — Previsão do IDEB municipal

> **Nota de atualização.** As seções 1–10 são o documento de design original, escrito
> com a base indo até **2023** e hospedada no Supabase; o raciocínio continua valendo
> integralmente. O banco passou a ser **SQLite local** e a divulgação de **2025** foi
> importada — a **§11 traz os resultados atuais** e compara com a execução anterior.
> Onde o texto abaixo cita anos fixos (2023, 2025), eles hoje são lidos do banco.

> Documento de design. Descreve **como** o modelo de previsão vai funcionar antes de escrever o
> código. Escopo: Brasil inteiro, unidade = município (rede pública). Baseado nos dados reais já
> ingeridos no banco (tabela `ideb_resultados`; à época, 2005–2023).

---

## 1. Objetivo

Dado o histórico de um município até o ciclo **T**, prever o **IDEB no ciclo seguinte T+1**.
Produto final: uma função que recebe um município e devolve a projeção para o próximo ciclo
(ex.: 2025), com um veredito simples — *"em trajetória de atingir a meta"* / *"abaixo da
trajetória"* — comparando a previsão com a meta projetada do INEP.

O IDEB é medido a cada **2 anos** (ciclos bienais). Portanto **T+1 = T + 2 anos**.

---

## 2. Dados de partida (já no banco)

Tabela `ideb_resultados` — formato longo, uma linha por (entidade, nível, ano, rede).

| Fato | Valor confirmado |
|------|------------------|
| Abrangência município | 319.700 linhas |
| Cobertura anos_iniciais / anos_finais | **2005 → 2023** (10 ciclos bienais) |
| Cobertura ensino_medio | **apenas 2017 → 2023** (4 ciclos) |
| Redes por município | `Estadual`, `Municipal`, **`Pública`** (agregado) |
| `ideb` NULL (participação insuficiente) | ~22% da base — tratados como ausência, **não** zero |

**Decisões derivadas dos dados:**
- **Unidade = município com `rede = "Pública"`** (o agregado, ~5.570 municípios/ciclo).
- **Modelar `anos_iniciais` e `anos_finais` separadamente.** São escalas e dinâmicas diferentes;
  um modelo por nível.
- **Ensino médio fica de fora do primeiro modelo** — só 4 ciclos não sustentam validação temporal
  decente. Entra depois, se sobrar tempo.

### Ciclos disponíveis (anos_iniciais / anos_finais)
```
2005  2007  2009  2011  2013  2015  2017  2019  2021  2023
```
→ 9 pares (T → T+1) possíveis por município.

---

## 3. Montagem do dataset de treino (a parte mais delicada)

Cada linha do dataset = **um município num ciclo T**, com:

- **Features** calculadas usando **somente informação de ciclos ≤ T** (nunca do futuro).
- **Alvo (`y`)** = `ideb` do mesmo município no ciclo **T+1**.

> ⚠️ **Regra de ouro anti-vazamento:** nenhuma feature pode usar dado de um ciclo posterior a T.
> A meta projetada para T+1 é a única exceção — ela é publicada *antes* do ciclo T+1 acontecer,
> então é informação legítima disponível em T.

### Features propostas (todas conhecidas em T)

| Feature | Origem |
|---------|--------|
| `ideb_T` | IDEB no ciclo T |
| `ideb_T_menos_1` | IDEB no ciclo anterior (T−1) |
| `variacao_ideb` | `ideb_T − ideb_T_menos_1` (tendência recente) |
| `rendimento_T` | `indicador_rendimento_p` em T |
| `saeb_T` | `nota_saeb_media_padronizada_n` em T |
| `flag_pos_pandemia` | 1 se T+1 ∈ {2021, 2023}, senão 0 |
| `nivel_ensino` | categórica — **modelos separados por nível** |
| ~~`meta_T_mais_1`~~ | **REMOVIDA das features** — ver nota abaixo |
| ~~`inse`~~ | **fora por ora** — INSE não está no banco (ver §7) |

> **Achado guiado pelos dados — a meta saiu das features.** O INEP só projetou metas até
> 2021: a `meta_projetada` de 2023 é **100% nula** e não existe meta para 2025. Usá-la como
> feature obrigatória zeraria a rodada de teste de 2023 (a mais importante) e impossibilitaria
> a projeção de 2025 — o produto final. A meta permanece na base **apenas para o veredito**
> (comparar a previsão com a última meta oficial), não como entrada do modelo.
>
> **Caveat da `flag_pos_pandemia` sob validação temporal.** A flag só tem sinal quando o treino
> inclui algum ciclo pós-pandemia. Na rodada que testa 2021 (treino ≤ 2019), a flag é sempre 0
> no treino e portanto inútil ali; ela só ajuda na rodada que testa 2023 (treino inclui 2021).

### Alvo
```
y = ideb  do município  no ciclo T+1
```

### Tratamento de ausências
- **Alvo NULL** (`ideb` em T+1 ausente) → a linha **não entra** no treino (não há o que prever/medir).
- **Feature NULL** (ex.: `ideb_T_menos_1` inexistente no primeiro ciclo, ou SAEB ausente) →
  decisão explícita: descartar a linha **ou** imputar. Começaremos **descartando** (mais honesto)
  e mediremos quantos % isso custa.
- Registrar o número de linhas descartadas — vira argumento no texto ("X% da base é ausência por
  participação insuficiente no SAEB").

### Tipos
Os valores vêm como **string** no banco (`"4.80"`, `"0.915826"`). Converter para `float` logo na
carga (`pd.to_numeric(..., errors="coerce")`, que já transforma vazios em `NaN`).

---

## 4. Validação temporal (crítico — nunca `shuffle`)

Validação aleatória vazaria futuro para o treino. Usamos **corte temporal**:

| Rodada | Treina com pares T→T+1 onde T+1 ≤ | Testa prevendo |
|--------|-----------------------------------|----------------|
| 1 | 2017 | **2019** |
| 2 | 2019 | **2021** |
| 3 | 2021 | **2023** |

Média das métricas nas 3 rodadas = desempenho reportado. `TimeSeriesSplit` do scikit-learn **não**
serve direto aqui (ele corta por índice, não por ano) — o corte é feito manualmente pelo ano de T+1.

---

## 5. Modelos (em ordem de complexidade)

1. **Baseline ingênuo** — `ideb_previsto(T+1) = ideb(T)`. Sem aprendizado. É o piso: **se um modelo
   não bate isso, ele não serve.** Banca respeita quem apresenta baseline.
2. **Regressão linear** (`LinearRegression`) sobre as features de §3.
3. **Random Forest** (`RandomForestRegressor`).

Todos do `scikit-learn`. Features numéricas padronizadas com `StandardScaler` quando fizer diferença
(linear sim; árvore é indiferente a escala).

---

## 6. Métricas

Reportadas em **pontos de IDEB** (a mesma escala 0–10 que a banca entende):

- **MAE** (erro absoluto médio) — "erro médio de 0,2 ponto".
- **RMSE** (penaliza erros grandes).

Comparar sempre **contra o baseline**. Um MAE de 0,25 só significa algo ao lado do MAE do baseline.

---

## 7. INSE (fora do escopo desta etapa)

O INSE (nível socioeconômico) **não está no banco** e é irregular entre anos. Conforme o plano:
- Fica **fora da regressão** por ora (evita buracos que derrubariam linhas).
- Será coletado e usado principalmente na **clusterização** (etapa seguinte), onde é essencial.
- Se depois vier com boa cobertura, entra como feature estática.

---

## 8. Produto final

```
prever_ideb(codigo_municipio, nivel_ensino) ->
    {
      "municipio": "...",
      "ultimo_ciclo": 2023,
      "ideb_2023": 5.2,
      "previsao_2025": 5.4,
      "meta_inep_2025": 5.7,
      "veredito": "abaixo da trajetória da meta",
      "modelo": "random_forest",
      "mae_validacao": 0.23
    }
```
+ gráfico: linha histórica do IDEB, ponto projetado destacado, meta do INEP marcada.

---

## 9. Estrutura de código proposta (`TG/ML/`)

```
TG/ML/
├── REGRESSAO.md              # este documento
├── dados.py                  # carrega ideb_resultados (rede=Pública), casta tipos, limpa
├── dataset.py                # monta pares T→T+1 sem vazamento (o coração)
├── modelos.py                # baseline, linear, random forest
├── validacao.py              # split temporal por ano + MAE/RMSE
└── prever.py                 # função-produto prever_ideb() + gráfico
```

Reaproveita o padrão de conexão já existente em
[Dados/consulta_ideb.py](../Dados/consulta_ideb.py) (paginação de 1000 + `create_client`).

---

## 10. Ordem de execução

1. `dados.py` — puxar município/rede=Pública, castar strings→float, salvar parquet local (cache).
2. `dataset.py` — gerar a matriz de pares T→T+1; **imprimir quantas linhas sobram e quantas caíram**.
3. `modelos.py` + `validacao.py` — rodar baseline → linear → RF nas 3 rodadas temporais.
4. Comparar MAE/RMSE numa tabela. Decidir o modelo oficial.
5. `prever.py` — empacotar a função-produto e o gráfico.

> **Plano B** (do plano original): se o Random Forest não superar o baseline, **não é fracasso** —
> é resultado. Reporta-se que a dinâmica do IDEB é bem capturada por modelos simples, e a
> **regressão linear vira o modelo oficial**.

---

## 11. Resultados obtidos

### 11.1 Execução atual (base 2005–2025)

Base real: **89.893 pares** usáveis de 109.739 (município/rede Pública), após descartar 18,1%
por ausência (quase tudo o ciclo 2005, que não tem T−1). Validação temporal, média de 3 rodadas
(treina ≤2019→testa 2021; ≤2021→testa 2023; ≤2023→testa 2025), MAE/RMSE em pontos de IDEB:

| Nível | Modelo | MAE | RMSE | Vencedor |
|-------|--------|-----|------|----------|
| **anos_iniciais** | regressão linear | **0,448** | 0,572 | 🏆 linear (+1,1% vs baseline) |
| anos_iniciais | baseline | 0,453 | 0,585 | |
| anos_iniciais | random forest | 0,462 | 0,587 | |
| **anos_finais** | regressão linear | **0,344** | 0,454 | 🏆 linear (+12,5% vs baseline) |
| anos_finais | random forest | 0,350 | 0,461 | |
| anos_finais | baseline | 0,393 | 0,519 | |

**Leitura:**

- **anos_iniciais** — a regressão linear passa à frente do baseline, mas por **1,1%**. Isso é um
  empate técnico, não uma vitória: a conclusão honesta continua sendo a do Plano B — a dinâmica
  do IDEB nos anos iniciais é essencialmente capturada pela hipótese ingênua "o IDEB não muda de
  um ciclo pro outro". Apresentar +1,1% como ganho do modelo seria superinterpretar ruído.
- **anos_finais** — a **regressão linear** reduz o erro em 12,5% sobre o baseline (MAE 0,344 ≈
  "erro médio de um terço de ponto de IDEB"). Aqui a vitória é real e se manteve entre as duas
  execuções.
- **Random Forest nunca venceu**, em nenhum nível nem em nenhuma das duas execuções. A relação é
  majoritariamente linear; não há padrão não-linear suficiente para ele explorar.
- `prever.py` seleciona automaticamente o modelo de menor MAE **por nível**, re-treina na base
  completa e projeta o ciclo seguinte (hoje, 2027).

**Exemplo de saída** (Sobral/CE, anos_finais): IDEB sobe de 3,3 (2005) → 8,0 (2025); projeção
2027 = **7,80**; muito acima da última meta oficial (5,3 em 2021). Gráficos em `ML/saidas/`.

### 11.2 Comparação com a execução anterior (base até 2023)

Vale registrar no texto do TG, porque uma conclusão mudou:

| Nível | Antes (até 2023) | Agora (até 2025) |
|---|---|---|
| anos_iniciais | 🏆 baseline, MAE 0,400 | 🏆 linear, MAE 0,448 (baseline 0,453) |
| anos_finais | 🏆 linear, MAE 0,330 (+12%) | 🏆 linear, MAE 0,344 (+12,5%) |

Duas observações:

1. **A ordem se inverteu em anos_iniciais**, por margem estreita. Não é uma descoberta nova sobre
   o fenômeno — é a diferença entre dois modelos que erram praticamente o mesmo tanto.
2. **O MAE subiu nos dois níveis** (0,400→0,448 e 0,330→0,344). Era esperado: a rodada mais antiga
   (testar 2019, o ciclo mais estável e pré-pandemia) saiu da média e entrou a de 2025, que exige
   prever a partir de um histórico atravessado pela pandemia. O erro maior reflete um problema
   mais difícil, não um modelo pior.

> Reprodutibilidade: `python -m ML.dados` → `python -m ML.dataset` → `python -m ML.validacao`
> → `python -m ML.prever`. Random Forest usa `random_state=42`; a pipeline é determinística.
