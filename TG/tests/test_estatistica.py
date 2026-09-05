"""
Testes de Estatistica.separacao_valores — funções puras, sem banco nem rede.

A seção final cobre os três bugs encontrados quando estes cálculos passaram a
receber dados vindos do SQLite em vez do JSON do Supabase. São testes de
regressão: cada um falha se a correção for desfeita.
"""
import json

import numpy as np
import pandas as pd

from Estatistica.separacao_valores import (
    aprovacao_geral_media,
    comparar_meta_ideb,
    evolucao_ideb,
    media_municipio,
    saeb_media_matematica,
    saeb_media_nota_padronizada,
    saeb_media_portugues,
    taxa_aprovacao,
    taxa_aprovacao_todas_series,
    valor_medias,
)


def _linha(**overrides):
    base = {
        "codigo_municipio": "1000000",
        "rede": "Pública",
        "ano": 2023,
        "ideb": 5.0,
        "meta_projetada": 4.8,
        "nota_saeb_matematica": "200.0",
        "nota_saeb_portugues": "190.0",
        "nota_saeb_media_padronizada_n": "5.5",
        "taxa_aprovacao_total": "90.0",
        "taxa_aprovacao_por_serie": {"1º": 95.0, "2º": 85.0},
    }
    base.update(overrides)
    return base


def test_taxa_aprovacao_todas_series_media_por_serie():
    df = pd.DataFrame([
        _linha(taxa_aprovacao_por_serie={"1º": 90.0, "2º": 80.0}),
        _linha(taxa_aprovacao_por_serie={"1º": 100.0, "2º": 90.0}),
    ])
    resultado = taxa_aprovacao_todas_series(df)
    assert resultado == {"1º": 95.0, "2º": 85.0}


def test_taxa_aprovacao_todas_series_ignora_linhas_sem_dado():
    df = pd.DataFrame([
        _linha(taxa_aprovacao_por_serie={"1º": 90.0}),
        _linha(taxa_aprovacao_por_serie=None),
    ])
    resultado = taxa_aprovacao_todas_series(df)
    assert resultado == {"1º": 90.0}


def test_taxa_aprovacao_reusa_todas_series():
    df = pd.DataFrame([_linha(taxa_aprovacao_por_serie={"1º": 70.0, "2º": 80.0})])
    assert taxa_aprovacao(df, "1º") == 70.0
    assert taxa_aprovacao(df, "3º") is None  # série inexistente nesta amostra


def test_saeb_medias():
    df = pd.DataFrame([
        _linha(nota_saeb_matematica="200.0", nota_saeb_portugues="190.0",
               nota_saeb_media_padronizada_n="5.0"),
        _linha(nota_saeb_matematica="220.0", nota_saeb_portugues="210.0",
               nota_saeb_media_padronizada_n="6.0"),
    ])
    assert saeb_media_matematica(df) == 210.0
    assert saeb_media_portugues(df) == 200.0
    assert saeb_media_nota_padronizada(df) == 5.5


def test_saeb_media_matematica_retorna_none_quando_tudo_ausente():
    df = pd.DataFrame([_linha(nota_saeb_matematica=None)])
    assert saeb_media_matematica(df) is None


def test_comparar_meta_ideb_marca_atingiu_e_calcula_diferenca():
    df = pd.DataFrame([
        _linha(ideb=5.5, meta_projetada=5.0),   # atingiu
        _linha(ideb=4.0, meta_projetada=4.5),   # não atingiu
    ])
    resultado = comparar_meta_ideb(df)
    assert len(resultado) == 2
    assert resultado[0]["atingiu_meta"] is True
    assert resultado[0]["diferenca"] == 0.5
    assert resultado[1]["atingiu_meta"] is False
    assert resultado[1]["diferenca"] == -0.5


def test_comparar_meta_ideb_ignora_ausencias():
    """ideb ou meta ausentes (None) não entram na comparação — não há o que comparar."""
    df = pd.DataFrame([
        _linha(ideb=5.0, meta_projetada=None),  # meta ausente (ex.: ciclo 2023)
        _linha(ideb=None, meta_projetada=4.0),  # ideb ausente (participação insuficiente)
        _linha(ideb=5.0, meta_projetada=4.5),   # linha válida
    ])
    resultado = comparar_meta_ideb(df)
    assert len(resultado) == 1
    assert resultado[0]["ideb"] == 5.0


