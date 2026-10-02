# Modelos — clusterização de municípios sobre o par INSE × IDEB

Decisões e resultados do modelo construído sobre o par INSE × IDEB.
Todos os números abaixo saíram de `python -m Modelos.agrupamento` rodando contra o
banco real, em 2026-10-02.

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

## 2. Clusterização de municípios (K-means)

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

| cluster | municípios | INSE | IDEB | rendimento | SAEB |
|---|---|---|---|---|---|
| 0 (baixo) | 2.176 | 4,45 | 4,93 | 0,95 | 5,18 |
| 1 (alto) | 3.253 | 5,12 | 6,42 | 0,98 | 6,52 |

Anos finais 2023: 2.246 municípios no cluster baixo (INSE 4,49, IDEB 4,10) e 3.135
no alto (INSE 5,11, IDEB 5,24).

**Outliers positivos por cluster.** `acima_do_grupo = IDEB do município − IDEB
médio do seu cluster`; os 5 maiores de cada grupo:

- *Cluster alto, anos iniciais:* Pires Ferreira/CE (+3,58), Santana do Mundaú/AL
  (+3,38), Coruripe/AL, Jijoca de Jericoacoara/CE e União dos Palmares/AL (+3,28).
- *Cluster baixo, anos iniciais:* Parnaguá/PI (+1,27), Damião/PB, Jacaré dos
  Homens/AL, Amontada/CE e Paramoti/CE (+1,17) — municípios pequenos do interior
  que estão bem acima do resto de um grupo de baixo desempenho.
- *Anos finais:* Santana do Mundaú/AL (+4,06) e Pires Ferreira/CE (+3,96) lideram o
  cluster alto; Chã Preta/AL (+1,00) lidera o baixo.
- **Sobral/CE** cai no cluster alto nos dois níveis, mesmo com INSE de 4,37 (abaixo
  da média do cluster baixo): é o desempenho, não a renda, que o coloca lá. Fica
  +3,18 acima do grupo nos anos iniciais e +2,66 nos finais. **Fortaleza/CE**, a
  capital, fica no mesmo cluster praticamente na média (−0,42 e −0,04).

O topo é dominado por municípios do Ceará e de Alagoas — o padrão regional que a
literatura descreve aparece nos dados sem que nada o induza.

**Limitação do desenho.** Três das quatro features medem desempenho (IDEB,
rendimento, SAEB); o agrupamento acaba separando por desempenho, e o INSE pesa
menos. O `acima_do_grupo` compara o município com quem tem desempenho parecido,
não com quem tem renda parecida.

---

## 3. O que estes resultados não dizem

- **Agrupamento, não causa.** Estar num grupo não diz por que o município está lá.
- **Dois cortes no tempo.** INSE existe para 2021 e 2023. O IDEB de 2025 não tem
  INSE para cruzar, e 2019 tem outro layout e escala não comparável (o INEP avisa).
  O modelo é um corte transversal por ano — não há série temporal.
- **Nível município, rede pública.** Escolas não entraram (o INSE por escola existe
  e não foi importado), nem a rede privada (o INSE de 2023 não calcula média para ela).
- **O `acima_do_grupo` herda o ruído do IDEB.** Município pequeno tem IDEB volátil;
  um valor alto num único ano pede confirmação no outro.

---

## 4. Como rodar

```bash
python -m DataBase.importData          # banco inteiro (IDEB + INSE), ~4 min
python -m DataBase.importInse          # só o INSE, ~30 s
python -m DataBase.check_BD            # 69 verificações; a §11 é do INSE
python -m Modelos.agrupamento          # perfis + outliers + 2 PNG, ~5 s
```

Saídas em `Modelos/saidas/` (fora do git; reproduzíveis).
