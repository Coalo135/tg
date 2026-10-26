"""
main.py — Aplicação FastAPI: monta os routers e expõe a rota de ingestão.

    uvicorn API.main:app --reload  (a partir de TG/)

Documentação interativa em /docs.
"""
import logging

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from API.rotas import dados, estatisticas, modelos
from Dados.inep_download import baixar_planilha
from Dados.planilhas import PLANILHAS, por_chave

logger = logging.getLogger(__name__)

app = FastAPI(
    title="IDEB API",
    description=("Consulta, estatísticas e modelos (INSE × IDEB, clusterização) "
                 "sobre os dados do IDEB (INEP)."),
)

# Permissivo de propósito (projeto acadêmico, sem front-end em produção ainda).
# Se isso for pra produção algum dia, troque "*" pela origem real do front-end.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dados.router)
app.include_router(estatisticas.router)
app.include_router(modelos.router)


@app.get("/planilhas", tags=["ingestao"])
def listar_planilhas() -> list[dict]:
    """Catálogo das planilhas e o que já está em disco."""
    return [
        {
            "chave": p.chave,
            "arquivo": f"{p.base}.xlsx",
            "abrangencia": p.abrangencia,
            "nivel_ensino": p.nivel_ensino,
            "layout": p.layout,
            "zip_disponivel": p.zip.exists(),
            "xlsx_disponivel": p.xlsx.exists(),
        }
        for p in PLANILHAS
    ]


@app.get("/baixar", tags=["ingestao"])
def baixar(chave: str) -> dict[str, str]:
    """Baixa uma planilha do INEP e deixa o .xlsx pronto em `Planilhas/`.

    Identificada pela chave do catálogo (ex.: `brasil_ideb`) — antes era um índice
    numérico posicional, que apontava para outro arquivo sempre que a ordem da
    lista mudava. As chaves válidas estão em `GET /planilhas`.
    """
    try:
        planilha = por_chave(chave)
    except KeyError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    try:
        caminho = baixar_planilha(planilha)
    except requests.exceptions.SSLError as erro:
        logger.exception("Erro de certificado SSL ao baixar %s", chave)
        raise HTTPException(
            status_code=502, detail="Erro de certificado SSL ao contatar o INEP"
        ) from erro
    except requests.exceptions.RequestException as erro:
        logger.exception("Falha ao baixar %s do INEP", chave)
        raise HTTPException(
            status_code=502, detail="Falha ao baixar o arquivo do INEP"
        ) from erro
    except ValueError as erro:
        raise HTTPException(status_code=502, detail=str(erro)) from erro
    except OSError as erro:
        logger.exception("Falha ao gravar %s em disco", chave)
        raise HTTPException(
            status_code=500, detail="Falha ao gravar o arquivo baixado em disco"
        ) from erro

    return {
        "mensagem": "Planilha baixada e descompactada",
        "chave": planilha.chave,
        "arquivo": str(caminho),
    }
