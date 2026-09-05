# Consulta os dados no BD sqlite
#

import json
import logging
import sqlite3

import pandas as pd

from DataBase.conexao import conectar

logger = logging.getLogger(__name__)

COLUNAS_RESULTADO = (
    "id", "abrangencia", "nivel_ensino", "ano", "rede",
    "codigo_entidade", "nome_entidade", "sigla_uf",
    "codigo_municipio", "codigo_escola",
    "taxa_aprovacao_total", "indicador_rendimento_p",
    "nota_saeb_matematica", "nota_saeb_portugues",
    "nota_saeb_media_padronizada_n", "ideb", "meta_projetada",
    "taxa_aprovacao_por_serie",
)

# Só estas colunas podem ser usadas como filtro.
FILTROS_PERMITIDOS = frozenset({
    "abrangencia", "nivel_ensino", "ano", "rede",
    "codigo_entidade", "sigla_uf", "codigo_municipio", "codigo_escola",
})

# Colunas TEXT no banco: um código vindo como int (5300108) não casaria com o
# TEXT gravado ('5300108'), e a consulta voltaria vazia sem erro nenhum.
FILTROS_TEXTO = frozenset({
    "codigo_municipio", "codigo_escola", "codigo_entidade", "sigla_uf",
})

COLUNAS_NUMERICAS = (
    "taxa_aprovacao_total", "indicador_rendimento_p",
    "nota_saeb_matematica", "nota_saeb_portugues",
    "nota_saeb_media_padronizada_n", "ideb", "meta_projetada",
)


