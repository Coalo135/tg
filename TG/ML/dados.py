"""
dados.py — Carga e limpeza da base de IDEB para o modelo de regressão.

Puxa de `ideb_resultados` apenas o que o modelo precisa: abrangência = município,
rede = Pública (o agregado), níveis anos_iniciais e anos_finais.

O que mudou com a saída do Supabase
-----------------------------------
A versão anterior baixava a base **bloco a bloco (nível × ano)** porque uma
consulta única estourava o statement timeout do Postgres na tabela de 1,27 M
linhas. Esse timeout era da camada HTTP do Supabase; em SQLite local a mesma
seleção é um único SELECT com índice, e o laço de blocos deixou de fazer sentido.

Os ciclos também deixaram de ser uma lista fixa no código. Estavam escritos como
`[2005, ..., 2023]`, o que passou a estar errado quando as planilhas de 2025
entraram: `prever.py` continuaria projetando 2025 a partir de 2023 mesmo com o
2025 real já no banco. Agora `ciclos()` pergunta ao banco quais anos existem.

Uso:
    from ML.dados import carregar_base
    df = carregar_base()              # usa cache se estiver atualizado
    df = carregar_base(forcar=True)   # relê do banco
"""
import logging
from pathlib import Path

import pandas as pd

import config
from config import PASSO_CICLO
from DataBase.conexao import conectar

logger = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parent / "cache_ideb_municipio.parquet"

# Níveis modelados nesta etapa. ensino_medio fica de fora: só existe a partir de
# 2017, série curta demais para a validação temporal de 3 rodadas.
NIVEIS = ("anos_iniciais", "anos_finais")

ABRANGENCIA = "municipio"
REDE = "Pública"

COLUNAS_NUMERICAS = [
    "ideb",
    "meta_projetada",
    "indicador_rendimento_p",
    "nota_saeb_media_padronizada_n",
    "nota_saeb_matematica",
    "nota_saeb_portugues",
    "taxa_aprovacao_total",
]

COLUNAS_SELECIONADAS = [
    "id",
    "codigo_municipio", "nome_entidade", "sigla_uf",
    "nivel_ensino", "ano", "rede",
] + COLUNAS_NUMERICAS

SQL_BASE = f"""
SELECT {', '.join(COLUNAS_SELECIONADAS)}
FROM ideb_resultados
WHERE abrangencia = ?
  AND rede = ?
  AND nivel_ensino IN ({', '.join('?' * len(NIVEIS))})
ORDER BY codigo_municipio, nivel_ensino, ano
"""


def ciclos(df: pd.DataFrame | None = None) -> list[int]:
    """Anos de ciclo presentes na base, em ordem crescente.

    Lido dos dados em vez de fixado no código: quando o INEP divulga um ciclo
    novo, basta reimportar as planilhas — nada aqui precisa ser editado.
    """
    if df is not None:
        return sorted(int(a) for a in df["ano"].dropna().unique())
    with conectar(exigir_existente=True) as conexao:
        linhas = conexao.execute(
            "SELECT DISTINCT ano FROM ideb_resultados"
            " WHERE abrangencia = ? AND rede = ? ORDER BY ano",
            (ABRANGENCIA, REDE),
        )
        return [linha[0] for linha in linhas]


def _ler_do_banco() -> pd.DataFrame:
    """Lê municípios (rede Pública) num único SELECT."""
    with conectar(exigir_existente=True) as conexao:
        return pd.read_sql_query(
            SQL_BASE, conexao, params=[ABRANGENCIA, REDE, *NIVEIS]
        )


def _limpar(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos. NaN permanece NaN (ausência real, nunca zero)."""
    for col in COLUNAS_NUMERICAS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["codigo_municipio"] = df["codigo_municipio"].astype(str)
    return df


def _cache_valido() -> bool:
    """Cache só vale se for mais novo que o banco.

    Sem esta checagem, reimportar planilhas novas e rodar a previsão devolveria
    resultados da base antiga sem nenhum aviso — o tipo de erro que não aparece
    em teste, só num número errado no texto final.
    """
    if not CACHE.exists():
        return False
    if not config.DB_PATH.exists():
        return True
    return CACHE.stat().st_mtime >= config.DB_PATH.stat().st_mtime


def carregar_base(forcar: bool = False) -> pd.DataFrame:
    """Base limpa (município, rede Pública). Usa cache parquet quando atualizado."""
    if _cache_valido() and not forcar:
        return pd.read_parquet(CACHE)

    logger.info("Lendo base de IDEB (município / rede Pública) do SQLite...")
    df = _limpar(_ler_do_banco())
    if df.empty:
        raise ValueError(
            "Nenhum registro de município/rede Pública no banco. "
            "Rode `python -m DataBase.importData` antes."
        )
    df.to_parquet(CACHE, index=False)
    logger.info("Cache salvo em %s (%d linhas).", CACHE, len(df))
    return df


def _resumo(df: pd.DataFrame) -> None:
    print("\n== Resumo da base carregada ==")
    print("Linhas:", len(df))
    print("Municípios distintos:", df["codigo_municipio"].nunique())
    print("Níveis:", sorted(df["nivel_ensino"].unique()))
    print("Ciclos:", ciclos(df), f"(passo de {PASSO_CICLO} anos)")
    print("\nLinhas por (nível, ano) [contagem]:")
    print(df.pivot_table(index="nivel_ensino", columns="ano",
                         values="ideb", aggfunc="count", observed=True).fillna(0).astype(int))
    print("\n% de IDEB ausente (NaN) por nível:")
    ausentes = (df.assign(nulo=df["ideb"].isna())
                  .groupby("nivel_ensino", observed=True)["nulo"].mean().mul(100).round(1))
    print(ausentes)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _resumo(carregar_base(forcar=True))
