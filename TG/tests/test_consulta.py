"""
Testes da camada de consulta (Dados.consulta_ideb) contra um SQLite temporário.

Cada teste monta um banco do zero com o esquema real (`DataBase.schema`) e insere
poucas linhas conhecidas. Sem rede, sem depender do banco de produção — e como o
esquema vem do módulo de verdade, uma coluna renomeada lá quebra estes testes,
que é exatamente o aviso que se quer.
"""
import json

import pytest

import config
from Dados.consulta_ideb import (
    anos_disponiveis,
    buscar_escolas,
    buscar_evolucao_ideb,
    buscar_municipios,
    buscar_resultados,
    buscar_ufs,
)
from DataBase.conexao import BancoNaoEncontrado, conectar
from DataBase.schema import criar_schema

MUNICIPIOS = [
    ("5300108", "Brasília", "DF"),
    ("2312908", "Sobral", "CE"),
]

ESCOLAS = [
    ("53000010", "ESCOLA A", "5300108", "DF"),
    ("53000020", "ESCOLA B", "5300108", "DF"),
]


def _fato(**over):
    base = {
        "abrangencia": "municipio",
        "nivel_ensino": "anos_iniciais",
        "ano": 2023,
        "rede": "Pública",
        "codigo_entidade": "5300108",
        "nome_entidade": "Brasília",
        "sigla_uf": "DF",
        "codigo_municipio": "5300108",
        "codigo_escola": None,
        "taxa_aprovacao_total": 95.0,
        "indicador_rendimento_p": 0.95,
        "nota_saeb_matematica": 226.0,
        "nota_saeb_portugues": 217.0,
        "nota_saeb_media_padronizada_n": 6.2,
        "ideb": 5.9,
        "meta_projetada": 6.6,
        "taxa_aprovacao_por_serie": json.dumps({"1º": 97.0, "2º": 95.0}),
    }
    base.update(over)
    return base


COLUNAS_FATO = list(_fato().keys())
SQL_INSERT = (
    f"INSERT INTO ideb_resultados ({', '.join(COLUNAS_FATO)}) "
    f"VALUES ({', '.join(':' + c for c in COLUNAS_FATO)})"
)


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Banco temporário populado, com todo o projeto apontando para ele."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "teste.db")

    fatos = [
        _fato(),
        _fato(ano=2025, ideb=6.0, meta_projetada=None, taxa_aprovacao_por_serie=None),
        _fato(nivel_ensino="anos_finais", ideb=4.8),
        _fato(codigo_entidade="2312908", codigo_municipio="2312908",
              nome_entidade="Sobral", sigla_uf="CE", ideb=8.0),
        _fato(abrangencia="escola", codigo_entidade="53000010",
              codigo_escola="53000010", nome_entidade="ESCOLA A", ideb=5.5),
    ]

    with conectar() as conexao:
        criar_schema(conexao)
        conexao.executemany(
            "INSERT INTO municipios VALUES (?, ?, ?)", MUNICIPIOS)
        conexao.executemany(
            "INSERT INTO escolas VALUES (?, ?, ?, ?)", ESCOLAS)
        conexao.executemany(SQL_INSERT, fatos)
    return config.DB_PATH


def test_sem_banco_erro_explicito(tmp_path, monkeypatch):
    """Banco ausente deve falhar dizendo o que fazer, não devolver zero linhas.

    O SQLite cria um arquivo vazio ao conectar num caminho inexistente; sem esta
    checagem, "esqueci de importar" e "meu filtro não casou nada" produziriam o
    mesmo resultado vazio.
    """
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "nao_existe.db")
    with pytest.raises(BancoNaoEncontrado):
        buscar_resultados(sigla_uf="DF")


def test_busca_sem_filtro_traz_tudo(banco):
    assert len(buscar_resultados()) == 5


