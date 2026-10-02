"""
agrupamento.py — Clusterização de municípios (K-means).

Agrupa os municípios da rede pública por perfil — nível socioeconômico dos alunos,
IDEB, rendimento (aprovação) e desempenho (SAEB) — e procura, dentro de cada grupo,
quem fica mais acima do IDEB médio do próprio grupo (`acima_do_grupo`). Sobral/CE é
o caso da literatura e serve de sanity check: deveria aparecer entre os mais altos
do seu cluster.

O número de grupos não é cravado: para cada k de 2 a 8 o script reporta inércia
(cotovelo) e silhueta, e usa o k de maior silhueta.

    python -m Modelos.agrupamento
"""
import logging

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from config import PASTA_MODELOS
from Exportacao.exportar import exportar_para_csv
from Modelos.dados import FORTALEZA, SOBRAL, anos_disponiveis, carregar_pares
from Visualizacao.gerador_grafico import GeradorGrafico

logger = logging.getLogger(__name__)

FEATURES = ("media_inse", "ideb", "indicador_rendimento_p", "nota_saeb_media_padronizada_n")
KS = range(2, 9)
SEMENTE = 0


def padronizar(df: pd.DataFrame, features=FEATURES) -> np.ndarray:
    """Média 0 e desvio 1 por coluna: INSE (~2–6), IDEB (0–10) e rendimento (0–1)
    não podem pesar diferente só por causa da escala."""
    return StandardScaler().fit_transform(df[list(features)].astype(float))


def avaliar_k(matriz: np.ndarray, ks=KS) -> pd.DataFrame:
    """Inércia e silhueta para cada k. A silhueta usa uma amostra: é O(n²)."""
    amostra = min(len(matriz), 3000)
    linhas = []
    for k in ks:
        modelo = KMeans(n_clusters=k, n_init=10, random_state=SEMENTE).fit(matriz)
        linhas.append({
            "k": k,
            "inercia": round(float(modelo.inertia_), 1),
            "silhueta": round(float(silhouette_score(
                matriz, modelo.labels_, sample_size=amostra, random_state=SEMENTE)), 4),
        })
    return pd.DataFrame(linhas)


def escolher_k(avaliacao: pd.DataFrame) -> int:
    return int(avaliacao.loc[avaliacao["silhueta"].idxmax(), "k"])


def agrupar(df: pd.DataFrame, k: int, features=FEATURES) -> pd.DataFrame:
    """Acrescenta a coluna `cluster`, com os grupos renumerados por IDEB médio crescente
    para o rótulo ter leitura (0 = pior desempenho, k−1 = melhor), e `acima_do_grupo`:
    o IDEB do município menos o IDEB médio do seu cluster."""
    matriz = padronizar(df, features)
    rotulos = KMeans(n_clusters=k, n_init=10, random_state=SEMENTE).fit_predict(matriz)
    saida = df.copy()
    saida["cluster"] = rotulos
    ordem = saida.groupby("cluster")["ideb"].mean().sort_values().index
    saida["cluster"] = saida["cluster"].map({antigo: novo for novo, antigo in enumerate(ordem)})
    media_grupo = saida.groupby("cluster")["ideb"].transform("mean")
    saida["acima_do_grupo"] = (saida["ideb"] - media_grupo).round(2)
    return saida


def perfil_clusters(df: pd.DataFrame, features=FEATURES) -> pd.DataFrame:
    perfil = df.groupby("cluster")[list(features)].mean().round(2)
    perfil.insert(0, "municipios", df.groupby("cluster").size())
    return perfil


def outliers_por_cluster(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Os n municípios mais acima do IDEB médio dentro de cada cluster."""
    return (df.sort_values("acima_do_grupo", ascending=False)
              .groupby("cluster").head(n)
              .sort_values(["cluster", "acima_do_grupo"], ascending=[True, False]))


def calcular(nivel_ensino: str, ano: int) -> dict | None:
    """Agrupamento completo, sem gravar nada — o que a API e o CLI compartilham."""
    pares, descartes = carregar_pares(nivel_ensino, ano=ano)
    pares = pares.dropna(subset=list(FEATURES)).reset_index(drop=True)
    if len(pares) < max(KS) * 5:
        logger.warning("%s/%d: sem base para agrupar (%d municípios)",
                       nivel_ensino, ano, len(pares))
        return None

    avaliacao = avaliar_k(padronizar(pares))
    k = escolher_k(avaliacao)
    agrupado = agrupar(pares, k)
    return {
        "nivel_ensino": nivel_ensino, "ano": ano, "k": k, "descartes": descartes,
        "avaliacao": avaliacao, "perfil": perfil_clusters(agrupado),
        "outliers": outliers_por_cluster(agrupado), "municipios": agrupado,
    }


def executar(nivel_ensino: str, ano: int) -> dict | None:
    resultado = calcular(nivel_ensino, ano)
    if resultado is None:
        return None
    k, descartes, avaliacao = resultado["k"], resultado["descartes"], resultado["avaliacao"]
    agrupado, perfil, outliers = (resultado["municipios"], resultado["perfil"],
                                  resultado["outliers"])

    sufixo = f"{nivel_ensino}_{ano}"
    exportar_para_csv(agrupado.sort_values(["cluster", "acima_do_grupo"], ascending=[True, False]),
                      PASTA_MODELOS / f"clusters_{sufixo}.csv")
    referencia = agrupado[agrupado["codigo_municipio"].isin([SOBRAL, FORTALEZA])]
    referencia = referencia.assign(
        rotulo=referencia["nome_municipio"] + "/" + referencia["sigla_uf"])
    png = GeradorGrafico(PASTA_MODELOS).dispersao(
        agrupado, "media_inse", "ideb", cor_por="cluster", destaques=referencia,
        rotulo_x="INSE médio dos alunos (rede pública)",
        rotulo_y=f"IDEB {nivel_ensino.replace('_', ' ')}",
        titulo=f"Clusters de municípios — {nivel_ensino.replace('_', ' ')}, {ano}  (k = {k})",
        nome_arquivo=f"clusters_{sufixo}.png",
    )

    print(f"\n=== {nivel_ensino} / {ano}: {len(agrupado)} municípios, descartados {descartes}")
    print("\nEscolha de k (cotovelo e silhueta):")
    print(avaliacao.to_string(index=False))
    print(f"\nk escolhido pela silhueta: {k}\n\nPerfil dos clusters (médias):")
    print(perfil.to_string())
    print(f"\nOutliers positivos por cluster (top {5}, IDEB acima da média do cluster):")
    colunas = ["cluster", "nome_municipio", "sigla_uf", "media_inse", "ideb",
               "acima_do_grupo"]
    print(outliers[colunas].to_string(index=False))
    if not referencia.empty:
        print("\nReferências da literatura:")
        print(referencia[colunas].to_string(index=False))
    print(f"\nGráfico: {png}")
    return resultado


def main():
    ano = max(anos_disponiveis())
    return [executar(nivel, ano) for nivel in ("anos_iniciais", "anos_finais")]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
