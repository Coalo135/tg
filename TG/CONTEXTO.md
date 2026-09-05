# Contexto do projeto — TG (IDEB)

> Briefing para retomar o projeto em qualquer conversa nova. Atualizado após a
> migração para SQLite e a importação da divulgação de 2025. Todos os números
> abaixo foram lidos do banco, não estimados.

---

## 1. O que é o projeto

Trabalho de Graduação: um **sistema de análise de dados do IDEB** (INEP/Brasil) com
dois módulos de Machine Learning:

1. **Clusterização** — agrupar municípios por perfil socioeconômico/pedagógico e
   identificar outliers positivos (Sobral/CE é o caso de referência da literatura).
   **Ainda não implementada.**
2. **Previsão (regressão)** — prever o IDEB de um município no próximo ciclo,
   comparar com a meta oficial do INEP, emitir veredito. **Implementada.**

Estudo de caso final: foco no Ceará (Sobral como destaque, Fortaleza como capital).
Escopo de dados: Brasil inteiro desde o início.

---

## 2. Arquitetura atual

```
TG/
├── config.py               Caminhos e constantes de todo o projeto
├── main.py                 Pipeline de demonstração (Brasília/DF)
├── Planilhas/
│   ├── *.zip               8 arquivos, versionados no git (60 MB)
│   └── *.xlsx              gerados por descompactar.py, fora do git (131 MB)
├── Dados/
│   ├── planilhas.py        Catálogo: nome, abrangência, nível
│   ├── descompactar.py     .zip -> .xlsx
│   └── consulta_ideb.py    Consultas e filtros sobre o SQLite
├── DataBase/
│   ├── conexao.py          Abertura única do banco (pragmas)
│   ├── schema.py           DDL do modelo estrela
│   ├── importData.py       ETL das planilhas
│   └── check_BD.py         52 verificações de integridade
├── Estatistica/  Exportacao/  Visualizacao/
├── API/          FastAPI: 11 rotas
├── ML/           dados -> dataset -> modelos -> validacao -> prever
└── tests/        47 testes
```

**Não existe mais `.env`.** O Supabase foi removido por completo: o banco é um
arquivo SQLite local, reconstruível a partir dos `.zip` do repositório.

---

## 3. Estado real do banco — lido por consulta direta

| Métrica | Valor |
|---|---|
| Total de linhas em `ideb_resultados` | **1.406.480** |
| Abrangência `escola` | 1.046.734 |
| Abrangência `municipio` | **355.720** ← unidade da regressão |
| Abrangência `regiao_uf` | 3.872 |
| Abrangência `brasil` | 154 |
| Nível `anos_iniciais` / `anos_finais` / `ensino_medio` | 698.830 / 552.012 / 155.638 |
| Cobertura temporal | **2005 → 2025**, bienal (11 ciclos) |
| `municipios` (dimensão) | 5.571 |
| `escolas` (dimensão) | 86.094 |
| `ideb` NULL geral | 20,1% (dominado pelo nível escola) |
| `ideb` NULL em município + rede Pública | **5,0%** |
| Tamanho do arquivo `.db` | ~557 MB (não versionado) |
| **INSE** | **não existe no schema** — falta coletar |

`regiao_uf` agora está carregada (antes eram 0 linhas). Cada município tem 3 valores
de `rede` por ciclo/nível: `Estadual`, `Municipal` e `Pública` (o agregado). A
regressão usa `rede = "Pública"`.

`ensino_medio` só existe a partir de 2017 — curto demais para a validação temporal,
por isso ficou de fora da regressão.

---

## 4. Módulo de regressão (`ML/`)

- **Unidade:** município, `rede = "Pública"` → 120.936 linhas na base.
- **Modelos separados por nível** (anos_iniciais / anos_finais).
- **Alvo:** IDEB no ciclo seguinte (T+1 = T + 2 anos).
- **Features (6):** `ideb_T`, `ideb_T_menos_1`, `variacao_ideb`, `rendimento_T`,
  `saeb_T`, `flag_pos_pandemia`.
