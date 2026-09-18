# Modelos — INSE × IDEB e clusterização de municípios

Decisões e resultados dos dois modelos construídos sobre o par INSE × IDEB.
Todos os números abaixo saíram de `python -m Modelos.relacao_inse_ideb` e
`python -m Modelos.agrupamento` rodando contra o banco real, em 2026-09-17.

---

## 1. O dado: par INSE × IDEB por município

O **INSE** (Indicador de Nível Socioeconômico, INEP/Saeb) resume, por município, a
escolaridade dos pais e a posse de bens das famílias dos alunos que fizeram o Saeb.
Escala contínua; nos dados vai de 2,3 a 6,5. Está no banco para **2021 e 2023**
(tabela `inse_municipios`; ver `DataBase/importInse.py` para as cinco regras de
limpeza e a evidência de cada uma).

Unidade de análise: **município, rede pública, todas as localizações** — no INSE,
`rede = 'Pública'` (código 6 do INEP: federal + estadual + municipal, a mesma
definição do IDEB) e `localizacao = 'Total'`. O IDEB entra por (ano, município, rede)
e por nível de ensino. Consulta em `Dados/consulta_inse.buscar_inse_ideb`.

Cobertura do par (municípios com INSE **e** IDEB no mesmo ano):

| Nível | 2021 | 2023 |
|---|---|---|
| anos iniciais | 5.072 (450 sem IDEB) | 5.429 (129 sem IDEB) |
| anos finais | 4.817 (705 sem IDEB) | 5.381 (177 sem IDEB) |
| ensino médio | 3.375 (2.147 sem IDEB) | 5.064 (494 sem IDEB) |

Nenhum município ficou sem INSE tendo IDEB. Quem não tem IDEB (participação
insuficiente no Saeb) sai da análise e é contado — nunca vira zero.

---

## 2. Modelo 1 — quanto do IDEB o nível socioeconômico explica

`Modelos/relacao_inse_ideb.py`. Para cada nível e ano: reta de mínimos quadrados
`IDEB ~ INSE`, Pearson, Spearman e R². Sem dependência além de pandas/numpy.

| Nível | Ano | n | Pearson | Spearman | R² | Reta |
|---|---|---|---|---|---|---|
| anos iniciais | 2021 | 5.072 | 0,63 | 0,67 | **0,39** | IDEB = 1,06·INSE + 0,42 |
| anos finais | 2021 | 4.817 | 0,55 | 0,57 | 0,30 | IDEB = 0,71·INSE + 1,40 |
| ensino médio | 2021 | 3.375 | 0,50 | 0,48 | 0,25 | IDEB = 0,63·INSE + 1,11 |
| anos iniciais | 2023 | 5.429 | 0,55 | 0,59 | **0,31** | IDEB = 1,08·INSE + 0,59 |
| anos finais | 2023 | 5.381 | 0,49 | 0,51 | 0,24 | IDEB = 0,75·INSE + 1,13 |
| ensino médio | 2023 | 5.064 | 0,39 | 0,38 | 0,15 | IDEB = 0,44·INSE + 2,02 |

**Leitura.** A relação é positiva e consistente, mas explica só de **15% a 39%** da
variância do IDEB municipal — a maior parte do que separa um município do outro
não é o perfil socioeconômico dos alunos. O efeito é mais forte nos anos iniciais
(um ponto de INSE vale ~1,1 ponto de IDEB) e enfraquece ao longo da trajetória
escolar; no ensino médio de 2023 quase some (R² = 0,15). Entre 2021 e 2023 a
correlação caiu em todos os níveis.

**O resíduo é o produto.** `residuo = IDEB observado − IDEB previsto pelo INSE`
(CSV em `saidas/residuos_<nivel>_<ano>.csv`, ordenado). Resíduo positivo alto é um
município que entrega mais do que o nível socioeconômico dos seus alunos faria
esperar — a definição operacional de "outlier positivo".

**Sanity check — Sobral/CE.** A literatura aponta Sobral como o caso de referência
de rede municipal que saiu de notas baixas para o topo nacional. No modelo:

| Nível | Ano | INSE | IDEB | previsto | resíduo | posição entre os resíduos |
|---|---|---|---|---|---|---|
| anos iniciais | 2023 | 4,37 | 9,6 | 5,31 | **+4,29** | 11º de 5.429 |
| anos finais | 2023 | 4,37 | 7,9 | 4,41 | **+3,49** | 8º de 5.381 |
| anos iniciais | 2021 | 4,36 | — | — | +2,93 | 23º de 5.072 |
| anos finais | 2021 | 4,36 | — | — | +2,09 | 17º de 4.817 |

