"""
previsao.py — Rota de previsão: projeta o IDEB de um município pro próximo ciclo.

Carregar a base e treinar os modelos é caro (leitura do banco + validação temporal
+ treino do scikit-learn). Isso acontece só na primeira chamada do processo; o
resultado fica em cache na memória pras chamadas seguintes.
"""
import logging

from fastapi import APIRouter, HTTPException

from DataBase.conexao import BancoNaoEncontrado
from ML.dados import NIVEIS, carregar_base
from ML.dataset import montar_pares
from ML.prever import escolher_e_treinar, prever_ideb

logger = logging.getLogger(__name__)

router = APIRouter(tags=["previsao"])

_cache: dict = {}


def _modelos():
    """Base + modelos treinados, memoizados no processo."""
    if not _cache:
        logger.info("Primeira chamada: carregando base e treinando modelos...")
        base = carregar_base()
        _cache["base"] = base
        _cache["modelos"] = escolher_e_treinar(montar_pares(base))
    return _cache["base"], _cache["modelos"]


@router.get("/previsao/{codigo_municipio}")
def obter_previsao(codigo_municipio: str, nivel: str) -> dict:
    """Projeta o IDEB do próximo ciclo pro município/nível dados.

    `nivel`: "anos_iniciais" ou "anos_finais" — `ensino_medio` fica de fora porque
    só existe a partir de 2017, série curta demais para a validação temporal.

    Não devolve gráfico (PNG): os valores da resposta já são o que um front-end
    precisa pra desenhar o próprio gráfico (ano-base, ponto projetado, meta de
    referência).
    """
    if nivel not in NIVEIS:
        raise HTTPException(
            status_code=400, detail=f"nivel deve ser um de {NIVEIS}"
        )

    try:
        base, modelos = _modelos()
    except (BancoNaoEncontrado, ValueError) as erro:
        # banco ausente ou vazio é problema de configuração do servidor, não do
        # pedido — 503 diz "tente de novo depois", 404 diria "esse município não
        # existe", que mandaria a depuração para o lado errado.
        raise HTTPException(status_code=503, detail=str(erro)) from erro

    try:
        return prever_ideb(codigo_municipio, nivel, base, modelos, salvar_grafico=False)
    except ValueError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
