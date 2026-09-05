"""
Testes do pipeline de ML — sem tocar no banco (nunca chama `carregar_base()`).

Os módulos de `ML/` passaram a usar import absoluto a partir da raiz do projeto,
então os testes importam por `ML.dataset` como qualquer outro pacote. A versão
anterior deste arquivo precisava inserir `ML/` no `sys.path` na mão, porque os
módulos se importavam por nome simples (`from dados import ...`).
"""
import pandas as pd

from config import PASSO_CICLO
from ML.dataset import ALVO, FEATURES, montar_pares, montar_xy
from ML.modelos import BaselineIngenuo, criar_modelos
from ML.validacao import montar_rodadas


def _base_sintetica():
    """Um município, 4 ciclos consecutivos (2019 a 2025), 1 nível."""
    return pd.DataFrame([
        {
            "codigo_municipio": "9999999", "nivel_ensino": "anos_iniciais", "ano": ano,
            "nome_entidade": "Município Teste", "sigla_uf": "TS",
            "ideb": ideb, "meta_projetada": meta,
            "indicador_rendimento_p": 0.9, "nota_saeb_media_padronizada_n": 200.0,
        }
        for ano, ideb, meta in [
            (2019, 5.0, 5.2), (2021, 5.5, 5.7), (2023, 6.0, None), (2025, 6.2, None)
        ]
    ])


def test_baseline_ingenuo_repete_ideb_t():
    modelo = BaselineIngenuo()
    X = pd.DataFrame({"ideb_T": [4.0, 5.5, 6.2]})
    modelo.fit(X)  # não faz nada, mas precisa existir na interface sklearn
    assert list(modelo.predict(X)) == [4.0, 5.5, 6.2]


def test_criar_modelos_devolve_instancias_novas_a_cada_chamada():
    m1, m2 = criar_modelos(), criar_modelos()
    assert set(m1) == {"baseline", "regressao_linear", "random_forest"}
    assert m1["baseline"] is not m2["baseline"]


def test_montar_pares_sem_vazamento_de_futuro():
    """A feature ideb_T do par T=2019 é o IDEB de 2019, nunca o de 2021 em diante."""
    pares = montar_pares(_base_sintetica())

    # T=2019->2021, 2021->2023, 2023->2025 (2025 não tem T+1 nos dados)
    assert len(pares) == 3
    assert set(pares["ano_alvo"] - pares["ano_T"]) == {PASSO_CICLO}

    linha_2019 = pares[pares["ano_T"] == 2019].iloc[0]
    assert linha_2019["ideb_T"] == 5.0        # o próprio T, não o futuro
    assert linha_2019["ideb_alvo"] == 5.5     # T+1 real
    assert pd.isna(linha_2019["ideb_T_menos_1"])  # não existe ciclo 2017 na amostra

    linha_2021 = pares[pares["ano_T"] == 2021].iloc[0]
    assert linha_2021["ideb_T_menos_1"] == 5.0  # o T-1 é o 2019 real


def test_meta_nula_nao_e_feature():
    """meta_T_mais_1 fica de fora de FEATURES propositalmente (ver dataset.py)."""
    assert "meta_T_mais_1" not in FEATURES
    pares = montar_pares(_base_sintetica())
    linha_2021 = pares[pares["ano_T"] == 2021].iloc[0]
    assert pd.isna(linha_2021["meta_T_mais_1"])  # meta de 2023 é nula, como no real


def test_montar_xy_descarta_linhas_com_feature_ausente():
    pares = montar_pares(_base_sintetica())
    X, y, limpo = montar_xy(pares, FEATURES, verbose=False)
    # T=2019 não tem ideb_T_menos_1; sobram T=2021 e T=2023
    assert len(limpo) == 2
    assert list(X.columns) == FEATURES
    assert y.name == ALVO


def test_rodadas_de_validacao_acompanham_os_dados():
    """As rodadas eram fixas até 2023 e ignoravam o ciclo novo. Agora saem dos dados."""
    pares = montar_pares(_base_sintetica())
    rodadas = montar_rodadas(pares)

    assert rodadas[-1] == (2023, 2025)  # o ciclo mais recente é testado
    # todo teste ocorre depois do fim do treino: nunca se treina com o futuro
    assert all(treino_max < ano_teste for treino_max, ano_teste in rodadas)


def test_rodadas_nao_usam_o_primeiro_ano_como_teste():
    """Testar no primeiro ano-alvo deixaria o treino vazio."""
    pares = montar_pares(_base_sintetica())
    primeiro_alvo = pares["ano_alvo"].min()
    assert primeiro_alvo not in [teste for _, teste in montar_rodadas(pares)]
