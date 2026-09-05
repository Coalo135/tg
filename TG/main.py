"""
main.py — Demonstração do pipeline completo sobre o banco local.

Consulta -> estatísticas -> exportação -> gráficos, usando Brasília/DF como
exemplo. É o roteiro que o texto do TG descreve, executável de uma vez:

    python main.py

Pré-requisito: o banco precisa existir. Se não existir, rode antes
`python -m DataBase.importData` (que descompacta as planilhas e carrega tudo).
"""
import logging
import sys

from config import PASTA_EXPORTACAO
from Dados.consulta_ideb import anos_disponiveis, buscar_evolucao_ideb, buscar_resultados
from DataBase.conexao import BancoNaoEncontrado
from Estatistica.separacao_valores import comparar_meta_ideb, evolucao_ideb, valor_medias
from Exportacao.exportar import exportar_para_csv
from Visualizacao.gerador_grafico import GeradorGrafico

logger = logging.getLogger(__name__)

MUNICIPIO_DF = "5300108"  # Brasília
UF = "DF"


def main() -> None:
    df = buscar_resultados(sigla_uf=UF, abrangencia="municipio")
    if df.empty:
        logger.error("Nenhum dado para %s. O banco foi importado?", UF)
        return

    logger.info("%d registros carregados para %s.", len(df), UF)

    # Médias: taxa de aprovação por série, SAEB, aprovação geral, município
    medias = valor_medias(df, MUNICIPIO_DF)
    for valor in medias:
        logger.info(valor)

    # IDEB observado vs meta projetada, linha a linha
    comparacoes = comparar_meta_ideb(df)
    atingiram = sum(1 for c in comparacoes if c["atingiu_meta"])
    logger.info("%d/%d registros atingiram a meta projetada", atingiram, len(comparacoes))

    # Evolução temporal do IDEB em Brasília/DF.
    # Os anos vêm do banco em vez de uma lista fixa no código: quando o INEP
    # divulga um ciclo novo, o gráfico passa a incluí-lo sozinho.
    anos = anos_disponiveis(abrangencia="municipio", codigo_municipio=MUNICIPIO_DF)
    serie_por_ano = buscar_evolucao_ideb(
        anos, sigla_uf=UF, abrangencia="municipio", codigo_municipio=MUNICIPIO_DF,
    )
    evolucao = evolucao_ideb(serie_por_ano)
    logger.info("Evolução do IDEB: %s", evolucao)

    # Exportação — dados ausentes ficam explícitos, não somem
    caminho_csv = exportar_para_csv(df, PASTA_EXPORTACAO / "df_resultados.csv")
    logger.info("CSV exportado em: %s", caminho_csv)

    # Gráficos
    grafico = GeradorGrafico()
    caminho_linha = grafico.linha_evolucao_temporal(
        evolucao, titulo="Evolução do IDEB — Brasília/DF"
    )
    caminho_barra = grafico.barra_comparacao(
        medias[0], titulo="Taxa de aprovação por série — DF", eixo_y="%"
    )
    caminho_heatmap = grafico.heatmap_rendimento_desempenho(
        df, titulo="Rendimento x Desempenho — DF"
    )
    logger.info("Gráfico de evolução: %s", caminho_linha)
    logger.info("Gráfico de barras: %s", caminho_barra)
    logger.info("Gráfico de dispersão: %s", caminho_heatmap)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        main()
    except BancoNaoEncontrado as erro:
        logger.error("%s", erro)
        sys.exit(1)
