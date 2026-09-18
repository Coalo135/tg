"""
importInse.py — ETL do INSE (Indicador de Nível Socioeconômico) para o SQLite.

O INSE resume, por município, a escolaridade dos pais e a posse de bens das
famílias dos alunos que fizeram o Saeb. É o dado que permite perguntar quanto do
IDEB vem da escola e quanto vem de onde o aluno nasceu.

Layout da planilha
------------------
Cabeçalho numa única linha, sem célula mesclada — nada do que `importData.py` faz
para o IDEB (cabeçalho de 4 linhas, ano vindo do rótulo do bloco) se aplica aqui,
por isso é um módulo à parte. Colunas, idênticas em 2021 e 2023:

    NU_ANO_SAEB, CO_UF, SG_UF, NO_UF, CO_MUNICIPIO, NO_MUNICIPIO,
    TP_TIPO_REDE, TP_LOCALIZACAO, TP_CAPITAL,
    QTD_ALUNOS_INSE, MEDIA_INSE, PC_NIVEL_1 ... PC_NIVEL_8

Três regras de limpeza, cada uma vinda de um achado medido nas planilhas:

1. `TP_TIPO_REDE = 0` é descartado. Nas 14.465 combinações (município, localização)
   em que 2023 traz os códigos 0 e 6, os valores são idênticos em todas — o 0, que
   não consta do dicionário, é cópia do 6. Importá-lo dobraria a rede pública em
   qualquer média.
2. `MEDIA_INSE = 0` vira NULL. Em 2021, 27.245 linhas (33%) trazem 0, todas com
   `QTD_ALUNOS_INSE = 0`: não houve aluno medido. Na escala do indicador (2,3 a
   6,5) um zero real é impossível — é ausência, e ausência nunca vira zero.
3. Linha sem nenhum indicador (média e os oito percentuais nulos) não é gravada,
   o mesmo critério que o importador do IDEB usa para não guardar linha vazia.
4. Percentual por nível vazio vira 0 quando há média. Em 2023, 44.711 linhas com
   média têm algum PC_NIVEL em branco; somando os oito com vazio = 0, o total dá
   100,00 em todas as 124.851 linhas medidas (mín 99,97, máx 100,03) — o INEP
   simplesmente não escreve o nível em que não há aluno. Aqui o vazio é um zero
   de verdade, e a soma é o que prova isso (`check_BD` confere a cada carga).
5. Linhas repetidas são gravadas uma vez. O arquivo de 2023 repete a mesma linha
   dezenas de vezes nas redes Estadual e Municipal — Sobral/Municipal/Urbana vem
   50 vezes, idêntica em todas as colunas (tudo indica uma linha por escola
   carregando o agregado do município). Das 125.741 linhas, só 57.111 são
   distintas. A chave única da tabela já impediria a duplicata; aqui ela é
   removida antes e contada no log, para o custo não ficar escondido no banco.

Uso: python -m DataBase.importInse   (ou como parte de `python -m DataBase.importData`)
"""
import logging
from collections import Counter

import pandas as pd

from Dados.descompactar import garantir_planilhas
from Dados.planilhas import por_layout
from DataBase.conexao import conectar
from DataBase.importData import codigo, gravar_municipios, numero, texto
from DataBase.schema import criar_schema

logger = logging.getLogger(__name__)

# TP_TIPO_REDE -> o vocabulário de `rede` de ideb_resultados, para o JOIN ser direto.
# O código 6 (Federal + Estadual + Municipal) é o que o IDEB chama de rede pública.
# O 5 exclui a federal e não tem equivalente no IDEB; ganha rótulo próprio para nunca
# casar por engano. O 4 não consta do dicionário do INEP: é a rede privada (em 2023
# vem sem INSE calculado). O 0 não está aqui de propósito — é a duplicata do 6.
REDES = {
    1: "Federal",
    2: "Estadual",
    3: "Municipal",
    4: "Privada",
    5: "Estadual+Municipal",
    6: "Pública",
}
LOCALIZACOES = {0: "Total", 1: "Urbana", 2: "Rural"}

NIVEIS = tuple(f"pc_nivel_{i}" for i in range(1, 9))

