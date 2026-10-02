"""
Testes dos modelos: funções puras sobre DataFrames sintéticos, sem banco.
"""
import numpy as np
import pandas as pd

from Modelos.agrupamento import agrupar, escolher_k, outliers_por_cluster, padronizar
from Modelos.dados import separar_completos


def _pares(n=50, ruido=0.0, semente=0):
    rng = np.random.default_rng(semente)
    inse = rng.uniform(3, 6, n)
    ideb = 1.5 * inse - 2 + rng.normal(0, ruido, n)
    return pd.DataFrame({
        "codigo_municipio": [f"{i:07d}" for i in range(n)],
        "nome_municipio": [f"M{i}" for i in range(n)],
        "sigla_uf": "CE",
        "media_inse": inse, "ideb": ideb,
        "indicador_rendimento_p": rng.uniform(0.7, 1.0, n),
        "nota_saeb_media_padronizada_n": ideb + rng.normal(0, 0.1, n),
    })


# ------------------------------------------------------------------ dados

def test_separar_completos_conta_o_que_saiu():
    df = pd.DataFrame({"media_inse": [4.0, None, 5.0, None],
                       "ideb": [5.0, 6.0, None, None]})
    completos, descartes = separar_completos(df)
    assert len(completos) == 1
    assert descartes == {"sem INSE": 1, "sem IDEB": 1, "sem os dois": 1}


# ------------------------------------------------------------ agrupamento

def test_padronizar_deixa_media_zero_e_desvio_um():
    matriz = padronizar(_pares(ruido=0.3))
    assert np.allclose(matriz.mean(axis=0), 0, atol=1e-9)
    assert np.allclose(matriz.std(axis=0), 1, atol=1e-9)


def test_escolher_k_pega_a_maior_silhueta():
    avaliacao = pd.DataFrame({"k": [2, 3, 4], "silhueta": [0.4, 0.7, 0.5], "inercia": [9, 5, 3]})
    assert escolher_k(avaliacao) == 3


def test_agrupar_renumera_clusters_por_ideb_crescente():
    agrupado = agrupar(_pares(n=90, ruido=0.2), k=3)
    medias = agrupado.groupby("cluster")["ideb"].mean()
    assert list(medias.index) == [0, 1, 2]
    assert medias.is_monotonic_increasing


def test_acima_do_grupo_e_o_ideb_menos_a_media_do_cluster():
    agrupado = agrupar(_pares(n=90, ruido=0.2), k=3)
    esperado = agrupado["ideb"] - agrupado.groupby("cluster")["ideb"].transform("mean")
    assert np.allclose(agrupado["acima_do_grupo"], esperado, atol=0.006)
    assert np.allclose(agrupado.groupby("cluster")["acima_do_grupo"].mean(), 0, atol=0.01)


def test_outliers_traz_os_n_mais_acima_de_cada_grupo():
    df = pd.DataFrame({"cluster": [0, 0, 0, 1, 1], "acima_do_grupo": [0.5, 2.0, -1.0, 0.1, 3.0]})
    outliers = outliers_por_cluster(df, n=2)
    assert list(outliers["cluster"]) == [0, 0, 1, 1]
    assert list(outliers["acima_do_grupo"]) == [2.0, 0.5, 3.0, 0.1]
