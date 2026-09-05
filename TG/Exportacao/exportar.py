"""
exportar.py — Camada de exportação: grava os resultados do módulo Estatística em CSV.

Decisão de design: dados ausentes NÃO são omitidos da exportação. Municípios/escolas
com poucos alunos no SAEB não recebem IDEB (fica ausente no banco) — omitir a linha
esconderia que o dado foi coletado mas é insuficiente; tratar como zero inventaria uma
nota que não existe. Por isso a linha permanece, com o texto explícito abaixo.
"""
from pathlib import Path

import pandas as pd

TEXTO_DADO_AUSENTE = "sem dado suficiente"


def exportar_para_csv(df, caminho_saida, coluna_ideb="ideb"):
    """Exporta `df` para CSV, marcando `coluna_ideb` ausente com TEXTO_DADO_AUSENTE."""
    df_exportado = df.copy()
    df_exportado[coluna_ideb] = df_exportado[coluna_ideb].apply(
        lambda v: TEXTO_DADO_AUSENTE if pd.isna(v) else v
    )

    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    df_exportado.to_csv(caminho_saida, index=False)
    return str(caminho_saida)
