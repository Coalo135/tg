"""
Testes do INSE: as regras de limpeza do importador (funções puras sobre um
DataFrame com as colunas da planilha) e a camada de consulta contra um SQLite
temporário montado com o esquema real.
"""
import pandas as pd
import pytest

import config
from Dados.consulta_inse import anos_inse, buscar_inse, buscar_inse_ideb
from DataBase.conexao import conectar
from DataBase.importData import gravar_municipios
from DataBase.importInse import gravar_fatos, montar_registros
from DataBase.schema import criar_schema

COLUNAS_PLANILHA = [
    "NU_ANO_SAEB", "CO_UF", "SG_UF", "NO_UF", "CO_MUNICIPIO", "NO_MUNICIPIO",
    "TP_TIPO_REDE", "TP_LOCALIZACAO", "TP_CAPITAL", "QTD_ALUNOS_INSE", "MEDIA_INSE",
] + [f"PC_NIVEL_{i}" for i in range(1, 9)]


def _linha(**over):
    base = {
        "NU_ANO_SAEB": 2023, "CO_UF": 23, "SG_UF": "CE", "NO_UF": "Ceará",
        "CO_MUNICIPIO": 2312908.0,   # float: é assim que o Excel entrega o código
        "NO_MUNICIPIO": "Sobral",
        "TP_TIPO_REDE": 6, "TP_LOCALIZACAO": 0, "TP_CAPITAL": 2,
        "QTD_ALUNOS_INSE": 3000, "MEDIA_INSE": 4.9,
        "PC_NIVEL_1": 0.5, "PC_NIVEL_2": 10.0, "PC_NIVEL_3": 20.0, "PC_NIVEL_4": 30.0,
        "PC_NIVEL_5": 20.0, "PC_NIVEL_6": 12.0, "PC_NIVEL_7": 6.0, "PC_NIVEL_8": 1.5,
    }
    base.update(over)
    return base


def _planilha(*linhas):
    return pd.DataFrame(list(linhas), columns=COLUNAS_PLANILHA).astype(object)


# ------------------------------------------------------ regras do importador

def test_rede_e_localizacao_traduzidas_para_o_vocabulario_do_ideb():
    registros, _ = montar_registros(_planilha(_linha(TP_TIPO_REDE=6, TP_LOCALIZACAO=0)))
    assert registros[0]["rede"] == "Pública"
    assert registros[0]["localizacao"] == "Total"
    assert registros[0]["codigo_municipio"] == "2312908"  # sem o .0 do Excel


def test_rede_zero_e_descartada_por_ser_duplicata_da_seis():
    registros, descartes = montar_registros(_planilha(
        _linha(TP_TIPO_REDE=0), _linha(TP_TIPO_REDE=6)))
    assert len(registros) == 1
    assert registros[0]["rede"] == "Pública"
    assert sum(descartes.values()) == 1


def test_media_zero_vira_nulo():
    """O INEP grava 0 quando não há aluno medido; na escala do INSE zero é impossível."""
    registros, _ = montar_registros(_planilha(
        _linha(MEDIA_INSE=0, QTD_ALUNOS_INSE=0, PC_NIVEL_2=5.0)))
    assert registros[0]["media_inse"] is None
    assert registros[0]["qtd_alunos"] is None


def test_linhas_repetidas_identicas_entram_uma_vez():
    """O arquivo de 2023 repete a mesma linha dezenas de vezes."""
    registros, descartes = montar_registros(_planilha(_linha(), _linha(), _linha()))
    assert len(registros) == 1
    assert descartes["linhas repetidas, idênticas em todas as colunas"] == 2


def test_mesma_chave_com_valores_diferentes_e_contada():
    registros, descartes = montar_registros(
        _planilha(_linha(MEDIA_INSE=4.9), _linha(MEDIA_INSE=5.1)))
    assert len(registros) == 2
    assert descartes["mesma chave, valores diferentes (fica a última)"] == 1


def test_linha_sem_indicador_algum_nao_e_gravada():
    vazia = _linha(MEDIA_INSE=0, QTD_ALUNOS_INSE=0,
                   **{f"PC_NIVEL_{i}": None for i in range(1, 9)})
    registros, descartes = montar_registros(_planilha(vazia, _linha()))
    assert len(registros) == 1
    assert descartes["sem nenhum indicador"] == 1


