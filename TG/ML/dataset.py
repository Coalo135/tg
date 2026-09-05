"""
dataset.py — Montagem do dataset de treino (pares ciclo T -> ciclo T+1).

Esta é a peça mais delicada do módulo: cada linha vira "um município num ciclo T",
com features calculadas SOMENTE com informação de ciclos <= T, e alvo = IDEB em T+1.

Regra de ouro anti-vazamento: nenhuma feature usa dado de ciclo posterior a T.
Única exceção permitida: a meta projetada do INEP para T+1 (publicada ANTES do ciclo
acontecer, logo é informação legítima disponível em T).

Como o IDEB é bienal, T+1 = T + 2 anos e T-1 = T - 2 anos (`config.PASSO_CICLO`).
"""
import logging
from pathlib import Path

import pandas as pd

from config import PASSO_CICLO
from ML.dados import carregar_base

logger = logging.getLogger(__name__)

# Anos-alvo considerados "pós-pandemia" (o ciclo T+1 caiu em 2021 ou 2023).
ANOS_POS_PANDEMIA = {2021, 2023}

# Features usadas pelos modelos (todas conhecidas em T).
#
# NOTA (decisão guiada pelos dados): `meta_T_mais_1` foi REMOVIDA das features.
# O INEP só projetou metas até 2021 — a meta de 2023 é 100% nula, e não existe meta
# para os ciclos seguintes. Usá-la como feature obrigatória zeraria a rodada de teste
# de 2023 e impossibilitaria a projeção do próximo ciclo (o produto final). A meta
# permanece na tabela apenas para o VEREDITO (comparar a previsão com a meta), não
# como entrada do modelo.
FEATURES = [
    "ideb_T",
    "ideb_T_menos_1",
    "variacao_ideb",
    "rendimento_T",
    "saeb_T",
    "flag_pos_pandemia",
]
# Coluna auxiliar mantida no dataset para o veredito, fora das features do modelo.
COLUNA_META = "meta_T_mais_1"
ALVO = "ideb_alvo"

CACHE_PARES = Path(__file__).resolve().parent / "cache_pares.parquet"


def montar_pares(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Constrói a tabela de pares T -> T+1 por (município, nível), sem vazamento.

    Estratégia vetorizada por deslocamento de ano:
      - `core`   = o ciclo T (features do próprio T).
      - `prev`   = ciclo anterior, com ano += 2 para casar em T  -> vira ideb_T_menos_1.
      - `target` = ciclo seguinte, com ano -= 2 para casar em T  -> vira ideb_alvo/meta.
    """
    if df is None:
        df = carregar_base()

    chave = ["codigo_municipio", "nivel_ensino"]

    core = df[[
        "codigo_municipio", "nivel_ensino", "ano", "nome_entidade", "sigla_uf",
        "ideb", "indicador_rendimento_p", "nota_saeb_media_padronizada_n",
    ]].rename(columns={
        "ano": "ano_T",
        "ideb": "ideb_T",
        "indicador_rendimento_p": "rendimento_T",
        "nota_saeb_media_padronizada_n": "saeb_T",
    })

    # Ciclo anterior: seu ano + PASSO vira o T em que ele é o "T-1".
    prev = df[chave + ["ano", "ideb"]].copy()
    prev["ano_T"] = prev["ano"] + PASSO_CICLO
    prev = prev.drop(columns="ano").rename(columns={"ideb": "ideb_T_menos_1"})

    # Ciclo seguinte (T+1): seu ano - PASSO vira o T que ele prevê.
    target = df[chave + ["ano", "ideb", "meta_projetada"]].copy()
    target["ano_T"] = target["ano"] - PASSO_CICLO
    target = target.rename(columns={"ano": "ano_alvo",
                                    "ideb": "ideb_alvo",
                                    "meta_projetada": "meta_T_mais_1"})

    pares = core.merge(target, on=chave + ["ano_T"], how="inner")  # exige ter T+1
    pares = pares.merge(prev, on=chave + ["ano_T"], how="left")     # T-1 é opcional

    pares["variacao_ideb"] = pares["ideb_T"] - pares["ideb_T_menos_1"]
    pares["flag_pos_pandemia"] = pares["ano_alvo"].isin(ANOS_POS_PANDEMIA).astype(int)

    colunas = (chave + ["nome_entidade", "sigla_uf", "ano_T", "ano_alvo"]
               + FEATURES + [COLUNA_META, ALVO])
    return pares[colunas].sort_values(chave + ["ano_T"]).reset_index(drop=True)


def montar_xy(pares: pd.DataFrame, features: list[str] | None = None,
              verbose: bool = True):
    """Devolve (X, y, pares_limpos) descartando linhas com feature/alvo ausente.

    Descartar (em vez de imputar) é a escolha honesta inicial; o custo é reportado.
    """
    features = features or FEATURES
    usadas = features + [ALVO]
    antes = len(pares)
    limpo = pares.dropna(subset=usadas).copy()
    caidas = antes - len(limpo)
    if verbose and antes:
        logger.info("  pares totais: %d | usados: %d | descartados por ausência: %d (%.1f%%)",
                    antes, len(limpo), caidas, caidas / antes * 100)
    return limpo[features], limpo[ALVO], limpo


def _resumo(pares: pd.DataFrame) -> None:
    print("\n== Dataset de pares T -> T+1 ==")
    print("Total de pares:", len(pares))
    print("Por nível:")
    print(pares.groupby("nivel_ensino", observed=True).size())
    print("\nPares por ano-alvo (é o que a validação temporal vai separar):")
    print(pares.groupby("ano_alvo", observed=True).size())
    print("\nExemplo (5 primeiras linhas):")
    cols = ["codigo_municipio", "nivel_ensino", "ano_T", "ano_alvo",
            "ideb_T", "ideb_T_menos_1", "variacao_ideb", "meta_T_mais_1", "ideb_alvo"]
    print(pares[cols].head().to_string(index=False))
    print("\nCobertura completa das features (sem NaN):")
    montar_xy(pares)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pares = montar_pares()
    pares.to_parquet(CACHE_PARES, index=False)
    _resumo(pares)
