"""
dados.py — Rotas de consulta bruta e de povoamento dos filtros da interface.

As rotas de filtro (`/ufs`, `/municipios`, `/escolas`, `/anos`) existem para que a
interface monte os seletores sem precisar baixar a tabela de resultados inteira só
para descobrir quais valores existem.
"""
from fastapi import APIRouter, HTTPException

from Dados.consulta_ideb import (
    anos_disponiveis,
    buscar_escolas,
    buscar_municipios,
    buscar_resultados,
    buscar_ufs,
)

from ._util import filtros_obrigatorios

router = APIRouter(tags=["dados"])


@router.get("/ufs")
def listar_ufs() -> list[str]:
    """Siglas de UF presentes no banco."""
    return buscar_ufs()


@router.get("/municipios")
def listar_municipios(sigla_uf: str | None = None) -> list[dict]:
    """Lista municípios, opcionalmente filtrando por UF."""
    return buscar_municipios(sigla_uf=sigla_uf)


@router.get("/escolas")
def listar_escolas(codigo_municipio: str | None = None,
                   sigla_uf: str | None = None) -> list[dict]:
    """Lista escolas de um município ou UF. Exige ao menos um dos dois."""
    try:
        return buscar_escolas(codigo_municipio=codigo_municipio, sigla_uf=sigla_uf)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@router.get("/anos")
def listar_anos(nivel_ensino: str | None = None,
                abrangencia: str | None = None,
                sigla_uf: str | None = None,
                codigo_municipio: str | None = None,
                codigo_escola: str | None = None) -> list[int]:
    """Anos com dado para o filtro dado — evita oferecer um ano que virá vazio."""
    filtros = {
        k: v for k, v in dict(
            nivel_ensino=nivel_ensino, abrangencia=abrangencia, sigla_uf=sigla_uf,
            codigo_municipio=codigo_municipio, codigo_escola=codigo_escola,
        ).items() if v is not None
    }
    return anos_disponiveis(**filtros)


@router.get("/resultados")
def listar_resultados(
    nivel_ensino: str | None = None,
    abrangencia: str | None = None,
    ano: int | None = None,
    sigla_uf: str | None = None,
    codigo_municipio: str | None = None,
    codigo_escola: str | None = None,
    rede: str | None = None,
    limite: int | None = None,
) -> list[dict]:
    """Resultados brutos do IDEB pro filtro dado (exige ao menos um filtro).

    Para agregados prontos pra gráfico, prefira /estatisticas, /comparacao-meta
    ou /evolucao — esta rota devolve linha a linha, sem processamento.
    `taxa_aprovacao_por_serie` sai como objeto JSON, já desserializado.
    """
    filtros = filtros_obrigatorios(
        nivel_ensino=nivel_ensino, abrangencia=abrangencia, ano=ano, sigla_uf=sigla_uf,
        codigo_municipio=codigo_municipio, codigo_escola=codigo_escola, rede=rede,
    )
    return buscar_resultados(**filtros, limite=limite, as_dataframe=False)