def _montar_where(filtros: dict) -> tuple[str, list]:
    """ Traduz {coluna: valor} em `WHERE ... AND ...` + lista de parâmetros.
        Um valor de lista/tupla vira `IN (?, ?, ...)`, o que permite `ano=[2019, 2021]`
        numa consulta só em vez de uma consulta por ano.
    """
    clausulas, parametros = [], []

    for coluna, valor in filtros.items():
        if valor is None:
            continue
        if coluna not in FILTROS_PERMITIDOS:
            raise ValueError(
                f"Filtro inválido: {coluna!r}. "
                f"Permitidos: {', '.join(sorted(FILTROS_PERMITIDOS))}"
            )

        if isinstance(valor, (list, tuple, set)):
            valores = [str(v) if coluna in FILTROS_TEXTO else v for v in valor]
            if not valores:
                continue
            clausulas.append(f"{coluna} IN ({', '.join('?' * len(valores))})")
            parametros.extend(valores)
        else:
            if coluna in FILTROS_TEXTO:
                valor = str(valor)
            clausulas.append(f"{coluna} = ?")
            parametros.append(valor)

    where = f" WHERE {' AND '.join(clausulas)}" if clausulas else ""
    return where, parametros


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Garante os tipos que o módulo Estatística espera."""
    for coluna in COLUNAS_NUMERICAS:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    if "ano" in df.columns:
        df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    return df


def buscar_resultados(
    nivel_ensino=None, abrangencia=None, ano=None,
    sigla_uf=None, codigo_municipio=None, codigo_escola=None,
    rede=None, limite: int | None = None, as_dataframe: bool = True,
):
    """Consulta `ideb_resultados` aplicando os filtros informados.

    Filtros com valor None são ignorados. `ano` aceita um inteiro ou uma lista
    de anos. Sem nenhum filtro, devolve a tabela inteira — cabe a quem chama
    decidir se isso faz sentido (a API exige ao menos um; ver API/rotas/_util.py).

    Devolve um DataFrame com as colunas de COLUNAS_RESULTADO — inclusive quando
    não há resultado, para que quem consome possa acessar `df["ideb"]` sem antes
    checar se o DataFrame está vazio.
    """
    filtros = {
        "nivel_ensino": nivel_ensino,
        "abrangencia": abrangencia,
        "ano": ano,
        "sigla_uf": sigla_uf,
        "codigo_municipio": codigo_municipio,
        "codigo_escola": codigo_escola,
        "rede": rede,
    }
    where, parametros = _montar_where(filtros)

    sql = f"SELECT {', '.join(COLUNAS_RESULTADO)} FROM ideb_resultados{where} ORDER BY id"
    if limite is not None:
        sql += " LIMIT ?"
        parametros.append(limite)

    with conectar(exigir_existente=True) as conexao:
        df = pd.read_sql_query(sql, conexao, params=parametros)

    if df.empty:
        logger.warning("Nenhum registro encontrado para esses filtros.")
        df = pd.DataFrame(columns=list(COLUNAS_RESULTADO))

    df = _normalizar(df)

    if as_dataframe:
        return df
    # taxa_aprovacao_por_serie é TEXT com JSON dentro; quem pede dict quer o JSON
    # já desserializado (é o que a API devolve para o front-end).
    registros = df.to_dict(orient="records")
    for registro in registros:
        bruto = registro.get("taxa_aprovacao_por_serie")
        if isinstance(bruto, str):
            registro["taxa_aprovacao_por_serie"] = json.loads(bruto)
    return registros


def buscar_evolucao_ideb(anos, **filtros) -> dict[int, pd.DataFrame]:
    """Série histórica: mesmo filtro em vários anos, no formato {ano: DataFrame}.

    Aceita os mesmos parâmetros de `buscar_resultados`, exceto `ano` — que vem de
    `anos`. Anos sem nenhum registro ficam de fora do resultado.

    Uma consulta só com `ano IN (...)`, particionada depois em memória: a versão
    anterior fazia uma ida ao banco por ano, o que na prática relia o mesmo índice
    N vezes. É a base do gráfico de evolução temporal.
    """
    filtros.pop("ano", None)
    anos = list(anos)
    if not anos:
        return {}

    df = buscar_resultados(ano=anos, **filtros)
    if df.empty:
        return {}

    return {
        int(ano): grupo.reset_index(drop=True)
        for ano, grupo in df.groupby("ano", sort=True)
        if pd.notna(ano)
    }


# --------------------------------------------------------------------- filtros
# Funções que alimentam os seletores da interface. Consultam as tabelas de
# dimensão (municipios/escolas), que são pequenas, em vez de fazer DISTINCT sobre
# as ~1,3 milhão de linhas da tabela fato.

def buscar_municipios(sigla_uf: str | None = None) -> list[dict]:
    """Lista municípios, opcionalmente de uma UF, em ordem alfabética."""
    sql = "SELECT codigo_municipio, nome_municipio, sigla_uf FROM municipios"
    parametros: list = []
    if sigla_uf:
        sql += " WHERE sigla_uf = ?"
        parametros.append(sigla_uf)
    sql += " ORDER BY nome_municipio"

    with conectar(exigir_existente=True) as conexao:
        conexao.row_factory = sqlite3.Row
        return [dict(linha) for linha in conexao.execute(sql, parametros)]


def buscar_escolas(codigo_municipio: str | None = None,
                   sigla_uf: str | None = None) -> list[dict]:
    """Lista escolas de um município ou de uma UF, em ordem alfabética.

    Exige ao menos um dos dois filtros: são ~85 mil escolas, e devolver todas de
    uma vez para popular um seletor não é utilizável na interface.
    """
    if not codigo_municipio and not sigla_uf:
        raise ValueError("Informe codigo_municipio ou sigla_uf para listar escolas.")

    clausulas, parametros = [], []
    if codigo_municipio:
        clausulas.append("codigo_municipio = ?")
        parametros.append(str(codigo_municipio))
    if sigla_uf:
        clausulas.append("sigla_uf = ?")
        parametros.append(sigla_uf)

    sql = (
        "SELECT codigo_escola, nome_escola, codigo_municipio, sigla_uf FROM escolas"
        f" WHERE {' AND '.join(clausulas)} ORDER BY nome_escola"
    )
    with conectar(exigir_existente=True) as conexao:
        conexao.row_factory = sqlite3.Row
        return [dict(linha) for linha in conexao.execute(sql, parametros)]


def buscar_ufs() -> list[str]:
    """Siglas de UF presentes no banco, em ordem."""
    with conectar(exigir_existente=True) as conexao:
        linhas = conexao.execute(
            "SELECT DISTINCT sigla_uf FROM municipios WHERE sigla_uf IS NOT NULL"
            " ORDER BY sigla_uf"
        )
        return [linha[0] for linha in linhas]


def anos_disponiveis(**filtros) -> list[int]:
    """Anos com dado para o filtro dado — evita oferecer um ano que virá vazio."""
    where, parametros = _montar_where(filtros)
    sql = f"SELECT DISTINCT ano FROM ideb_resultados{where} ORDER BY ano"
    with conectar(exigir_existente=True) as conexao:
        return [linha[0] for linha in conexao.execute(sql, parametros)]
