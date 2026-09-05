# TG — Pipeline de dados e ML do IDEB

Trabalho de Graduação: pipeline de dados do **IDEB** (Índice de Desenvolvimento da
Educação Básica / INEP) com banco **SQLite local**, estatísticas descritivas,
exportação, gráficos e um módulo de regressão (scikit-learn) que projeta o IDEB de
um município para o próximo ciclo.

Cobertura atual do banco: **2005 a 2025**, bienal, nos quatro níveis de abrangência
(Brasil, região/UF, município, escola).

---

## Início rápido

```bash
cd TG
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # execução
pip install -r requirements-dev.txt      # + pytest e ruff

python -m DataBase.importData            # descompacta as planilhas e monta o banco
python -m DataBase.check_BD              # 52 verificações de integridade
python main.py                           # pipeline de demonstração (Brasília/DF)
```

Não há `.env` nem credenciais: o banco é um arquivo local.

---

## Como as planilhas são versionadas

Os 8 `.xlsx` de divulgação somam **131 MB**. Versioná-los direto é ruim para o git:
são binários, e cada nova divulgação do INEP grava outros 131 MB no histórico.

Zipar o `.xlsx` não resolve — ele **já é** um zip deflate por dentro, e recomprimir
economiza 0,3%. O que funciona é extrair as partes OOXML de dentro dele (os XML
crus) e recomprimir tudo com LZMA:

| Estratégia | Tamanho |
|---|---|
| 8 `.xlsx` originais | 131 MB |
| re-zipar os `.xlsx` direto | 130 MB (−0,3%) |
| **`.zip` LZMA das partes OOXML** | **60 MB (−55%)** |

Então o que fica no git é um `.zip` por planilha; o `.xlsx` é gerado localmente e
está no `.gitignore`. `python -m Dados.descompactar` reconstrói todos.

O mesmo comando também aceita o formato que o INEP entrega (um `.zip` com o
`.xlsx` dentro), então serve tanto para o repositório quanto para um download novo.

---

## Como rodar cada parte

Todos os comandos assumem `cd TG` e o venv ativo.

| Parte | Comando |
|---|---|
| Descompactar planilhas | `python -m Dados.descompactar` |
| Importar para o banco | `python -m DataBase.importData` |
| Checkup de integridade | `python -m DataBase.check_BD` |
| Pipeline de demonstração | `python main.py` |
| API | `uvicorn API.main:app --reload` (docs em `/docs`) |
| ML — carga | `python -m ML.dados` |
| ML — dataset de pares | `python -m ML.dataset` |
| ML — validação temporal | `python -m ML.validacao` |
| ML — previsão | `python -m ML.prever` |
| Testes | `pytest` |
| Lint | `ruff check .` |

**Convenção de imports:** todos os módulos usam import absoluto a partir da raiz
do projeto (`from Dados.consulta_ideb import ...`) e são executados com `python -m`.
Antes, os módulos de `ML/` usavam import de irmão (`from dados import ...`) para
rodar com `cd ML && python dados.py`, o que exigia um remendo de `sys.path` em
`ML/__init__.py` e outro em `tests/test_ml.py`. Os dois remendos foram removidos.

---

## Rotas da API

| Rota | Para quê |
|---|---|
| `GET /ufs` | Siglas de UF no banco |
| `GET /municipios?sigla_uf=` | Municípios (seletor) |
| `GET /escolas?codigo_municipio=&sigla_uf=` | Escolas; exige um dos dois filtros |
| `GET /anos?...` | Anos com dado para o filtro — evita oferecer ano vazio |
| `GET /resultados?...` | Linhas brutas do IDEB |
| `GET /estatisticas?...` | Médias agregadas, prontas para gráfico |
| `GET /comparacao-meta?...` | IDEB observado vs. meta do INEP (`resumo` + `detalhes`) |
| `GET /evolucao?anos=2019&anos=2021...` | Série histórica do IDEB médio |
| `GET /previsao/{codigo_municipio}?nivel=` | Projeção do próximo ciclo |
| `GET /planilhas` | Catálogo e o que já está em disco |
| `GET /baixar?chave=brasil_ideb` | Baixa uma planilha do INEP |