def test_filtro_por_uf_e_nivel(banco):
    df = buscar_resultados(sigla_uf="DF", nivel_ensino="anos_iniciais")
    assert len(df) == 3
    assert set(df["sigla_uf"]) == {"DF"}


def test_codigo_numerico_casa_com_texto_do_banco(banco):
    """codigo_municipio é TEXT; passar int não pode devolver vazio silenciosamente."""
    como_texto = buscar_resultados(codigo_municipio="5300108")
    como_inteiro = buscar_resultados(codigo_municipio=5300108)
    assert len(como_inteiro) == len(como_texto) > 0


def test_filtro_de_ano_aceita_lista(banco):
    df = buscar_resultados(codigo_municipio="5300108", ano=[2023, 2025])
    assert sorted(df["ano"].unique()) == [2023, 2025]


def test_filtro_invalido_e_rejeitado(banco):
    """Nome de coluna vindo de fora nunca entra no SQL montado."""
    from Dados.consulta_ideb import _montar_where

    with pytest.raises(ValueError):
        _montar_where({"coluna_inexistente": "x"})
    with pytest.raises(ValueError):
        _montar_where({"ano = 1 OR 1=1 --": "x"})


def test_valores_do_filtro_vao_como_parametro(banco):
    """O valor é sempre placeholder: aspas no conteúdo não fecham a string SQL."""
    from Dados.consulta_ideb import _montar_where

    where, parametros = _montar_where({"sigla_uf": "DF' OR '1'='1"})
    assert where == " WHERE sigla_uf = ?"
    assert parametros == ["DF' OR '1'='1"]
    # e, ponta a ponta, um valor malicioso simplesmente não casa com nada
    assert buscar_resultados(sigla_uf="DF' OR '1'='1").empty


def test_resultado_vazio_mantem_as_colunas(banco):
    """DataFrame vazio ainda precisa ter as colunas: quem consome acessa df['ideb']."""
    df = buscar_resultados(sigla_uf="ZZ")
    assert df.empty
    assert "ideb" in df.columns
    assert "taxa_aprovacao_por_serie" in df.columns


def test_valores_ausentes_viram_nan_nunca_zero(banco):
    """meta_projetada NULL em 2025 é ausência real, não meta igual a zero."""
    df = buscar_resultados(codigo_municipio="5300108", ano=2025,
                           nivel_ensino="anos_iniciais")
    assert df["meta_projetada"].isna().all()
    assert not (df["meta_projetada"] == 0).any()


def test_as_dataframe_false_desserializa_o_json(banco):
    registros = buscar_resultados(codigo_municipio="5300108", ano=2023,
                                  nivel_ensino="anos_iniciais", as_dataframe=False)
    assert registros[0]["taxa_aprovacao_por_serie"] == {"1º": 97.0, "2º": 95.0}


def test_evolucao_agrupa_por_ano(banco):
    por_ano = buscar_evolucao_ideb(
        [2023, 2025], codigo_municipio="5300108", nivel_ensino="anos_iniciais")
    assert sorted(por_ano) == [2023, 2025]
    assert por_ano[2025]["ideb"].iloc[0] == 6.0


def test_evolucao_pula_ano_sem_registro(banco):
    por_ano = buscar_evolucao_ideb([2023, 1999], codigo_municipio="5300108")
    assert 1999 not in por_ano


def test_filtros_da_interface(banco):
    assert buscar_ufs() == ["CE", "DF"]
    assert [m["nome_municipio"] for m in buscar_municipios()] == ["Brasília", "Sobral"]
    assert [m["nome_municipio"] for m in buscar_municipios(sigla_uf="CE")] == ["Sobral"]
    assert len(buscar_escolas(codigo_municipio="5300108")) == 2
    assert anos_disponiveis(codigo_municipio="5300108") == [2023, 2025]


def test_listar_escolas_sem_filtro_e_recusado(banco):
    """São ~85 mil escolas: devolver todas não popula seletor nenhum."""
    with pytest.raises(ValueError):
        buscar_escolas()
