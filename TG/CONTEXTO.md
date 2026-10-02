# Contexto do projeto — TG (IDEB)

> Briefing para retomar o projeto em qualquer conversa nova. Atualizado após a
> entrada do INSE no banco e a construção do K-means (2026-10-02). Todos os
> números abaixo foram lidos do banco, não estimados.

---

## 1. O que é o projeto

Trabalho de Graduação: um **sistema de análise de dados do IDEB** (INEP/Brasil).

A base de dados, as estatísticas, a exportação, os gráficos e a API estão prontos.
Sobre eles é construída a **clusterização de municípios** (ver §4): agrupar por
perfil e identificar os outliers positivos, que entregam IDEB acima da média do
próprio grupo.

Estudo de caso final: foco no Ceará (Sobral como destaque, Fortaleza como capital).
Escopo de dados: Brasil inteiro desde o início.

---

## 2. Arquitetura atual

```
TG/
├── config.py               Caminhos e constantes de todo o projeto
├── main.py                 Pipeline de demonstração (Brasília/DF)
├── Planilhas/
│   ├── *.zip               10 arquivos (8 IDEB + 2 INSE), versionados no git (66 MB)
│   └── *.xlsx              gerados por descompactar.py, fora do git (149 MB)
├── Dados/
│   ├── planilhas.py        Catálogo: nome, abrangência, nível, URL, layout (ideb|inse)
│   ├── inep_download.py    Download do INEP com o intermediário de certs/ (TLS)
│   ├── descompactar.py     .zip -> .xlsx
│   ├── compactar.py        .xlsx -> .zip LZMA (round-trip conferido byte a byte)
│   ├── consulta_ideb.py    Consultas sobre o IDEB
│   └── consulta_inse.py    Consultas sobre o INSE e o par INSE × IDEB
├── DataBase/
│   ├── conexao.py          Abertura única do banco (pragmas)
│   ├── schema.py           DDL do modelo estrela (+ inse_municipios)
│   ├── importData.py       ETL do IDEB; chama o do INSE no fim
│   ├── importInse.py       ETL do INSE, com as 5 regras de limpeza e a evidência
│   └── check_BD.py         69 verificações de integridade (§11 é do INSE)
├── Estatistica/  Exportacao/  Visualizacao/
├── Modelos/
│   ├── dados.py            Par INSE × IDEB pronto para modelar (conta o descarte)
│   ├── agrupamento.py      K-means, k por silhueta, outliers por cluster
│   └── MODELOS.md          Decisões e resultados
├── API/          FastAPI: 8 rotas
└── tests/        66 testes
```

**Não existe mais `.env`.** O Supabase foi removido por completo: o banco é um
arquivo SQLite local, reconstruível a partir dos `.zip` do repositório.

---

## 3. Estado real do banco — lido por consulta direta

| Métrica | Valor |
|---|---|
| Total de linhas em `ideb_resultados` | **1.406.480** |
| Abrangência `escola` | 1.046.734 |
| Abrangência `municipio` | **355.720** |
| Abrangência `regiao_uf` | 3.872 |
| Abrangência `brasil` | 154 |
| Nível `anos_iniciais` / `anos_finais` / `ensino_medio` | 698.830 / 552.012 / 155.638 |
| Cobertura temporal | **2005 → 2025**, bienal (11 ciclos) |
| `municipios` (dimensão) | 5.571 |
| `escolas` (dimensão) | 86.094 |
| `ideb` NULL geral | 20,1% (dominado pelo nível escola) |
| `ideb` NULL em município + rede Pública | **5,0%** |
| Tamanho do arquivo `.db` | ~560 MB (não versionado) |
| **`inse_municipios`** | **112.696** linhas: 57.111 de 2023 e 55.585 de 2021 |
| Municípios com INSE (rede pública) | 5.558 em 2023, 5.522 em 2021 |
| Par INSE × IDEB (pública, anos iniciais) | 5.429 municípios em 2023 (98%), 5.072 em 2021 (92%) |

