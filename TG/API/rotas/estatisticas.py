"""
estatisticas.py — Rotas de estatísticas agregadas: médias, IDEB x meta, evolução.

Os valores devolvidos aqui já vêm no formato que um front-end consome direto
pra montar gráfico (dict/lista de números) — sem precisar reprocessar o bruto.
"""
from fastapi import APIRouter, HTTPException, Query

from Dados.consulta_ideb import buscar_evolucao_ideb, buscar_resultados
from Estatistica.separacao_valores import (
    aprovacao_geral_media,
    comparar_meta_ideb,
    evolucao_ideb,
    media_municipio,
    saeb_media_matematica,
    saeb_media_nota_padronizada,
    saeb_media_portugues,
    taxa_aprovacao_todas_series,
)

from ._util import filtros_obrigatorios

router = APIRouter(tags=["estatisticas"])


@router.get("/estatisticas")
def obter_estatisticas(
    nivel_ensino: str | None = None,
    abrangencia: str | None = None,
    ano: int | None = None,
    sigla_uf: str | None = None,
    codigo_municipio: str | None = None,
    codigo_escola: str | None = None,
    rede: str | None = None,
) -> dict:
    """Médias agregadas pro filtro dado.

    `taxa_aprovacao_por_serie` já vem pronto pra um gráfico de barra por série;
    `media_municipio` só aparece se `codigo_municipio` for informado.
    """
    filtros = filtros_obrigatorios(
        nivel_ensino=nivel_ensino, abrangencia=abrangencia, ano=ano, sigla_uf=sigla_uf,
        codigo_municipio=codigo_municipio, codigo_escola=codigo_escola, rede=rede,
    )
    df = buscar_resultados(**filtros)
    if df.empty:
        raise HTTPException(
            status_code=404, detail="Nenhum registro encontrado para esses filtros."
        )

    resultado = {
        "taxa_aprovacao_por_serie": taxa_aprovacao_todas_series(df),
        "saeb_matematica": saeb_media_matematica(df),
        "saeb_portugues": saeb_media_portugues(df),
        "saeb_nota_padronizada": saeb_media_nota_padronizada(df),
        "aprovacao_geral": aprovacao_geral_media(df),
    }
    if codigo_municipio:
        resultado["media_municipio"] = media_municipio(df, codigo_municipio)
    return resultado


@router.get("/comparacao-meta")
def obter_comparacao_meta(
    nivel_ensino: str | None = None,
    abrangencia: str | None = None,
    ano: int | None = None,
    sigla_uf: str | None = None,
    codigo_municipio: str | None = None,
    codigo_escola: str | None = None,
    rede: str | None = None,
) -> dict:
    """IDEB observado vs meta projetada do INEP.

    `resumo` serve pra um KPI/gráfico de pizza (quantos atingiram a meta);
    `detalhes` é a lista linha a linha, pra tabela ou gráfico de dispersão.
    """
    filtros = filtros_obrigatorios(
        nivel_ensino=nivel_ensino, abrangencia=abrangencia, ano=ano, sigla_uf=sigla_uf,
        codigo_municipio=codigo_municipio, codigo_escola=codigo_escola, rede=rede,
    )
    df = buscar_resultados(**filtros)
    detalhes = comparar_meta_ideb(df)
    atingiram = sum(1 for d in detalhes if d["atingiu_meta"])
    return {
        "resumo": {
            "total": len(detalhes),
            "atingiram_meta": atingiram,
            "nao_atingiram_meta": len(detalhes) - atingiram,
        },
        "detalhes": detalhes,
    }


@router.get("/evolucao")
def obter_evolucao(
    anos: list[int] = Query(...),
    nivel_ensino: str | None = None,
    abrangencia: str | None = None,
    sigla_uf: str | None = None,
    codigo_municipio: str | None = None,
    codigo_escola: str | None = None,
    rede: str | None = None,
) -> list[dict]:
    """Série histórica do IDEB médio por ano (ex.: ?anos=2019&anos=2021&anos=2023),
    pronta pro gráfico de linha (evolução temporal)."""
    filtros = {
        k: v
        for k, v in dict(
            nivel_ensino=nivel_ensino, abrangencia=abrangencia, sigla_uf=sigla_uf,
            codigo_municipio=codigo_municipio, codigo_escola=codigo_escola, rede=rede,
        ).items()
        if v is not None
    }
    series_por_ano = buscar_evolucao_ideb(anos, **filtros)
    evolucao = evolucao_ideb(series_por_ano)
    return [{"ano": ano, "ideb_medio": ideb} for ano, ideb in evolucao.items()]
