"""
consulta_inse.py — Consultas sobre o INSE e sobre o par INSE × IDEB por município.

O par é o insumo dos dois modelos de `Modelos/`: cada linha é um município num
ano, com o nível socioeconômico dos alunos de um lado e o IDEB (e seus
componentes) do outro, para uma rede e um nível de ensino.

O JOIN parte do INSE (LEFT JOIN): município com INSE mas sem IDEB naquele ano/rede
aparece com `ideb` nulo em vez de sumir — quem analisa decide o que fazer com ele
e consegue contar quantos são.
"""
import logging

import pandas as pd

from DataBase.conexao import conectar

logger = logging.getLogger(__name__)

NIVEIS_INSE = tuple(f"pc_nivel_{i}" for i in range(1, 9))

COLUNAS_INSE = (
    "ano", "codigo_municipio", "sigla_uf", "rede", "localizacao", "capital",
    "qtd_alunos", "media_inse", *NIVEIS_INSE,
)

COLUNAS_PAR = (
    "ano", "codigo_municipio", "nome_municipio", "sigla_uf", "rede", "capital",
    "qtd_alunos", "media_inse", "nivel_ensino", "ideb",
    "indicador_rendimento_p", "nota_saeb_media_padronizada_n",
    "taxa_aprovacao_total", "meta_projetada",
)

COLUNAS_NUMERICAS = (
    "qtd_alunos", "media_inse", *NIVEIS_INSE, "ideb",
    "indicador_rendimento_p", "nota_saeb_media_padronizada_n",
    "taxa_aprovacao_total", "meta_projetada",
)


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    for coluna in COLUNAS_NUMERICAS:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    for coluna in ("ano", "capital"):
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
    return df


def _clausulas(**filtros) -> tuple[str, list]:
    """`{coluna_qualificada: valor}` -> ' AND col = ?' ... ; None é ignorado."""
    partes, parametros = [], []
    for coluna, valor in filtros.items():
        if valor is None:
            continue
        partes.append(f" AND {coluna} = ?")
        # colunas TEXT: um código vindo como int não casaria com o '5300108' gravado
        texto = coluna.endswith(("codigo_municipio", "sigla_uf"))
        parametros.append(str(valor) if texto else valor)
    return "".join(partes), parametros


def anos_inse() -> list[int]:
    """Anos com INSE no banco — para nenhum modelo cravar ciclo no código."""
    with conectar(exigir_existente=True) as conexao:
        linhas = conexao.execute("SELECT DISTINCT ano FROM inse_municipios ORDER BY ano")
        return [int(a) for (a,) in linhas]


def buscar_inse(ano=None, sigla_uf=None, codigo_municipio=None,
                rede=None, localizacao=None) -> pd.DataFrame:
    """Linhas de `inse_municipios` com os filtros informados (None é ignorado)."""
    where, parametros = _clausulas(ano=ano, sigla_uf=sigla_uf, codigo_municipio=codigo_municipio,
                                   rede=rede, localizacao=localizacao)
    sql = (f"SELECT {', '.join(COLUNAS_INSE)} FROM inse_municipios WHERE 1=1{where}"
           " ORDER BY ano, codigo_municipio, rede, localizacao")
    with conectar(exigir_existente=True) as conexao:
        df = pd.read_sql_query(sql, conexao, params=parametros)
    if df.empty:
        df = pd.DataFrame(columns=list(COLUNAS_INSE))
    return _normalizar(df)


def buscar_inse_ideb(nivel_ensino: str, ano=None, rede: str = "Pública",
                     localizacao: str = "Total", sigla_uf=None) -> pd.DataFrame:
    """Par INSE × IDEB por município: uma linha por (ano, município).

    O IDEB é casado por (ano, município, rede); `localizacao` recorta só o INSE,
    porque o IDEB municipal não distingue urbana/rural. Com `ano=None` vêm todos
    os anos em que há INSE.

    O município entra pelo `codigo_entidade` (que, na abrangência município, é o
    próprio código IBGE) e não pelo `codigo_municipio`: assim o JOIN cai inteiro no
    índice único de ideb_resultados (abrangencia, nivel_ensino, ano, codigo_entidade,
    rede). Por `codigo_municipio` o SQLite usava um índice sem o município e varria
    ~5.500 linhas por município — 55 s por consulta em vez de 0,03 s.
    """
    where, parametros = _clausulas(**{"i.ano": ano, "i.sigla_uf": sigla_uf})
    sql = f"""
        SELECT i.ano, i.codigo_municipio, m.nome_municipio, i.sigla_uf, i.rede, i.capital,
               i.qtd_alunos, i.media_inse,
               r.nivel_ensino, r.ideb, r.indicador_rendimento_p,
               r.nota_saeb_media_padronizada_n, r.taxa_aprovacao_total, r.meta_projetada
        FROM inse_municipios i
        JOIN municipios m ON m.codigo_municipio = i.codigo_municipio
        LEFT JOIN ideb_resultados r
               ON r.abrangencia = 'municipio'
              AND r.nivel_ensino = ?
              AND r.ano = i.ano
              AND r.codigo_entidade = i.codigo_municipio
              AND r.rede = i.rede
        WHERE i.rede = ? AND i.localizacao = ?{where}
        ORDER BY i.ano, i.codigo_municipio
    """
    with conectar(exigir_existente=True) as conexao:
        df = pd.read_sql_query(sql, conexao, params=[nivel_ensino, rede, localizacao, *parametros])
    if df.empty:
        logger.warning("Nenhum par INSE x IDEB para nivel=%s rede=%s", nivel_ensino, rede)
        df = pd.DataFrame(columns=list(COLUNAS_PAR))
    # a coluna vem nula nas linhas sem IDEB; o valor pedido é o que vale para todas
    df["nivel_ensino"] = nivel_ensino
    return _normalizar(df)