- **Dataset:** 109.739 pares T→T+1, dos quais **89.893 usáveis** (18,1% descartados
  por ausência, majoritariamente o ciclo 2005 sem T−1).
- **Anti-vazamento:** toda feature usa só dado de ciclos ≤ T.
- **Ausências descartadas, não imputadas**, com o custo reportado.

### Resultados da validação temporal

Rodadas derivadas dos dados: `(2019→2021)`, `(2021→2023)`, `(2023→2025)`.

| Nível | Modelo vencedor | MAE | RMSE | vs baseline |
|---|---|---|---|---|
| anos_iniciais | regressão linear | 0,448 | 0,572 | +1,1% |
| anos_finais | regressão linear | 0,344 | 0,454 | **+12,5%** |

Random Forest não venceu em nenhum nível — a relação é majoritariamente linear.

Em `anos_iniciais` a vantagem sobre o baseline ingênuo ("o IDEB não muda") é de
apenas 1,1%: na prática, empate. Isso é resultado, não fracasso — é o "Plano B" do
design original. Vale notar que na rodada anterior (que ia só até 2023) o baseline
vencia nesse nível; a inclusão do ciclo 2025 inverteu a ordem por margem estreita.

### Exemplos de projeção para 2027

- Sobral/CE, anos_finais: IDEB 2025 = 8,0 → projeção 2027 = **7,80** (queda leve,
  bem acima da última meta oficial, 5,3 em 2021).
- Fortaleza/CE, anos_iniciais: IDEB 2025 = 6,1 → projeção 2027 = **6,37** (alta).
- Fortaleza/CE, anos_finais: IDEB 2025 = 5,2 → projeção 2027 = **5,30** (alta).

---

## 5. Bugs encontrados e corrigidos nesta migração

Todos pré-existentes, nenhum introduzido pela troca de banco:

1. **Catálogo apontava para `_2023`** enquanto os arquivos em disco eram `_2025`.
   Nenhuma planilha seria encontrada.
2. **`ML/prever.py` fixava `ULTIMO_CICLO = 2023`.** Com o 2025 no banco, projetaria
   2025 a partir de 2023 — prevendo um ciclo já ocorrido.
3. **Rodadas de validação fixas até 2023**, ignorando o ciclo mais recente.
4. **`/baixar` gravaria por cima dos `.zip` versionados** (mesmo nome do INEP).
   Agora baixa para `Planilhas/downloads/`.
5. **`/baixar` usava índice numérico posicional**, que apontava para outro arquivo
   sempre que a ordem do catálogo mudava. Agora usa chave nomeada.
6. **`sqLiteBD.py` criava um `.db` vazio no import**, na pasta de quem importasse.
7. **Caminhos absolutos do Windows hardcoded** (`C:\Users\cris2\...`) em dois módulos.
8. **`taxa_aprovacao_todas_series` quebrava com `NaN`**: testava `is None`, mas o
   pandas entrega `NaN` (float) para `NULL` de coluna TEXT. `AttributeError` em
   produção.
9. **Médias retornavam `numpy.float64`**, poluindo logs e complicando o JSON da API.
10. **`media_municipio` comparava código sem normalizar tipo** — um int devolveria
    `None` como se o município não tivesse dado.

---

## 6. O que falta

1. **Clusterização (K-means)** — não iniciada.
2. **Coletar INSE** — bloqueio da clusterização.
3. **Estudo de caso do Ceará** detalhado, cruzando com a literatura
   (Almeida e Vieira, 2019).
4. **Seções de texto do TG** (revisão de literatura, metodologia) — fora do escopo
   de código.

`ML/REGRESSAO.md` já foi atualizado: a §11 traz os resultados da base até 2025 e
compara explicitamente com a execução anterior, incluindo a inversão em
`anos_iniciais` e a explicação de por que o MAE subiu nos dois níveis.

---

## 7. Convenções seguidas

- Decisões de design **guiadas pelos dados reais**, não pré-definidas em teoria.
- Resultados "ruins" (baseline empatando) são tratados como achado válido.
- Ausência de dado nunca vira zero, em nenhuma camada.
- Nada de valor fixo no código para algo que o banco pode responder.
