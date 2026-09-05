"""
validacao.py — Validação temporal (nunca shuffle) + métricas MAE/RMSE.

Validação aleatória vazaria futuro para o treino. Aqui o corte é por ANO-ALVO:
treina com tudo até um ciclo, testa no ciclo seguinte, e repete deslocando a
janela. Com a cobertura atual (alvos de 2007 até o último ciclo divulgado), as
três últimas rodadas são, por exemplo:

    Rodada 1: treina ano_alvo <= 2019, testa ano_alvo == 2021
    Rodada 2: treina ano_alvo <= 2021, testa ano_alvo == 2023
    Rodada 3: treina ano_alvo <= 2023, testa ano_alvo == 2025

As rodadas eram uma lista fixa `[(2017, 2019), (2019, 2021), (2021, 2023)]`. Com a
divulgação de 2025 essa lista passou a ignorar o ciclo mais recente — justamente o
mais informativo para escolher o modelo. Agora elas são derivadas dos anos-alvo
que existem no dataset.

Roda separadamente por nível (anos_iniciais / anos_finais), como decidido no design.
"""
import logging
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from ML.dados import NIVEIS
from ML.dataset import FEATURES, montar_pares, montar_xy
from ML.modelos import criar_modelos

logger = logging.getLogger(__name__)

N_RODADAS = 3  # quantos ciclos mais recentes servem de teste


def montar_rodadas(pares: pd.DataFrame, n: int = N_RODADAS) -> list[tuple[int, int]]:
    """(ano-alvo máximo do treino, ano-alvo de teste) para os n ciclos mais recentes.

    Descarta o primeiro ano-alvo do dataset: usá-lo como teste deixaria o treino
    vazio, já que não há nada anterior a ele.
    """
    anos = sorted(int(a) for a in pares["ano_alvo"].dropna().unique())
    candidatos = anos[1:]
    return [(anos[anos.index(ano) - 1], ano) for ano in candidatos[-n:]]


def _avaliar_rodada(modelo, treino: pd.DataFrame, teste: pd.DataFrame):
    Xtr, ytr, _ = montar_xy(treino, FEATURES, verbose=False)
    Xte, yte, _ = montar_xy(teste, FEATURES, verbose=False)
    if len(Xtr) == 0 or len(Xte) == 0:
        return None
    modelo.fit(Xtr, ytr)
    pred = modelo.predict(Xte)
    return {
        "mae": mean_absolute_error(yte, pred),
        "rmse": root_mean_squared_error(yte, pred),
        "n_treino": len(Xtr),
        "n_teste": len(Xte),
    }


def validar(pares: pd.DataFrame, rodadas: list[tuple[int, int]] | None = None) -> pd.DataFrame:
    """Roda todos os modelos em todas as rodadas, por nível. Devolve a tabela."""
    rodadas = rodadas or montar_rodadas(pares)
    logger.info("Rodadas de validação (treino <= X, testa em Y): %s", rodadas)

    linhas = []
    for nivel in NIVEIS:
        sub = pares[pares["nivel_ensino"] == nivel]
        for nome_modelo in criar_modelos():
            maes, rmses = [], []
            for treino_max, ano_teste in rodadas:
                treino = sub[sub["ano_alvo"] <= treino_max]
                teste = sub[sub["ano_alvo"] == ano_teste]
                # instância nova por rodada (evita reaproveitar estado do fit)
                modelo = criar_modelos()[nome_modelo]
                r = _avaliar_rodada(modelo, treino, teste)
                if r:
                    maes.append(r["mae"])
                    rmses.append(r["rmse"])
            if maes:
                linhas.append({
                    "nivel": nivel,
                    "modelo": nome_modelo,
                    "MAE": np.mean(maes),
                    "RMSE": np.mean(rmses),
                    "rodadas": len(maes),
                })
    return pd.DataFrame(linhas)


def _formatar(tabela: pd.DataFrame) -> None:
    print("\n== Resultado da validação temporal (média das rodadas) ==")
    for nivel in NIVEIS:
        bloco = (tabela[tabela["nivel"] == nivel]
                 .sort_values("MAE")
                 .assign(MAE=lambda d: d["MAE"].round(3),
                         RMSE=lambda d: d["RMSE"].round(3)))
        if bloco.empty:
            continue
        print(f"\n--- {nivel} ---")
        print(bloco[["modelo", "MAE", "RMSE", "rodadas"]].to_string(index=False))

        base = bloco[bloco["modelo"] == "baseline"]
        if not base.empty:
            mae_base = base["MAE"].iloc[0]
            melhor = bloco.iloc[0]
            ganho = (mae_base - melhor["MAE"]) / mae_base * 100
            print(f"  Baseline MAE={mae_base:.3f} | melhor: {melhor['modelo']} "
                  f"MAE={melhor['MAE']:.3f} ({ganho:+.1f}% vs baseline)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    warnings.filterwarnings("ignore")
    _formatar(validar(montar_pares()))
