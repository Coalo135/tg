"""
Testes dos modelos: funções puras sobre DataFrames sintéticos, sem banco.
"""
import numpy as np
import pandas as pd
import pytest

from Modelos.agrupamento import agrupar, escolher_k, padronizar
from Modelos.dados import separar_completos
from Modelos.relacao_inse_ideb import ajustar_reta, calcular_residuos, destaques


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


# --------------------------------------------------------------- modelo 1

def test_ajuste_recupera_uma_relacao_linear_exata():
    ajuste = ajustar_reta(_pares(ruido=0.0))
    assert ajuste["inclinacao"] == pytest.approx(1.5, abs=1e-3)
    assert ajuste["intercepto"] == pytest.approx(-2.0, abs=1e-3)
    assert ajuste["r2"] == pytest.approx(1.0, abs=1e-6)
    assert ajuste["pearson"] == pytest.approx(1.0, abs=1e-6)
    assert isinstance(ajuste["r2"], float) and not isinstance(ajuste["r2"], np.floating)


def test_ajuste_com_ruido_tem_r2_menor_que_um():
    ajuste = ajustar_reta(_pares(ruido=0.5))
    assert 0.5 < ajuste["r2"] < 1.0
    assert ajuste["n"] == 50


def test_ajuste_ignora_pares_incompletos_e_exige_minimo():
    df = _pares(n=5)
    df.loc[0, "ideb"] = None
    assert ajustar_reta(df)["n"] == 4
    with pytest.raises(ValueError):
        ajustar_reta(df.head(2))


def test_residuo_positivo_e_ideb_acima_do_previsto():
    df = pd.DataFrame({"media_inse": [4.0, 4.0], "ideb": [6.0, 3.0]})
    com = calcular_residuos(df, inclinacao=1.0, intercepto=0.5)
    assert list(com["ideb_previsto"]) == [4.5, 4.5]
    assert list(com["residuo"]) == [1.5, -1.5]


def test_destaques_traz_os_extremos_com_rotulo():
    df = calcular_residuos(_pares(ruido=0.5), 1.5, -2.0)
    ext = destaques(df, n=3)
    assert len(ext) == 6
    assert ext["residuo"].iloc[0] == df["residuo"].max()
    assert ext["residuo"].iloc[-1] == df["residuo"].min()
    assert ext["rotulo"].iloc[0].endswith("/CE")


# --------------------------------------------------------------- modelo 2

def test_padronizar_deixa_media_zero_e_desvio_um():
    matriz = padronizar(_pares(ruido=0.3))
    assert np.allclose(matriz.mean(axis=0), 0, atol=1e-9)
    assert np.allclose(matriz.std(axis=0), 1, atol=1e-9)


def test_escolher_k_pega_a_maior_silhueta():
    avaliacao = pd.DataFrame({"k": [2, 3, 4], "silhueta": [0.4, 0.7, 0.5], "inercia": [9, 5, 3]})
    assert escolher_k(avaliacao) == 3


def test_agrupar_renumera_clusters_por_ideb_crescente():
    df = calcular_residuos(_pares(n=90, ruido=0.2), 1.5, -2.0)
    agrupado = agrupar(df, k=3)
    medias = agrupado.groupby("cluster")["ideb"].mean()
    assert list(medias.index) == [0, 1, 2]
    assert medias.is_monotonic_increasing