`/resultados`, `/estatisticas` e `/comparacao-meta` compartilham os filtros
`nivel_ensino`, `abrangencia`, `ano`, `sigla_uf`, `codigo_municipio`,
`codigo_escola`, `rede`. **Ao menos um é obrigatório**: sem filtro, a consulta
devolveria as ~1,3 milhão de linhas da tabela inteira.

O CORS está aberto (`*`) por ser projeto acadêmico sem front-end em produção.

---

## Mapa dos módulos

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Caminhos e constantes compartilhados (raiz de tudo) |
| `Dados/planilhas.py` | Catálogo das 8 planilhas: nome, abrangência, nível |
| `Dados/descompactar.py` | Reconstrói os `.xlsx` a partir dos `.zip` |
| `Dados/consulta_ideb.py` | Consultas e filtros sobre o SQLite |
| `DataBase/conexao.py` | Abertura única do banco, com os pragmas corretos |
| `DataBase/schema.py` | DDL: modelo estrela (fato + dimensões) |
| `DataBase/importData.py` | ETL das planilhas para o banco |
| `DataBase/check_BD.py` | 52 verificações de integridade (só leitura) |
| `Estatistica/` | Cálculos sobre um DataFrame já filtrado |
| `Exportacao/` | CSV, deixando ausências explícitas |
| `Visualizacao/` | `GeradorGrafico`: linha, barra e dispersão por quadrante |
| `ML/` | Regressão: carga → pares T→T+1 → modelos → validação → previsão |

---

## Decisões que valem registro

**Ausência nunca vira zero.** Município com participação insuficiente no SAEB não
recebe IDEB, e o INEP não projetou metas depois de 2021. Esses casos ficam como
`NULL` no banco e `NaN` no DataFrame; na exportação viram o texto
`"sem dado suficiente"`, e a linha permanece. Tratar como zero inventaria uma nota
que não existe; omitir a linha esconderia que o dado foi coletado e é insuficiente.

**O ano de cada coluna vem do rótulo do bloco, não do código técnico.** Na planilha
de regiões/UFs há uma coluna do bloco de 2025 com o código `VL_INDICADOR_REND_2023`
— erro de origem do INEP. O código da linha 10 identifica só o *tipo* do indicador.

**Nada de ciclo fixo no código.** O último ciclo, as rodadas de validação e os anos
dos gráficos são lidos do banco. Havia um `ULTIMO_CICLO = 2023` que, com o 2025 já
importado, faria o modelo "prever" um ciclo que já aconteceu.

**A meta do INEP não é feature do modelo.** É 100% nula em 2023 e não existe depois.
Como feature obrigatória, zeraria a rodada de teste e impediria a projeção — que é o
produto final. Fica só como referência para o veredito.

---

## Migração do Supabase (concluída)

O projeto usava Supabase/PostgREST. O que mudou:

- `Dados/consulta_ideb.py` e `ML/dados.py` reescritos para SQLite.
- `API/bd_connection.py` removido (era só CRUD de exemplo do Supabase).
- **A paginação de 1000 em 1000 sumiu** — era o `db-max-rows` do PostgREST, um
  limite da camada HTTP, não do banco.
- **O download bloco a bloco do ML sumiu** — existia para driblar o statement
  timeout do Postgres numa tabela de 1,27 M linhas. Em SQLite é um `SELECT` só.
- `supabase` e `python-dotenv` saíram do `requirements.txt`.

---

## Pendências conhecidas

- **Clusterização (K-means)** não implementada; depende do INSE.
- **INSE não está no banco** — é o bloqueio da clusterização.
- **Estudo de caso do Ceará** aprofundado ainda não escrito (`ML/prever.py` já usa
  Sobral e Fortaleza como sanity check).
- **Nomes de pastas misturam português e inglês** e usam PascalCase em vez de
  `snake_case`. Renomear tocaria todos os imports; deixado como está de propósito.