SQL_FATO = f"""
INSERT OR REPLACE INTO inse_municipios
    (ano, codigo_municipio, sigla_uf, rede, localizacao, capital,
     qtd_alunos, media_inse, {', '.join(NIVEIS)})
VALUES
    (:ano, :codigo_municipio, :sigla_uf, :rede, :localizacao, :capital,
     :qtd_alunos, :media_inse, {', '.join(':' + n for n in NIVEIS)})
"""


def _inteiro(valor):
    n = numero(valor)
    return None if n is None else int(n)


def montar_registros(df: pd.DataFrame) -> tuple[list[dict], Counter]:
    """Uma linha da planilha -> um dict pronto para o INSERT. Devolve também o que
    foi descartado e por quê — o custo da limpeza fica visível no log."""
    registros, descartes = [], Counter()

    repetidas = int(df.duplicated().sum())
    if repetidas:
        descartes["linhas repetidas, idênticas em todas as colunas"] = repetidas
        df = df.drop_duplicates()

    for linha in df.itertuples(index=False):
        cod_municipio = codigo(linha.CO_MUNICIPIO)
        if not cod_municipio:
            descartes["sem município (rodapé/linha vazia)"] += 1
            continue

        rede = REDES.get(_inteiro(linha.TP_TIPO_REDE))
        localizacao = LOCALIZACOES.get(_inteiro(linha.TP_LOCALIZACAO))
        if rede is None or localizacao is None:
            descartes["rede 0 (duplicata) ou código desconhecido"] += 1
            continue

        qtd_alunos = _inteiro(linha.QTD_ALUNOS_INSE)
        media = numero(linha.MEDIA_INSE)
        if media == 0:
            media = None
            qtd_alunos = qtd_alunos or None

        niveis = {n: numero(getattr(linha, n.upper())) for n in NIVEIS}
        if media is None and all(v is None for v in niveis.values()):
            descartes["sem nenhum indicador"] += 1
            continue
        if media is not None:
            niveis = {n: 0.0 if v is None else v for n, v in niveis.items()}

        registros.append({
            "ano": _inteiro(linha.NU_ANO_SAEB),
            "codigo_municipio": cod_municipio,
            "_nome_municipio": texto(linha.NO_MUNICIPIO),
            "sigla_uf": texto(linha.SG_UF),
            "rede": rede,
            "localizacao": localizacao,
            "capital": _inteiro(linha.TP_CAPITAL),
            "qtd_alunos": qtd_alunos,
            "media_inse": media,
            **niveis,
        })

    # Mesma chave com valores diferentes seria outro defeito, mais grave: não foi
    # visto nos dados, mas se aparecer, o INSERT OR REPLACE fica com a última e
    # isto deixa registrado.
    chaves = Counter((r["ano"], r["codigo_municipio"], r["rede"], r["localizacao"])
                     for r in registros)
    conflitos = sum(n - 1 for n in chaves.values() if n > 1)
    if conflitos:
        logger.warning("%d linhas com a mesma chave e valores diferentes; fica a última",
                       conflitos)
        descartes["mesma chave, valores diferentes (fica a última)"] = conflitos
    return registros, descartes


def gravar_fatos(conexao, registros) -> int:
    limpos = [{k: v for k, v in r.items() if not k.startswith("_")} for r in registros]
    conexao.executemany(SQL_FATO, limpos)
    return len(limpos)


def importar(conexao) -> int:
    """Carrega todas as planilhas de layout `inse` do catálogo. Devolve o total gravado."""
    total = 0
    for planilha in por_layout("inse"):
        if not planilha.xlsx.exists():
            logger.warning("[pulado] %s não encontrado", planilha.xlsx.name)
            continue

        df = pd.read_excel(planilha.xlsx, sheet_name=0, header=0, dtype=object)
        registros, descartes = montar_registros(df)

        # a dimensão antes do fato: a FK está ligada, e o INSE pode trazer município
        # que ainda não entrou pelo IDEB
        gravar_municipios(conexao, registros)
        n = gravar_fatos(conexao, registros)
        conexao.commit()
        total += n

        logger.info("%s: %d registros gravados de %d linhas", planilha.base, n, len(df))
        for motivo, quantos in descartes.most_common():
            logger.info("    descartadas %6d — %s", quantos, motivo)
    return total


def main():
    garantir_planilhas()
    with conectar() as conexao:
        criar_schema(conexao)
        total = importar(conexao)
        conexao.execute("PRAGMA optimize;")
    logger.info("Importação do INSE concluída: %d registros.", total)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
