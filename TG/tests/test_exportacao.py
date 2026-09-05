"""Unit tests for Exportacao.exportar — the explicit missing-data export decision."""
import pandas as pd

from Exportacao.exportar import TEXTO_DADO_AUSENTE, exportar_para_csv


def test_exportar_marca_ideb_ausente_em_vez_de_omitir_linha(tmp_path):
    df = pd.DataFrame([
        {"codigo_municipio": "1000000", "ideb": 5.5},
        {"codigo_municipio": "2000000", "ideb": None},  # baixa participação no SAEB
    ])
    caminho = exportar_para_csv(df, tmp_path / "saida.csv")

    # a coluna ideb mistura número e texto (o marcador), então ao reler vira string —
    # comportamento esperado do pandas, não um efeito colateral do exportar_para_csv.
    exportado = pd.read_csv(caminho, dtype=str)
    assert len(exportado) == 2  # nenhuma linha foi omitida
    assert float(exportado.loc[0, "ideb"]) == 5.5
    assert exportado.loc[1, "ideb"] == TEXTO_DADO_AUSENTE


def test_exportar_nao_afeta_outras_colunas(tmp_path):
    df = pd.DataFrame([{"codigo_municipio": "1000000", "ideb": None, "rede": "Pública"}])
    caminho = exportar_para_csv(df, tmp_path / "saida.csv")

    exportado = pd.read_csv(caminho)
    assert exportado.loc[0, "rede"] == "Pública"
    assert exportado.loc[0, "codigo_municipio"] == 1000000
