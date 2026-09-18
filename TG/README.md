# TG — Pipeline de dados do IDEB

Trabalho de Graduação: pipeline de dados do **IDEB** (Índice de Desenvolvimento da
Educação Básica / INEP) com banco **SQLite local**, estatísticas descritivas,
exportação, gráficos e dois modelos sobre o cruzamento com o **INSE** (Indicador de
Nível Socioeconômico): a relação INSE × IDEB e a clusterização de municípios.

Cobertura atual do banco: IDEB de **2005 a 2025**, bienal, nos quatro níveis de
abrangência (Brasil, região/UF, município, escola); INSE de **2021 e 2023**, por
município.

---

## Início rápido

```bash
cd TG
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # execução
pip install -r requirements-dev.txt      # + pytest e ruff

python -m DataBase.importData            # descompacta as planilhas e monta o banco (IDEB + INSE)
python -m DataBase.check_BD              # 69 verificações de integridade
python main.py                           # pipeline de demonstração (Brasília/DF)
python -m Modelos.relacao_inse_ideb      # modelo 1: relação INSE × IDEB
python -m Modelos.agrupamento            # modelo 2: clusterização de municípios
```

Não há `.env` nem credenciais: o banco é um arquivo local.

---

## Como as planilhas são versionadas

As 10 planilhas (8 do IDEB, 2 do INSE) somam **149 MB** em `.xlsx`. Versioná-las
direto é ruim para o git: são binárias, e cada nova divulgação do INEP grava outros
tantos MB no histórico.

Zipar o `.xlsx` não resolve — ele **já é** um zip deflate por dentro, e recomprimir
economiza 0,3%. O que funciona é extrair as partes OOXML de dentro dele (os XML
crus) e recomprimir tudo com LZMA:

| Estratégia | Tamanho |
|---|---|
| 8 `.xlsx` do IDEB | 131 MB |
| re-zipar os `.xlsx` direto | 130 MB (−0,3%) |
| **`.zip` LZMA das partes OOXML** | **60 MB (−55%)** |
| 2 `.xlsx` do INSE → `.zip` LZMA | 18 MB → **6 MB (−65%)** |

Então o que fica no git é um `.zip` por planilha; o `.xlsx` é gerado localmente e
está no `.gitignore`. `python -m Dados.descompactar` reconstrói todos, e
`python -m Dados.compactar` faz o caminho inverso quando uma planilha nova entra
(confere o round-trip byte a byte antes de aceitar o `.zip`).

O descompactador também aceita o formato que o INEP entrega (um `.zip` com o
`.xlsx` dentro), então serve tanto para o repositório quanto para um download novo.

**Download direto do INEP.** `download.inep.gov.br` envia o certificado sem o
intermediário que o assina, e todo cliente com verificação ligada recusa a
conexão. `Dados/inep_download.py` resolve fornecendo o intermediário (versionado
em `Dados/certs/`), sem desligar a verificação — é o que a rota `GET /baixar` e o
comando `python -m Dados.inep_download <chave>` usam.

---

## Como rodar cada parte

Todos os comandos assumem `cd TG` e o venv ativo.

| Parte | Comando |
|---|---|
| Baixar uma planilha do INEP | `python -m Dados.inep_download <chave>` |
| Descompactar planilhas | `python -m Dados.descompactar` |
| Compactar planilha nova para o git | `python -m Dados.compactar` |
| Importar para o banco (IDEB + INSE) | `python -m DataBase.importData` |
| Reimportar só o INSE | `python -m DataBase.importInse` |
| Checkup de integridade | `python -m DataBase.check_BD` |
| Pipeline de demonstração | `python main.py` |
| Modelo 1 — relação INSE × IDEB | `python -m Modelos.relacao_inse_ideb` |
| Modelo 2 — clusterização | `python -m Modelos.agrupamento` |
| API | `uvicorn API.main:app --reload` (docs em `/docs`) |
| Testes | `pytest` |
| Lint | `ruff check .` |

