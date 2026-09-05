"""Pequenos helpers compartilhados entre os módulos de rota deste pacote."""
from fastapi import HTTPException


def filtros_obrigatorios(**filtros) -> dict:
    """Descarta valores None; levanta 400 se nada sobrar.

    Evita que uma chamada sem nenhum filtro devolva a tabela inteira de
    `ideb_resultados` (~1,3 milhão de linhas). No Supabase isso estourava o
    statement timeout do Postgres; em SQLite local não há timeout, o que é pior:
    a consulta completa, materializa tudo em memória e a resposta HTTP fica
    grande demais para o front-end consumir.
    """
    filtros = {k: v for k, v in filtros.items() if v is not None}
    if not filtros:
        raise HTTPException(
            status_code=400,
            detail="Informe ao menos um filtro (ex.: sigla_uf, codigo_municipio, ano).",
        )
    return filtros
