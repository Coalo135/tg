"""
Testes das rotas da API.

As funções de acesso ao banco são substituídas por dados sintéticos, então a
suíte não depende de um `sqlite_ideb.db` importado — o que ela verifica é o
contrato HTTP (códigos de status, formato da resposta, repasse dos filtros), não
o conteúdo do banco. A integração real com o SQLite é coberta por
`tests/test_consulta.py`.
"""
import json
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from API.main import app

client = TestClient(app)


def _linha(**overrides):
    base = {
        "codigo_municipio": "1000000",
        "rede": "Pública",
        "ano": 2025,
        "ideb": 5.5,
        "meta_projetada": 5.0,
        "nota_saeb_matematica": 200.0,
        "nota_saeb_portugues": 190.0,
        "nota_saeb_media_padronizada_n": 5.5,
        "taxa_aprovacao_total": 90.0,
        "taxa_aprovacao_por_serie": json.dumps({"1º": 95.0, "2º": 85.0}),
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------ validação

def test_resultados_sem_filtro_retorna_400():
    """Sem filtro, a consulta devolveria a tabela inteira (~1,3 M linhas)."""
    assert client.get("/resultados").status_code == 400


def test_escolas_sem_filtro_retorna_400():
    assert client.get("/escolas").status_code == 400


def test_baixar_chave_desconhecida_retorna_404():
    resp = client.get("/baixar", params={"chave": "planilha_que_nao_existe"})
    assert resp.status_code == 404


# --------------------------------------------------------------------- rotas

def test_planilhas_lista_o_catalogo():
    corpo = client.get("/planilhas").json()
    assert len(corpo) == 10
    assert {"chave", "arquivo", "abrangencia", "nivel_ensino", "layout"} <= set(corpo[0])


@patch("API.rotas.dados.buscar_municipios")
def test_municipios_repassa_filtro_de_uf(mock_buscar):
    mock_buscar.return_value = [
        {"codigo_municipio": "5300108", "nome_municipio": "Brasília", "sigla_uf": "DF"}
    ]
    resp = client.get("/municipios", params={"sigla_uf": "DF"})

    assert resp.status_code == 200
    assert resp.json() == mock_buscar.return_value
    mock_buscar.assert_called_once_with(sigla_uf="DF")


@patch("API.rotas.dados.buscar_ufs")
def test_ufs(mock_buscar):
    mock_buscar.return_value = ["CE", "DF"]
    assert client.get("/ufs").json() == ["CE", "DF"]


@patch("API.rotas.dados.anos_disponiveis")
def test_anos_repassa_apenas_filtros_preenchidos(mock_anos):
    mock_anos.return_value = [2023, 2025]

    resp = client.get("/anos", params={"codigo_municipio": "5300108"})

    assert resp.json() == [2023, 2025]
    mock_anos.assert_called_once_with(codigo_municipio="5300108")


@patch("API.rotas.dados.buscar_resultados")
def test_resultados_pede_json_desserializado(mock_buscar):
    mock_buscar.return_value = [_linha() | {"taxa_aprovacao_por_serie": {"1º": 95.0}}]

    resp = client.get("/resultados", params={"sigla_uf": "DF"})

    assert resp.status_code == 200
    assert resp.json()[0]["taxa_aprovacao_por_serie"] == {"1º": 95.0}
    # as_dataframe=False é o que faz a rota devolver o JSON já como objeto
    assert mock_buscar.call_args.kwargs["as_dataframe"] is False


@patch("API.rotas.estatisticas.buscar_resultados")
def test_estatisticas_com_filtro(mock_buscar):
    mock_buscar.return_value = pd.DataFrame([
        _linha(),
        _linha(taxa_aprovacao_por_serie=json.dumps({"1º": 85.0})),
    ])

    resp = client.get("/estatisticas", params={"sigla_uf": "DF"})

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["taxa_aprovacao_por_serie"]["1º"] == 90.0  # média de 95 e 85
    assert corpo["saeb_matematica"] == 200.0
    mock_buscar.assert_called_once_with(sigla_uf="DF")


@patch("API.rotas.estatisticas.buscar_resultados")
def test_estatisticas_vazio_retorna_404(mock_buscar):
    mock_buscar.return_value = pd.DataFrame(columns=["ideb"])
    assert client.get("/estatisticas", params={"sigla_uf": "ZZ"}).status_code == 404


@patch("API.rotas.estatisticas.buscar_resultados")
def test_comparacao_meta_resumo(mock_buscar):
    mock_buscar.return_value = pd.DataFrame([
        _linha(ideb=5.5, meta_projetada=5.0),   # atingiu
        _linha(ideb=4.0, meta_projetada=4.5),   # não atingiu
    ])

    corpo = client.get("/comparacao-meta", params={"codigo_municipio": "1000000"}).json()

    assert corpo["resumo"] == {"total": 2, "atingiram_meta": 1, "nao_atingiram_meta": 1}
    assert len(corpo["detalhes"]) == 2


@patch("API.rotas.estatisticas.buscar_evolucao_ideb")
def test_evolucao_retorna_lista_ordenada(mock_buscar):
    mock_buscar.return_value = {
        2025: pd.DataFrame([_linha(ideb=6.0), _linha(ideb=8.0)]),
        2023: pd.DataFrame([_linha(ideb=5.0)]),
    }

    resp = client.get("/evolucao", params={"anos": [2023, 2025], "sigla_uf": "DF"})

    assert resp.status_code == 200
    assert resp.json() == [
        {"ano": 2023, "ideb_medio": 5.0},
        {"ano": 2025, "ideb_medio": 7.0},
    ]


# ------------------------------------------------------------------ modelos

def _relacao_falsa():
    """O que `Modelos.relacao_inse_ideb.calcular` devolve, em miniatura."""
    municipios = pd.DataFrame([
        {"posicao": 1, "codigo_municipio": "2312908", "nome_municipio": "Sobral",
         "sigla_uf": "CE", "media_inse": 4.37, "ideb": 9.6, "ideb_previsto": 5.31,
         "residuo": 4.29},
        {"posicao": 2, "codigo_municipio": "5300108", "nome_municipio": "Brasília",
         "sigla_uf": "DF", "media_inse": 5.6, "ideb": 6.5, "ideb_previsto": 6.63,
         "residuo": -0.13},
    ])
    return {"nivel_ensino": "anos_iniciais", "ano": 2023,
            "ajuste": {"n": 2, "pearson": 0.55, "spearman": 0.59, "r2": 0.31,
                       "inclinacao": 1.08, "intercepto": 0.59},
            "descartes": {"sem IDEB": 129}, "municipios": municipios}


def _agrupamento_falso():
    municipios = pd.DataFrame([
        {"cluster": 1, "codigo_municipio": "2312908", "nome_municipio": "Sobral",
         "sigla_uf": "CE", "media_inse": 4.37, "ideb": 9.6, "indicador_rendimento_p": 0.99,
         "nota_saeb_media_padronizada_n": 9.7, "ideb_previsto": 5.31, "residuo": 4.29},
    ])
    perfil = pd.DataFrame(
        [{"municipios": 1, "media_inse": 4.37, "ideb": 9.6, "indicador_rendimento_p": 0.99,
          "nota_saeb_media_padronizada_n": 9.7, "residuo": 4.29}],
        index=pd.Index([1], name="cluster"))
    return {"nivel_ensino": "anos_iniciais", "ano": 2023, "k": 2, "descartes": {},
            "avaliacao": pd.DataFrame([{"k": 2, "inercia": 1.0, "silhueta": 0.43}]),
            "perfil": perfil, "outliers": municipios, "municipios": municipios}


@patch("API.rotas.modelos.anos_disponiveis", return_value=[2021, 2023])
def test_modelos_nivel_invalido_retorna_400(_anos):
    resp = client.get("/modelos/relacao-inse-ideb", params={"nivel_ensino": "fundamental"})
    assert resp.status_code == 400


@patch("API.rotas.modelos.anos_disponiveis", return_value=[2021, 2023])
def test_modelos_ano_sem_inse_retorna_404(_anos):
    resp = client.get("/modelos/relacao-inse-ideb",
                      params={"nivel_ensino": "anos_iniciais", "ano": 2025})
    assert resp.status_code == 404
    assert "2021" in resp.json()["detail"]


@patch("API.rotas.modelos.calcular_relacao", return_value=_relacao_falsa())
@patch("API.rotas.modelos.anos_disponiveis", return_value=[2021, 2023])
def test_relacao_devolve_ajuste_e_recorta_por_uf(_anos, mock_calc):
    corpo = client.get("/modelos/relacao-inse-ideb",
                       params={"nivel_ensino": "anos_iniciais", "sigla_uf": "ce"}).json()

    assert corpo["ano"] == 2023  # sem `ano`, vale o mais recente com INSE
    assert corpo["ajuste"]["r2"] == 0.31
    assert corpo["total"] == 2   # o total é nacional, o recorte é só da lista
    assert [m["nome_municipio"] for m in corpo["municipios"]] == ["Sobral"]
    assert corpo["municipios"][0]["posicao"] == 1
    mock_calc.assert_called_once_with("anos_iniciais", 2023)


@patch("API.rotas.modelos.calcular_agrupamento", return_value=_agrupamento_falso())
@patch("API.rotas.modelos.calcular_relacao", return_value=_relacao_falsa())
@patch("API.rotas.modelos.anos_disponiveis", return_value=[2021, 2023])
def test_municipio_traz_previsao_posicao_e_cluster(_anos, _rel, _agr):
    corpo = client.get("/modelos/municipio/2312908",
                       params={"nivel_ensino": "anos_iniciais", "ano": 2023}).json()

    assert corpo["ideb"] == 9.6 and corpo["ideb_previsto"] == 5.31
    assert corpo["residuo"] == 4.29 and corpo["posicao"] == 1 and corpo["total"] == 2
    assert corpo["cluster"] == 1 and corpo["k"] == 2
    assert corpo["cluster_perfil"]["ideb"] == 9.6


@patch("API.rotas.modelos.calcular_agrupamento", return_value=None)
@patch("API.rotas.modelos.calcular_relacao", return_value=_relacao_falsa())
@patch("API.rotas.modelos.anos_disponiveis", return_value=[2021, 2023])
def test_municipio_sem_par_retorna_404(_anos, _rel, _agr):
    resp = client.get("/modelos/municipio/9999999", params={"nivel_ensino": "anos_iniciais"})
    assert resp.status_code == 404


@patch("API.rotas.modelos.calcular_agrupamento", return_value=_agrupamento_falso())
@patch("API.rotas.modelos.anos_disponiveis", return_value=[2021, 2023])
def test_agrupamento_devolve_k_perfil_e_municipios(_anos, _agr):
    corpo = client.get("/modelos/agrupamento", params={"nivel_ensino": "anos_iniciais"}).json()

    assert corpo["k"] == 2
    assert corpo["perfil"][0]["cluster"] == 1 and corpo["perfil"][0]["municipios"] == 1
    assert corpo["avaliacao"][0]["silhueta"] == 0.43
    assert corpo["municipios"][0]["cluster"] == 1