**Convenção de imports:** todos os módulos usam import absoluto a partir da raiz
do projeto (`from Dados.consulta_ideb import ...`) e são executados com `python -m`.

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
| `GET /modelos/anos` | Anos com INSE — os únicos em que os modelos existem |
| `GET /modelos/relacao-inse-ideb?nivel_ensino=` | Modelo 1: reta IDEB ~ INSE e o resíduo de cada município, ranqueado |
| `GET /modelos/agrupamento?nivel_ensino=` | Modelo 2: clusters (K-means), perfil de cada um e outliers |
| `GET /modelos/municipio/{codigo}?nivel_ensino=` | A "previsão" de um município: observado, previsto pelo INSE, resíduo, posição, cluster |
| `GET /planilhas` | Catálogo (IDEB e INSE) e o que já está em disco |
| `GET /baixar?chave=inse_municipios_2023` | Baixa uma planilha do INEP e deixa o `.xlsx` pronto |

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
| `Dados/planilhas.py` | Catálogo das 10 planilhas: nome, abrangência, nível, URL, layout |
| `Dados/inep_download.py` | Download do INEP com a cadeia de certificados completa |
| `Dados/descompactar.py` | Reconstrói os `.xlsx` a partir dos `.zip` |
| `Dados/compactar.py` | Gera o `.zip` LZMA versionado a partir do `.xlsx` |
| `Dados/consulta_ideb.py` | Consultas e filtros sobre o IDEB |
| `Dados/consulta_inse.py` | Consultas sobre o INSE e o par INSE × IDEB |
| `DataBase/conexao.py` | Abertura única do banco, com os pragmas corretos |
| `DataBase/schema.py` | DDL: modelo estrela (fatos + dimensões) |
| `DataBase/importData.py` | ETL das planilhas do IDEB (e chama o do INSE) |
| `DataBase/importInse.py` | ETL da planilha do INSE, com as regras de limpeza documentadas |
| `DataBase/check_BD.py` | 69 verificações de integridade (só leitura) |
| `Estatistica/` | Cálculos sobre um DataFrame já filtrado |
| `Exportacao/` | CSV, deixando ausências explícitas |
| `Visualizacao/` | `GeradorGrafico`: linha, barra, dispersão por quadrante e dispersão com ajuste |
| `Modelos/` | Modelo 1 (relação INSE × IDEB, resíduos) e modelo 2 (K-means); ver `Modelos/MODELOS.md` |

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

**Nada de ciclo fixo no código.** O último ciclo, os anos dos gráficos e os anos dos
modelos são lidos do banco, não de uma lista fixa: quando o INEP divulga um ciclo
novo, ele aparece sozinho.

**No INSE, o zero do INEP é ausência.** Em 2021, um terço das linhas traz
`MEDIA_INSE = 0` com zero alunos medidos; na escala do indicador (2,3 a 6,5) um zero
real é impossível. Vira `NULL`. Já o percentual por nível em branco é 0% de verdade:
somando os oito com vazio = 0, dá 100,00 em todas as linhas medidas. As regras e a
evidência de cada uma estão em `DataBase/importInse.py`.

**O arquivo do INSE de 2023 repete linhas.** A mesma linha aparece dezenas de vezes
nas redes estadual e municipal (Sobral/Municipal/Urbana vem 50 vezes, idêntica). Só
57 mil das 126 mil linhas são distintas; o importador remove e conta.

---

## Migração do Supabase (concluída)

O projeto usava Supabase/PostgREST. O que mudou:

- `Dados/consulta_ideb.py` reescrito para SQLite.
- `API/bd_connection.py` removido (era só CRUD de exemplo do Supabase).
- **A paginação de 1000 em 1000 sumiu** — era o `db-max-rows` do PostgREST, um
  limite da camada HTTP, não do banco.
- `supabase` e `python-dotenv` saíram do `requirements.txt`.

---

## Pendências conhecidas

- **Estudo de caso do Ceará** aprofundado ainda não escrito — o modelo 1 já mostra
  Sobral entre os 11 maiores resíduos positivos do país (`Modelos/MODELOS.md`).
- **INSE por escola** existe no INEP e não foi importado; só o de município entrou.
- **Clusterização por INSE + resíduo** (em vez de INSE + desempenho) separaria
  melhor perfil socioeconômico de entrega escolar; ver `Modelos/MODELOS.md` §3.
- **Nomes de pastas misturam português e inglês** e usam PascalCase em vez de
  `snake_case`. Renomear tocaria todos os imports; deixado como está de propósito.
