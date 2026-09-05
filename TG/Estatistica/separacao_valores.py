"""
separacao_valores.py — Cálculos estatísticos sobre os resultados do IDEB.

Recebe DataFrames já filtrados (ver Dados.consulta_ideb.buscar_resultados) e
calcula médias, comparações com a meta do INEP e séries históricas.
"""
import json
import math
from statistics import mean

import pandas as pd


def valor_medias(df: pd.DataFrame, municipio: str) -> list:
    """Agrega as principais médias de `df`: taxa de aprovação por série, SAEB
    (matemática/português/padronizada), aprovação geral e a média de um município."""
    return [
        taxa_aprovacao_todas_series(df),
        saeb_media_matematica(df),
        saeb_media_portugues(df),
        saeb_media_nota_padronizada(df),
        aprovacao_geral_media(df),
        media_municipio(df, municipio),
    ]


def taxa_aprovacao_todas_series(df: pd.DataFrame) -> dict[str, float]:
    """Média de taxa de aprovação de TODAS as séries, numa única passada pelo DF.

    Evita chamar `taxa_aprovacao(df, serie)` uma vez por série (o que reprocessaria
    o DF inteiro a cada série) — é o formato que o GeradorGrafico consome pra montar
    a barra de comparação por série de uma vez.
    """
    valores_por_serie: dict[str, list] = {}

    for _, row in df.iterrows():
        dados_serie = row["taxa_aprovacao_por_serie"]
        if isinstance(dados_serie, str):
            dados_serie = json.loads(dados_serie)
        # Ausência chega de formas diferentes conforme a origem: None vindo do
        # JSON da API, NaN (float) quando o pandas lê a coluna TEXT do SQLite com
        # NULL. Checar o tipo final cobre as duas — testar `is None` deixava o NaN
        # passar e quebrava no `.items()`.
        if not isinstance(dados_serie, dict):
            continue
        for serie, valor in dados_serie.items():
            if valor is not None:
                valores_por_serie.setdefault(serie, []).append(float(valor))

    return {serie: round(mean(valores), 2) for serie, valores in valores_por_serie.items()}


def taxa_aprovacao(df: pd.DataFrame, serie: str) -> float | None:
    """Taxa de aprovação de uma única série. Mantida por compatibilidade;
    reusa taxa_aprovacao_todas_series em vez de reprocessar o DF."""
    return taxa_aprovacao_todas_series(df).get(serie)


def _media(df: pd.DataFrame, coluna: str) -> float | None:
    """Média de uma coluna numérica, como float nativo do Python.

    O `float()` no fim não é decorativo: `Series.mean()` devolve `numpy.float64`,
    que vaza para os logs como `np.float64(5.28)` e não é serializável por
    padrão quando a API monta a resposta JSON.
    """
    if coluna not in df.columns or df.empty:
        return None
    resultado = df[coluna].astype(float).mean()
    return None if math.isnan(resultado) else round(float(resultado), 2)


def saeb_media_matematica(df: pd.DataFrame) -> float | None:
    return _media(df, "nota_saeb_matematica")


def saeb_media_portugues(df: pd.DataFrame) -> float | None:
    return _media(df, "nota_saeb_portugues")


def saeb_media_nota_padronizada(df: pd.DataFrame) -> float | None:
    return _media(df, "nota_saeb_media_padronizada_n")


def comparar_meta_ideb(df: pd.DataFrame) -> list[dict]:
    """Compara, linha a linha, o IDEB observado com a meta projetada do INEP.

    Linhas sem ideb ou sem meta_projetada (ambos existem no banco como ausência
    real — baixa participação no SAEB, ou o INEP não projetou meta pra aquele
    ciclo — nunca como zero) ficam de fora: não há o que comparar nelas.
    """
    resultados = []

    for _, row in df.iterrows():
        ideb, meta = row["ideb"], row["meta_projetada"]
        if pd.isna(ideb) or pd.isna(meta):
            continue
        ideb, meta = float(ideb), float(meta)
        resultados.append({
            "codigo_municipio": row["codigo_municipio"],
            "rede": row["rede"],
            "ano": int(row["ano"]) if pd.notna(row["ano"]) else None,
            "ideb": ideb,
            "meta_projetada": meta,
            "atingiu_meta": ideb >= meta,
            "diferenca": round(ideb - meta, 2),
        })

    return resultados


def evolucao_ideb(series_por_ano: dict[int, pd.DataFrame]) -> dict[int, float]:
    """Reduz {ano: df} (ver Dados.consulta_ideb.buscar_evolucao_ideb) numa série
    histórica {ano: ideb_medio}, pronta pro GeradorGrafico plotar a evolução temporal.
    """
    evolucao = {}
    for ano, df_ano in series_por_ano.items():
        media = df_ano["ideb"].astype(float).mean()
        if not math.isnan(media):
            evolucao[int(ano)] = round(float(media), 2)
    return dict(sorted(evolucao.items()))


def aprovacao_geral_media(df: pd.DataFrame) -> float | None:
    return _media(df, "taxa_aprovacao_total")


def media_municipio(df: pd.DataFrame, municipio: str) -> float | None:
    """Taxa de aprovação média de um município dentro de `df`.

    Compara como string: `codigo_municipio` é TEXT no banco, e um código passado
    como int nunca casaria — a função devolveria None como se o município não
    tivesse dado, em vez de sinalizar o erro de tipo.
    """
    recorte = df.loc[df["codigo_municipio"].astype(str) == str(municipio)]
    return _media(recorte, "taxa_aprovacao_total")
