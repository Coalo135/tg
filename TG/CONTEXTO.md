# Contexto do projeto — TG (IDEB)

> Briefing para retomar o projeto em qualquer conversa nova. Atualizado após a
> entrada do INSE no banco e a construção dos dois modelos (2026-09-17). Todos os
> números abaixo foram lidos do banco, não estimados.

---

## 1. O que é o projeto

Trabalho de Graduação: um **sistema de análise de dados do IDEB** (INEP/Brasil).

A base de dados, as estatísticas, a exportação, os gráficos e a API estão prontos.
Sobre eles são construídos **dois modelos** (ver §4):

1. **Relação INSE × IDEB** — quanto do desempenho de um município é explicado pelo
   nível socioeconômico dos seus alunos.
2. **Clusterização de municípios** — agrupar por perfil e identificar os outliers
   positivos, que entregam IDEB acima do que o INSE preveria.

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
│   ├── relacao_inse_ideb.py  Modelo 1: correlação, reta, R², resíduos
│   ├── agrupamento.py      Modelo 2: K-means, k por silhueta, outliers por cluster
│   └── MODELOS.md          Decisões e resultados
├── API/          FastAPI: 10 rotas
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

Dois modelos sobre o par INSE × IDEB por município (rede pública). Detalhes,
tabelas completas e limitações em `Modelos/MODELOS.md`.

1. **Relação INSE × IDEB** (`Modelos/relacao_inse_ideb.py`) — reta de mínimos
   quadrados, Pearson, Spearman e R² por nível e ano. **O INSE explica de 15% a 39%
   da variância do IDEB municipal** (R² de 0,39 nos anos iniciais de 2021 a 0,15 no
   ensino médio de 2023); o efeito enfraquece ao longo da trajetória escolar e caiu
   de 2021 para 2023. O produto é o **resíduo** (observado − previsto): a definição
   operacional de outlier positivo. **Sobral/CE tem o 11º maior resíduo do país**
   nos anos iniciais de 2023 (+4,29) e o 8º nos anos finais (+3,49), com INSE abaixo
   da média; o topo é dominado por municípios do Ceará e de Alagoas.
2. **Clusterização de municípios** (`Modelos/agrupamento.py`) — K-means sobre INSE,
   IDEB, rendimento e SAEB padronizados. **A silhueta escolhe k = 2** (0,43 e 0,39):
   os municípios formam um contínuo, não grupos separados. Sobral cai no cluster alto
   apesar do INSE baixo; Fortaleza fica no mesmo cluster com resíduo pequeno.
   Limitação: três das quatro features medem desempenho, então o corte é por
   desempenho — agrupar por INSE + resíduo é o próximo passo.

Regras que valem para os dois: nenhum ano fixo no código (vem do banco); ausência
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
   (Almeida e Vieira, 2019) — o modelo 1 já dá o dado central (Sobral no top 11).
2. **Clusterização por INSE + resíduo**, para separar perfil socioeconômico de
   entrega escolar (hoje o corte é por desempenho).
3. **INSE por escola** — existe no INEP, não foi importado.
4. **Seções de texto do TG** (revisão de literatura, metodologia) — fora do escopo
   de código.

---

## 7. Convenções seguidas

- Decisões de design **guiadas pelos dados reais**, não pré-definidas em teoria.
- Resultado fraco (correlação baixa, cluster sem separação) é achado válido.
- Ausência de dado nunca vira zero, em nenhuma camada.
- Nada de valor fixo no código para algo que o banco pode responder.