# ------------------------------------------------------------ banco + consulta

def _fato_ideb(**over):
    base = {
        "abrangencia": "municipio", "nivel_ensino": "anos_iniciais", "ano": 2023,
        "rede": "Pública", "codigo_entidade": "2312908", "nome_entidade": "Sobral",
        "sigla_uf": "CE", "codigo_municipio": "2312908", "codigo_escola": None,
        "taxa_aprovacao_total": 98.0, "indicador_rendimento_p": 0.98,
        "nota_saeb_matematica": 240.0, "nota_saeb_portugues": 230.0,
        "nota_saeb_media_padronizada_n": 7.5, "ideb": 7.3, "meta_projetada": None,
        "taxa_aprovacao_por_serie": None,
    }
    base.update(over)
    return base


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "teste.db")
    inse = _planilha(
        _linha(),                                                     # Sobral, com IDEB
        _linha(TP_LOCALIZACAO=1, MEDIA_INSE=5.0),                     # Sobral, urbana
        _linha(NU_ANO_SAEB=2021, MEDIA_INSE=4.7),                     # Sobral 2021, sem IDEB
        _linha(CO_MUNICIPIO=2304400.0, NO_MUNICIPIO="Fortaleza",
               TP_CAPITAL=1, MEDIA_INSE=5.3),                         # Fortaleza, com IDEB
        _linha(CO_MUNICIPIO=2300101.0, NO_MUNICIPIO="Abaiara", MEDIA_INSE=4.1),  # sem IDEB
    )
    ideb = [
        _fato_ideb(),
        _fato_ideb(codigo_entidade="2304400", codigo_municipio="2304400",
                   nome_entidade="Fortaleza", ideb=6.1),
        _fato_ideb(nivel_ensino="anos_finais", ideb=8.0),
    ]
    colunas = list(ideb[0].keys())
    sql_ideb = (f"INSERT INTO ideb_resultados ({', '.join(colunas)}) "
                f"VALUES ({', '.join(':' + c for c in colunas)})")

    registros, _ = montar_registros(inse)
    with conectar() as conexao:
        criar_schema(conexao)
        gravar_municipios(conexao, registros)
        gravar_fatos(conexao, registros)
        conexao.executemany(sql_ideb, ideb)
    return registros


def test_reimportar_nao_duplica(banco):
    """A chave única + INSERT OR REPLACE tornam a carga idempotente."""
    with conectar() as conexao:
        antes = conexao.execute("SELECT COUNT(*) FROM inse_municipios").fetchone()[0]
        gravar_fatos(conexao, banco)
        depois = conexao.execute("SELECT COUNT(*) FROM inse_municipios").fetchone()[0]
    assert antes == depois == 5


def test_anos_inse_vem_do_banco(banco):
    assert anos_inse() == [2021, 2023]


def test_buscar_inse_filtra_e_normaliza(banco):
    df = buscar_inse(ano=2023, codigo_municipio=2312908, localizacao="Total")
    assert len(df) == 1
    assert df.loc[0, "media_inse"] == 4.9
    assert df.loc[0, "capital"] == 2


def test_par_inse_ideb_junta_por_ano_municipio_e_rede(banco):
    df = buscar_inse_ideb("anos_iniciais", ano=2023)
    por_municipio = df.set_index("codigo_municipio")

    assert len(df) == 3  # Sobral, Fortaleza, Abaiara — só localização Total
    assert por_municipio.loc["2312908", "ideb"] == 7.3
    assert por_municipio.loc["2312908", "nome_municipio"] == "Sobral"
    assert por_municipio.loc["2304400", "ideb"] == 6.1
    # município com INSE mas sem IDEB permanece, com o IDEB nulo — não some
    assert pd.isna(por_municipio.loc["2300101", "ideb"])


def test_par_respeita_o_nivel_de_ensino(banco):
    df = buscar_inse_ideb("anos_finais", ano=2023).set_index("codigo_municipio")
    assert df.loc["2312908", "ideb"] == 8.0
    assert pd.isna(df.loc["2304400", "ideb"])


def test_par_sem_ano_traz_todos_os_anos(banco):
    df = buscar_inse_ideb("anos_iniciais")
    assert sorted(df["ano"].unique()) == [2021, 2023]
