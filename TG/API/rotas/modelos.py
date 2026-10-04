"""
modelos.py — Rotas que expõem os dois modelos de `Modelos/` ao front-end.

Os modelos são calculados sob demanda a partir do banco e ficam em cache no
processo por (nível, ano): o modelo 1 leva ~0,5 s e o 2 ~2 s na primeira chamada,
depois é instantâneo. Nada é lido de `Modelos/saidas/` — a API não depende de
alguém ter rodado os scripts antes.

Rotas:
    GET /modelos/anos                            anos com INSE (o front não crava ano)
    GET /modelos/relacao-inse-ideb?nivel_ensino= ajuste + todos os municípios com resíduo
    GET /modelos/agrupamento?nivel_ensino=       clusters, perfil, outliers, municípios
    GET /modelos/municipio/{codigo}?nivel_ensino= a "previsão" de um município: observado,
                                                 previsto pelo INSE, resíduo, posição, cluster

`ano` é opcional em todas: sem ele, vale o ano mais recente com INSE. `sigla_uf`
recorta só a lista devolvida — o ajuste e o ranking são sempre nacionais.
"""
import json
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, HTTPException

from config import NIVEIS_ENSINO
from DataBase.conexao import BancoNaoEncontrado
from Modelos import agrupamento, relacao_inse_ideb
from Modelos.dados import anos_disponiveis

router = APIRouter(prefix="/modelos", tags=["modelos"])

COLUNAS_RELACAO = (
    "posicao", "codigo_municipio", "nome_municipio", "sigla_uf",
    "media_inse", "ideb", "ideb_previsto", "residuo",
)
COLUNAS_AGRUPAMENTO = (
    "cluster", "codigo_municipio", "nome_municipio", "sigla_uf",
    "media_inse", "ideb", "indicador_rendimento_p", "nota_saeb_media_padronizada_n",
    "ideb_previsto", "residuo",
)


def _registros(df: pd.DataFrame, colunas=None) -> list[dict]:
    """DataFrame -> lista de dicts com tipos nativos e NaN como null."""
    if colunas is not None:
        df = df[list(colunas)]
    # 4 casas bastam para qualquer exibição e cortam ~15% do payload (rendimento e
    # SAEB chegam do banco com 6 casas)
    return json.loads(df.round(4).to_json(orient="records", force_ascii=False))


@lru_cache(maxsize=16)
def calcular_relacao(nivel_ensino: str, ano: int):
    return relacao_inse_ideb.calcular(nivel_ensino, ano)


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
    """Anos com INSE no banco — os únicos em que os modelos existem."""
    try:
        return anos_disponiveis()
    except BancoNaoEncontrado as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro


@router.get("/relacao-inse-ideb")
def relacao(nivel_ensino: str, ano: int | None = None, sigla_uf: str | None = None) -> dict:
    """Modelo 1: reta IDEB ~ INSE e o resíduo de cada município.

    `municipios` vem ordenado por resíduo decrescente; `posicao` é o lugar no
    ranking nacional (1 = entrega mais acima do que o INSE preveria).
    """
    ano = _resolver(nivel_ensino, ano)
    resultado = calcular_relacao(nivel_ensino, ano)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Sem base para ajustar nesse nível/ano.")
    return {
        "nivel_ensino": nivel_ensino,
        "ano": ano,
        "ajuste": resultado["ajuste"],
        "descartes": resultado["descartes"],
        "total": int(len(resultado["municipios"])),
        "municipios": _registros(_recortar(resultado["municipios"], sigla_uf), COLUNAS_RELACAO),
    }


@router.get("/agrupamento")
def agrupar(nivel_ensino: str, ano: int | None = None, sigla_uf: str | None = None) -> dict:
    """Modelo 2: K-means dos municípios, com o k escolhido pela silhueta."""
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


@router.get("/municipio/{codigo_municipio}")
def municipio(codigo_municipio: str, nivel_ensino: str, ano: int | None = None) -> dict:
    """A "previsão" de um município: IDEB observado, previsto pelo INSE, resíduo,
    posição no ranking nacional e o cluster em que ele cai."""
    ano = _resolver(nivel_ensino, ano)
    resultado = calcular_relacao(nivel_ensino, ano)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Sem base para ajustar nesse nível/ano.")

    linhas = resultado["municipios"]
    linha = linhas[linhas["codigo_municipio"] == str(codigo_municipio)]
    if linha.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Município {codigo_municipio} sem par INSE × IDEB em {ano} ({nivel_ensino}).",
        )
    saida = _registros(linha, COLUNAS_RELACAO)[0]
    saida.update({"nivel_ensino": nivel_ensino, "ano": ano, "total": int(len(linhas)),
                  "ajuste": resultado["ajuste"], "cluster": None, "k": None,
                  "cluster_perfil": None})

    grupos = calcular_agrupamento(nivel_ensino, ano)
    if grupos is not None:
        no_grupo = grupos["municipios"]
        no_grupo = no_grupo[no_grupo["codigo_municipio"] == str(codigo_municipio)]
        if not no_grupo.empty:
            cluster = int(no_grupo["cluster"].iloc[0])
            perfil = grupos["perfil"].reset_index()
            saida.update({
                "cluster": cluster,
                "k": grupos["k"],
                "cluster_perfil": _registros(perfil[perfil["cluster"] == cluster])[0],
            })
    return saida