Com INSE abaixo da média nacional, Sobral está entre os 11 maiores resíduos do
país. Os demais no topo são quase todos do Ceará e de Alagoas (Pires Ferreira/CE,
Santana do Mundaú/AL, Coreaú/CE, Ibateguara/AL, União dos Palmares/AL) — o padrão
regional que a literatura descreve aparece nos dados sem que nada o induza.

---

## 3. Modelo 2 — clusterização de municípios (K-means)

`Modelos/agrupamento.py`. Ano mais recente com INSE (2023), anos iniciais e finais.
Features padronizadas (`StandardScaler`): `media_inse`, `ideb`,
`indicador_rendimento_p`, `nota_saeb_media_padronizada_n`. Para cada k de 2 a 8,
inércia (cotovelo) e silhueta; fica o k de maior silhueta. Clusters renumerados por
IDEB médio crescente.

**A silhueta escolhe k = 2 nos dois níveis** (0,43 nos anos iniciais, 0,39 nos
finais; qualquer k maior cai para ~0,30). Os municípios brasileiros não formam
grupos separados nessas quatro dimensões: formam um contínuo, e a melhor partição
é "metade de baixo / metade de cima". Isso é resultado, não defeito do método.

Perfil dos clusters, anos iniciais 2023 (médias):

| cluster | municípios | INSE | IDEB | rendimento | SAEB | resíduo médio |
|---|---|---|---|---|---|---|
| 0 (baixo) | 2.176 | 4,45 | 4,93 | 0,95 | 5,18 | −0,47 |
| 1 (alto) | 3.253 | 5,12 | 6,42 | 0,98 | 6,52 | +0,31 |

Anos finais 2023: 2.246 municípios no cluster baixo (INSE 4,49, IDEB 4,10) e 3.135
no alto (INSE 5,11, IDEB 5,24).

**Outliers positivos por cluster** (maior resíduo do modelo 1 dentro de cada grupo):

- *Cluster alto, anos iniciais:* Pires Ferreira/CE (+4,92), Santana do Mundaú/AL
  (+4,75), Coreaú/CE (+4,63), Ibateguara/AL (+4,61), União dos Palmares/AL (+4,46).
- *Cluster baixo, anos iniciais:* Joaquim Pires/PI (+1,29), Chã Preta/AL (+1,28),
  Monte Formoso/MG (+1,25), Serrano do Maranhão/MA (+1,12), Senador Rui
  Palmeira/AL (+1,10) — municípios pequenos do interior que, dentro de um grupo de
  baixo desempenho, estão bem acima do que o INSE preveria.
- **Sobral/CE** cai no cluster alto nos dois níveis, mesmo com INSE de 4,37 (abaixo
  da média do cluster baixo): é o desempenho, não a renda, que o coloca lá.
  **Fortaleza/CE**, a capital, fica no mesmo cluster com resíduo pequeno (+0,48 e
  +0,64) — desempenho compatível com o esperado para o seu INSE.

**Limitação do desenho.** Três das quatro features medem desempenho (IDEB,
rendimento, SAEB); o agrupamento acaba separando por desempenho, e o INSE pesa
menos. Uma variante que agrupasse por INSE e resíduo — "quem é parecido em renda e
quem entrega mais dentro disso" — separaria o perfil socioeconômico da entrega
escolar de forma mais direta. Fica como próximo passo.

---

## 4. O que estes resultados não dizem

- **Correlação, não causa.** O INSE explica parte do IDEB; nada aqui diz que
  mudar um muda o outro.
- **Dois cortes no tempo.** INSE existe para 2021 e 2023. O IDEB de 2025 não tem
  INSE para cruzar, e 2019 tem outro layout e escala não comparável (o INEP avisa).
  Cada modelo é um corte transversal por ano — não há série temporal.
- **Nível município, rede pública.** Escolas não entraram (o INSE por escola existe
  e não foi importado), nem a rede privada (o INSE de 2023 não calcula média para ela).
- **O resíduo herda o ruído do IDEB.** Município pequeno tem IDEB volátil; um
  resíduo alto num único ano pede confirmação no outro.

---

## 5. Como rodar

```bash
python -m DataBase.importData          # banco inteiro (IDEB + INSE), ~4 min
python -m DataBase.importInse          # só o INSE, ~30 s
python -m DataBase.check_BD            # 69 verificações; a §11 é do INSE
python -m Modelos.relacao_inse_ideb    # modelo 1: tabela + 6 PNG + 6 CSV, ~3 s
python -m Modelos.agrupamento          # modelo 2: perfis + outliers + 2 PNG, ~5 s
```

Saídas em `Modelos/saidas/` (fora do git; reproduzíveis).
