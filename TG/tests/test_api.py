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


def test_previsao_nivel_invalido_retorna_400():
    resp = client.get("/previsao/1000000", params={"nivel": "ensino_medio"})
    assert resp.status_code == 400


def test_escolas_sem_filtro_retorna_400():
    assert client.get("/escolas").status_code == 400


def test_baixar_chave_desconhecida_retorna_404():
    resp = client.get("/baixar", params={"chave": "planilha_que_nao_existe"})
    assert resp.status_code == 404


# --------------------------------------------------------------------- rotas

def test_planilhas_lista_o_catalogo():
    corpo = client.get("/planilhas").json()
    assert len(corpo) == 8
    assert {"chave", "arquivo", "abrangencia", "nivel_ensino"} <= set(corpo[0])


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