`regiao_uf` agora está carregada (antes eram 0 linhas). Cada município tem 3 valores
de `rede` por ciclo/nível: `Estadual`, `Municipal` e `Pública` (o agregado).

`ensino_medio` só existe a partir de 2017 — série curta, o que limita qualquer
análise temporal nesse nível.

O INSE vem das planilhas `INSE_{2021,2023}_municipios.xlsx` do INEP (layout de uma
linha de cabeçalho; 2019 tem outro layout e escala não comparável, ficou de fora).
Três defeitos dos arquivos, medidos e tratados em `importInse.py`: o código de rede
0 é cópia do 6; `MEDIA_INSE = 0` é ausência (33% das linhas de 2021); o arquivo de
2023 repete a mesma linha dezenas de vezes (só 57 mil de 126 mil são distintas).

---

## 4. Modelos (`Modelos/`)

Um modelo sobre o par INSE × IDEB por município (rede pública). Detalhes,
tabelas completas e limitações em `Modelos/MODELOS.md`.

**Clusterização de municípios** (`Modelos/agrupamento.py`) — K-means sobre INSE,
IDEB, rendimento e SAEB padronizados. **A silhueta escolhe k = 2** (0,43 e 0,39):
os municípios formam um contínuo, não grupos separados. Outlier positivo é quem
fica mais acima do IDEB médio do próprio cluster (`acima_do_grupo`). Sobral cai no
cluster alto apesar do INSE baixo e fica +3,18 acima do grupo nos anos iniciais de
2023; Fortaleza fica no mesmo cluster, praticamente na média. O topo é dominado por
municípios do Ceará e de Alagoas. Limitação: três das quatro features medem
desempenho, então o corte é por desempenho.

Regras: nenhum ano fixo no código (vem do banco); ausência
nunca vira zero; resultado fraco é achado válido, não bug a maquiar.

---

## 5. Bugs encontrados e corrigidos nesta migração

Todos pré-existentes, nenhum introduzido pela troca de banco:

1. **Catálogo apontava para `_2023`** enquanto os arquivos em disco eram `_2025`.
   Nenhuma planilha seria encontrada.
2. **`/baixar` gravaria por cima dos `.zip` versionados** (mesmo nome do INEP).
   Agora baixa para `Planilhas/downloads/`.
3. **`/baixar` usava índice numérico posicional**, que apontava para outro arquivo
   sempre que a ordem do catálogo mudava. Agora usa chave nomeada.
4. **`sqLiteBD.py` criava um `.db` vazio no import**, na pasta de quem importasse.
5. **Caminhos absolutos do Windows hardcoded** (`C:\Users\cris2\...`) em dois módulos.
6. **`taxa_aprovacao_todas_series` quebrava com `NaN`**: testava `is None`, mas o
   pandas entrega `NaN` (float) para `NULL` de coluna TEXT. `AttributeError` em
   produção.
7. **Médias retornavam `numpy.float64`**, poluindo logs e complicando o JSON da API.
8. **`media_municipio` comparava código sem normalizar tipo** — um int devolveria
    `None` como se o município não tivesse dado.

---

## 6. O que falta

1. **Estudo de caso do Ceará** detalhado, cruzando com a literatura
   (Almeida e Vieira, 2019) — o K-means já dá o dado central (Sobral bem acima do
   seu grupo).
2. **INSE por escola** — existe no INEP, não foi importado.
3. **Seções de texto do TG** (revisão de literatura, metodologia) — fora do escopo
   de código.

---

## 7. Convenções seguidas

- Decisões de design **guiadas pelos dados reais**, não pré-definidas em teoria.
- Resultado fraco (correlação baixa, cluster sem separação) é achado válido.
- Ausência de dado nunca vira zero, em nenhuma camada.
- Nada de valor fixo no código para algo que o banco pode responder.