def test_evolucao_ideb_reduz_serie_por_ano_e_ordena():
    series_por_ano = {
        2023: pd.DataFrame([_linha(ideb=6.0), _linha(ideb=8.0)]),  # média 7.0
        2019: pd.DataFrame([_linha(ideb=5.0)]),
    }
    resultado = evolucao_ideb(series_por_ano)
    assert list(resultado.keys()) == [2019, 2023]  # ordenado por ano
    assert resultado[2019] == 5.0
    assert resultado[2023] == 7.0


def test_evolucao_ideb_pula_ano_totalmente_sem_ideb():
    series_por_ano = {2021: pd.DataFrame([_linha(ideb=None)])}
    resultado = evolucao_ideb(series_por_ano)
    assert resultado == {}


def test_aprovacao_geral_media_e_media_municipio():
    df = pd.DataFrame([
        _linha(codigo_municipio="1000000", taxa_aprovacao_total="80.0"),
        _linha(codigo_municipio="2000000", taxa_aprovacao_total="90.0"),
    ])
    assert aprovacao_geral_media(df) == 85.0
    assert media_municipio(df, "1000000") == 80.0


def test_valor_medias_retorna_seis_metricas_na_ordem_esperada():
    df = pd.DataFrame([_linha()])
    resultado = valor_medias(df, "1000000")
    assert len(resultado) == 6
    assert isinstance(resultado[0], dict)  # taxa_aprovacao_todas_series


# --------------------------------------------------------------- regressões
# Bugs reais expostos pela migração do Supabase para o SQLite.

def test_taxa_aprovacao_aceita_json_em_texto():
    """No SQLite a coluna é TEXT: chega string, não dict como vinha da API."""
    df = pd.DataFrame([
        _linha(taxa_aprovacao_por_serie=json.dumps({"1º": 90.0, "2º": 80.0})),
        _linha(taxa_aprovacao_por_serie=json.dumps({"1º": 100.0, "2º": 90.0})),
    ])
    assert taxa_aprovacao_todas_series(df) == {"1º": 95.0, "2º": 85.0}


def test_taxa_aprovacao_ignora_nan_alem_de_none():
    """Bug: testava `is None`, mas NULL de coluna TEXT vira NaN (float).

    O NaN passava pela checagem e estourava AttributeError no `.items()` —
    quebrava o pipeline inteiro na primeira execução contra o banco real.
    """
    df = pd.DataFrame([
        _linha(taxa_aprovacao_por_serie=json.dumps({"1º": 90.0})),
        _linha(taxa_aprovacao_por_serie=float("nan")),
        _linha(taxa_aprovacao_por_serie=None),
    ])
    assert taxa_aprovacao_todas_series(df) == {"1º": 90.0}


def test_medias_devolvem_float_nativo_nao_numpy():
    """Bug: `Series.mean()` devolve numpy.float64.

    Vazava para os logs como `np.float64(5.28)` e não é serializável pelo
    JSON encoder padrão que a API usa para montar a resposta.
    """
    df = pd.DataFrame([_linha(), _linha(ideb=6.0)])
    for valor in (saeb_media_matematica(df), aprovacao_geral_media(df),
                  media_municipio(df, "1000000")):
        assert type(valor) is float
        assert not isinstance(valor, np.floating)

    evolucao = evolucao_ideb({2025: df})
    ano, ideb = next(iter(evolucao.items()))
    assert type(ano) is int and type(ideb) is float


def test_comparar_meta_devolve_ano_como_int():
    """`ano` sai como Int64 do pandas; a resposta JSON precisa de int nativo."""
    df = pd.DataFrame([_linha(ano=2025, ideb=5.5, meta_projetada=5.0)])
    df["ano"] = df["ano"].astype("Int64")
    assert type(comparar_meta_ideb(df)[0]["ano"]) is int


def test_media_municipio_aceita_codigo_numerico():
    """Bug: codigo_municipio é TEXT; um int devolvia None como se não houvesse dado."""
    df = pd.DataFrame([_linha(codigo_municipio="1000000", taxa_aprovacao_total=80.0)])
    assert media_municipio(df, 1000000) == media_municipio(df, "1000000") == 80.0


def test_medias_em_dataframe_vazio_devolvem_none():
    """DataFrame vazio não pode estourar: é o resultado normal de um filtro restritivo."""
    vazio = pd.DataFrame(columns=["nota_saeb_matematica", "taxa_aprovacao_total",
                                  "codigo_municipio"])
    assert saeb_media_matematica(vazio) is None
    assert aprovacao_geral_media(vazio) is None
    assert media_municipio(vazio, "1000000") is None
