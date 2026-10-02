"""
modelos.py — Rotas que expõem o modelo de `Modelos/` (K-means) ao front-end.

O modelo é calculado sob demanda a partir do banco e fica em cache no
processo por (nível, ano): leva ~2 s na primeira chamada, depois é
instantâneo. Nada é lido de `Modelos/saidas/` — a API não depende de
alguém ter rodado os scripts antes.

Rotas:
    GET /modelos/anos                            anos com INSE (o front não crava ano)
    GET /modelos/agrupamento?nivel_ensino=       clusters, perfil, outliers, municípios

`ano` é opcional nas duas: sem ele, vale o ano mais recente com INSE. `sigla_uf`
recorta só a lista devolvida — os grupos são sempre nacionais.
"""
import json
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, HTTPException

from config import NIVEIS_ENSINO
from DataBase.conexao import BancoNaoEncontrado
from Modelos import agrupamento
from Modelos.dados import anos_disponiveis

router = APIRouter(prefix="/modelos", tags=["modelos"])

COLUNAS_AGRUPAMENTO = (
    "cluster", "codigo_municipio", "nome_municipio", "sigla_uf",
    "media_inse", "ideb", "indicador_rendimento_p", "nota_saeb_media_padronizada_n",
    "acima_do_grupo",
)


def _registros(df: pd.DataFrame, colunas=None) -> list[dict]:
    """DataFrame -> lista de dicts com tipos nativos e NaN como null."""
    if colunas is not None:
        df = df[list(colunas)]
    # 4 casas bastam para qualquer exibição e cortam ~15% do payload (rendimento e
    # SAEB chegam do banco com 6 casas)
    return json.loads(df.round(4).to_json(orient="records", force_ascii=False))


@lru_cache(maxsize=16)
def calcular_agrupamento(nivel_ensino: str, ano: int):
    return agrupamento.calcular(nivel_ensino, ano)


def _resolver(nivel_ensino: str, ano: int | None) -> int:
    """Valida o nível, resolve o ano (default: o mais recente com INSE)."""
    if nivel_ensino not in NIVEIS_ENSINO:
        raise HTTPException(
            status_code=400, detail=f"nivel_ensino deve ser um de {list(NIVEIS_ENSINO)}"
        )
    try:
        anos = anos_disponiveis()
    except BancoNaoEncontrado as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    if not anos:
        raise HTTPException(status_code=503, detail="O INSE ainda não foi importado.")
    if ano is None:
        return max(anos)
    if ano not in anos:
        raise HTTPException(
            status_code=404, detail=f"Sem INSE para {ano}. Anos com INSE: {anos}"
        )
    return ano


def _recortar(df: pd.DataFrame, sigla_uf: str | None) -> pd.DataFrame:
    return df if not sigla_uf else df[df["sigla_uf"] == sigla_uf.upper()]


@router.get("/anos")
def anos_modelos() -> list[int]:
    """Anos com INSE no banco — os únicos em que o modelo existe."""
    try:
        return anos_disponiveis()
    except BancoNaoEncontrado as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro


@router.get("/agrupamento")
def agrupar(nivel_ensino: str, ano: int | None = None, sigla_uf: str | None = None) -> dict:
    """K-means dos municípios, com o k escolhido pela silhueta."""
    ano = _resolver(nivel_ensino, ano)
    resultado = calcular_agrupamento(nivel_ensino, ano)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Sem base para agrupar nesse nível/ano.")
    return {
        "nivel_ensino": nivel_ensino,
        "ano": ano,
        "k": resultado["k"],
        "descartes": resultado["descartes"],
        "avaliacao": _registros(resultado["avaliacao"]),
        "perfil": _registros(resultado["perfil"].reset_index()),
        "outliers": _registros(resultado["outliers"], COLUNAS_AGRUPAMENTO),
        "total": int(len(resultado["municipios"])),
        "municipios": _registros(
            _recortar(resultado["municipios"], sigla_uf), COLUNAS_AGRUPAMENTO
        ),
    }

