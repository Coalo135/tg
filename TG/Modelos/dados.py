"""
dados.py — Prepara o par INSE × IDEB para os modelos.

Uma linha é um município num ano: o nível socioeconômico dos alunos de um lado,
o IDEB e seus componentes do outro. Só entra na análise quem tem os dois; quem
não tem é contado, não escondido — o custo do descarte faz parte do resultado.
"""
import logging

import pandas as pd

from Dados.consulta_inse import anos_inse, buscar_inse_ideb

logger = logging.getLogger(__name__)

# código IBGE dos municípios usados como sanity check contra a literatura
SOBRAL = "2312908"
FORTALEZA = "2304400"


def separar_completos(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fica só com quem tem INSE e IDEB. Devolve também quantos saíram e por quê."""
    sem_inse = df["media_inse"].isna()
    sem_ideb = df["ideb"].isna()
    descartes = {
        "sem INSE": int((sem_inse & ~sem_ideb).sum()),
        "sem IDEB": int((sem_ideb & ~sem_inse).sum()),
        "sem os dois": int((sem_inse & sem_ideb).sum()),
    }
    completos = df[~sem_inse & ~sem_ideb].reset_index(drop=True)
    return completos, descartes


def carregar_pares(nivel_ensino: str, ano: int | None = None, rede: str = "Pública",
                   localizacao: str = "Total") -> tuple[pd.DataFrame, dict[str, int]]:
    """Par INSE × IDEB pronto para modelar, com o relato do que foi descartado."""
    bruto = buscar_inse_ideb(nivel_ensino, ano=ano, rede=rede, localizacao=localizacao)
    completos, descartes = separar_completos(bruto)
    logger.info("%s / %s: %d municípios com par completo, descartados %s",
                nivel_ensino, ano or "todos os anos", len(completos), descartes)
    return completos, descartes


def anos_disponiveis() -> list[int]:
    """Os anos vêm do banco: nenhum ciclo cravado no código."""
    return anos_inse()
