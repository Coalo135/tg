"""
main.py — Aplicação FastAPI: monta os routers e expõe a rota de ingestão.

    uvicorn API.main:app --reload      (a partir de TG/)

Documentação interativa em /docs.
"""
import logging

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from API.rotas import dados, estatisticas, previsao
from config import PASTA_PLANILHAS
from Dados.descompactar import extrair_xlsx_de_zip
from Dados.planilhas import PLANILHAS, por_chave

logger = logging.getLogger(__name__)

app = FastAPI(
    title="IDEB API",
    description="Consulta, estatísticas e previsão sobre os dados do IDEB (INEP).",
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
app.include_router(previsao.router)

URL_INEP = "https://download.inep.gov.br/ideb/resultados/"

# Os downloads do INEP vão para uma subpasta própria. Os .zip de `Planilhas/` são
# os arquivos versionados no git (partes OOXML recomprimidas); gravar o download
# do INEP com o mesmo nome sobrescreveria o arquivo do repositório.
PASTA_DOWNLOADS = PASTA_PLANILHAS / "downloads"


@app.get("/planilhas", tags=["ingestao"])
def listar_planilhas() -> list[dict]:
    """Catálogo das planilhas de divulgação e o que já está em disco."""
    return [
        {
            "chave": p.chave,
            "arquivo": f"{p.base}.xlsx",
            "abrangencia": p.abrangencia,
            "nivel_ensino": p.nivel_ensino,
            "zip_disponivel": p.zip.exists(),
            "xlsx_disponivel": p.xlsx.exists(),
        }
        for p in PLANILHAS
    ]


@app.get("/baixar", tags=["ingestao"])
def baixar_planilha(chave: str) -> dict[str, str]:
    """Baixa uma planilha do INEP e deixa o .xlsx pronto em `Planilhas/`.

    Identificada pela chave do catálogo (ex.: `brasil_ideb`) — antes era um índice
    numérico posicional, que apontava para outro arquivo sempre que a ordem da
    lista mudava. As chaves válidas estão em `GET /planilhas`.
    """
    try:
        planilha = por_chave(chave)
    except KeyError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    nome_zip = f"{planilha.base}.zip"
    destino_zip = PASTA_DOWNLOADS / nome_zip

    try:
        resposta = requests.get(
            URL_INEP + nome_zip,
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
            timeout=60,
        )
        resposta.raise_for_status()

        PASTA_DOWNLOADS.mkdir(parents=True, exist_ok=True)
        with open(destino_zip, "wb") as arquivo:
            for pedaco in resposta.iter_content(chunk_size=8192):
                if pedaco:
                    arquivo.write(pedaco)

    except requests.exceptions.SSLError as erro:
        logger.exception("Erro de certificado SSL ao baixar %s", nome_zip)
        raise HTTPException(
            status_code=502, detail="Erro de certificado SSL ao contatar o INEP"
        ) from erro
    except requests.exceptions.RequestException as erro:
        logger.exception("Falha ao baixar %s do INEP", nome_zip)
        raise HTTPException(
            status_code=502, detail="Falha ao baixar o arquivo do INEP"
        ) from erro
    except OSError as erro:
        logger.exception("Falha ao gravar %s em disco", nome_zip)
        raise HTTPException(
            status_code=500, detail="Falha ao gravar o arquivo baixado em disco"
        ) from erro

    if not extrair_xlsx_de_zip(destino_zip, planilha.xlsx):
        raise HTTPException(
            status_code=502, detail=f"Nenhum .xlsx dentro de {nome_zip}"
        )

    return {
        "mensagem": "Planilha baixada e descompactada",
        "chave": planilha.chave,
        "arquivo": str(planilha.xlsx),
    }
