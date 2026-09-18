"""
relacao_inse_ideb.py — Modelo 1: quanto do IDEB o nível socioeconômico explica.

Para cada nível de ensino e ano com INSE, ajusta uma reta IDEB ~ INSE sobre os
municípios da rede pública e mede a força da relação (Pearson, Spearman, R²).

O produto que interessa não é a reta, é o **resíduo**: IDEB observado menos o IDEB
que o INSE preveria. Resíduo positivo alto é um município que entrega mais do que
o perfil socioeconômico dos seus alunos faria esperar — a definição operacional de
"outlier positivo" que o modelo 2 vai procurar dentro de cada cluster.

Uma correlação fraca aqui é resultado, não defeito: diria que o IDEB municipal
depende pouco de onde o aluno nasceu.

    python -m Modelos.relacao_inse_ideb
"""
import logging

import numpy as np
import pandas as pd

from config import NIVEIS_ENSINO, PASTA_MODELOS
from Exportacao.exportar import exportar_para_csv
from Modelos.dados import SOBRAL, anos_disponiveis, carregar_pares
from Visualizacao.gerador_grafico import GeradorGrafico

logger = logging.getLogger(__name__)

X, Y = "media_inse", "ideb"


def ajustar_reta(df: pd.DataFrame, x: str = X, y: str = Y) -> dict:
    """Mínimos quadrados de y sobre x, mais as correlações. Tudo em float nativo."""
    dados = df[[x, y]].dropna().astype(float)
    if len(dados) < 3:
        raise ValueError(f"{len(dados)} pares não bastam para ajustar uma reta")

    inclinacao, intercepto = np.polyfit(dados[x], dados[y], deg=1)
    previsto = inclinacao * dados[x] + intercepto
    ss_res = float(((dados[y] - previsto) ** 2).sum())
    ss_tot = float(((dados[y] - dados[y].mean()) ** 2).sum())

    return {
        "n": int(len(dados)),
        "pearson": round(float(dados[x].corr(dados[y], method="pearson")), 4),
        "spearman": round(float(dados[x].corr(dados[y], method="spearman")), 4),
        "inclinacao": round(float(inclinacao), 4),
        "intercepto": round(float(intercepto), 4),
        "r2": round(1 - ss_res / ss_tot, 4) if ss_tot else 0.0,
    }


def calcular_residuos(df: pd.DataFrame, inclinacao: float, intercepto: float,
                      x: str = X, y: str = Y) -> pd.DataFrame:
    """Acrescenta `ideb_previsto` e `residuo` (observado − previsto)."""
    saida = df.copy()
    saida["ideb_previsto"] = (inclinacao * saida[x] + intercepto).round(2)
    saida["residuo"] = (saida[y] - saida["ideb_previsto"]).round(2)
    return saida


def destaques(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Os n maiores resíduos positivos e os n mais negativos, com rótulo para o gráfico."""
    ordenado = df.sort_values("residuo", ascending=False)
    extremos = pd.concat([ordenado.head(n), ordenado.tail(n)])
    extremos = extremos.assign(rotulo=extremos["nome_municipio"] + "/" + extremos["sigla_uf"])
    return extremos


def executar(nivel_ensino: str, ano: int, grafico: GeradorGrafico | None = None) -> dict | None:
    """Roda o modelo para um nível/ano; grava CSV de resíduos e PNG; devolve o ajuste."""
    pares, descartes = carregar_pares(nivel_ensino, ano=ano)
    if len(pares) < 3:
        logger.warning("%s/%d: sem base (%d pares)", nivel_ensino, ano, len(pares))
        return None

    ajuste = ajustar_reta(pares)
    com_residuo = calcular_residuos(pares, ajuste["inclinacao"], ajuste["intercepto"])
    extremos = destaques(com_residuo)

    sufixo = f"{nivel_ensino}_{ano}"
    csv = exportar_para_csv(
        com_residuo.sort_values("residuo", ascending=False),
        PASTA_MODELOS / f"residuos_{sufixo}.csv",
    )
    png = (grafico or GeradorGrafico(PASTA_MODELOS)).dispersao(
        com_residuo, X, Y,
        reta=(ajuste["inclinacao"], ajuste["intercepto"]),
        destaques=extremos,
        rotulo_x="INSE médio dos alunos (rede pública)",
        rotulo_y=f"IDEB {nivel_ensino.replace('_', ' ')}",
        titulo=f"INSE × IDEB por município — {nivel_ensino.replace('_', ' ')}, {ano}  "
               f"(r = {ajuste['pearson']:.2f}, R² = {ajuste['r2']:.2f}, n = {ajuste['n']})",
        nome_arquivo=f"relacao_inse_ideb_{sufixo}.png",
    )

    sobral = com_residuo[com_residuo["codigo_municipio"] == SOBRAL]
    posicao_sobral = None
    if not sobral.empty:
        posicao_sobral = int((com_residuo["residuo"] > float(sobral["residuo"].iloc[0])).sum()) + 1

    return {
        "nivel_ensino": nivel_ensino, "ano": ano, **ajuste,
        "descartes": descartes, "csv": csv, "png": png,
        "sobral_residuo": None if sobral.empty else float(sobral["residuo"].iloc[0]),
        "sobral_posicao": posicao_sobral,
    }


def main() -> list[dict]:
    grafico = GeradorGrafico(PASTA_MODELOS)
    resultados = []
    for ano in anos_disponiveis():
        for nivel in NIVEIS_ENSINO:
            r = executar(nivel, ano, grafico)
            if r:
                resultados.append(r)

    tabela = pd.DataFrame(resultados)[
        ["nivel_ensino", "ano", "n", "pearson", "spearman", "r2", "inclinacao", "intercepto",
         "sobral_residuo", "sobral_posicao"]
    ]
    print("\n" + tabela.to_string(index=False))
    print(f"\nSaídas em {PASTA_MODELOS}")
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
