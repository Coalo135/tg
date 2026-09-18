"""
importData.py — ETL: planilhas de divulgação do IDEB (INEP) -> banco SQLite.

Layout confirmado nas 8 planilhas:
    linhas 1-6  : títulos e notas do MEC/INEP (descartadas)
    linha  7    : rótulo do bloco (ex.: 'Taxa de Aprovação - 2005'), célula
                  mesclada -> vale para as colunas seguintes até o próximo rótulo
    linha  8    : subdivisão do bloco SAEB ('Matemática', 'Língua Portuguesa', ...)
    linha  9    : série ('1º', '2ª série', 'Total') ou ano das metas projetadas
    linha 10    : código técnico da coluna (SG_UF, VL_APROVACAO_2005_SI_4, ...)
    linha 11+   : dados, seguidos das linhas de rodapé com as notas

O ano de cada coluna vem da linha 9/7 (contexto do bloco), NÃO do código técnico
da linha 10: na planilha de regiões/UFs a coluna 79 pertence ao bloco de 2025 mas
tem o código VL_INDICADOR_REND_2023 (erro de origem do INEP). O código da linha 10
serve apenas para identificar o TIPO do indicador.

Este arquivo faz só a transformação. Quem descompacta as planilhas é
`Dados/descompactar.py` e quem define as tabelas é `DataBase/schema.py`; os dois
são chamados automaticamente no início da carga, então a importação funciona a
partir de um clone limpo do repositório, sem passo manual.

    python -m DataBase.importData
"""
import json
import logging
import re
import unicodedata
from pathlib import Path

import pandas as pd

from Dados.descompactar import garantir_planilhas
from Dados.planilhas import por_layout
from DataBase.conexao import conectar
from DataBase.schema import criar_schema

logger = logging.getLogger(__name__)

LINHA_BLOCO = 6            # índice 0-based da linha 7 do Excel
LINHA_SERIE = 8            # linha 9
LINHA_CODIGO = 9           # linha 10
PRIMEIRA_LINHA_DADOS = 10  # linha 11

NULOS = {"-", "ND", "", "*", "--"}
REDES_VALIDAS = {"Total", "Pública", "Privada", "Estadual", "Municipal", "Federal"}

# código técnico (linha 10) -> coluna do banco
CAMPOS_SIMPLES = {
    "VL_INDICADOR_REND": "indicador_rendimento_p",
    "VL_NOTA_MATEMATICA": "nota_saeb_matematica",
    "VL_NOTA_PORTUGUES": "nota_saeb_portugues",
    "VL_NOTA_MEDIA": "nota_saeb_media_padronizada_n",
    "VL_OBSERVADO": "ideb",
    "VL_PROJECAO": "meta_projetada",
}

COLUNAS_IDENT = {
    "SG_UF": "sigla_uf",
    "CO_MUNICIPIO": "codigo_municipio",
    "NO_MUNICIPIO": "nome_municipio",
    "ID_ESCOLA": "codigo_escola",
    "NO_ESCOLA": "nome_escola",
    "REDE": "rede",
}

# A planilha de regiões/UFs traz o nome por extenso (e abreviado); o filtro do
# sistema usa a sigla, então a conversão acontece na importação.
UF_POR_NOME = {
    "Rondônia": "RO", "Acre": "AC", "Amazonas": "AM", "Roraima": "RR",
    "Pará": "PA", "Amapá": "AP", "Tocantins": "TO", "Maranhão": "MA",
    "Piauí": "PI", "Ceará": "CE", "R. G. do Norte": "RN", "Paraíba": "PB",
    "Pernambuco": "PE", "Alagoas": "AL", "Sergipe": "SE", "Bahia": "BA",
    "Minas Gerais": "MG", "Espírito Santo": "ES", "Rio de Janeiro": "RJ",
    "São Paulo": "SP", "Paraná": "PR", "Santa Catarina": "SC",
    "R. G. do Sul": "RS", "M. G. do Sul": "MS", "Mato Grosso": "MT",
    "Goiás": "GO", "Distrito Federal": "DF",
}
REGIOES = {"Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste"}

REGEX_ANO = re.compile(r"(?:19|20)\d{2}")
REGEX_NOTA_RODAPE = re.compile(r"\s*\(\d+\)")


# ---------------------------------------------------------------- normalização

def texto(valor):
    """Normaliza célula de texto; None para vazio ou marcador de ausência."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    s = str(valor).strip()
    return None if s in NULOS or s.lower() == "nan" else s


def numero(valor):
    """Converte célula numérica; '-' e 'ND' viram None (dado não divulgado)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    s = str(valor).strip()
    if s in NULOS:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def codigo(valor):
    """Códigos IBGE/INEP chegam como float do Excel; viram string sem '.0'."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    s = str(valor).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def normalizar_rede(valor):
    """'Pública (4)' -> 'Pública'; 'Total (3)(4)' -> 'Total'."""
    s = texto(valor)
    if s is None:
        return None
    s = REGEX_NOTA_RODAPE.sub("", s).strip()
    return s if s in REDES_VALIDAS else None


def extrair_ano(*celulas):
    """Primeiro ano de 4 dígitos encontrado. '20212' (com nota de rodapé) -> 2021."""
    for c in celulas:
        if c is None or (isinstance(c, float) and pd.isna(c)):
            continue
        m = REGEX_ANO.search(str(c))
        if m:
            return int(m.group())
    return None


def nivel_pela_aba(nome_aba):
    """Deduz o nível de ensino pelo nome da aba (arquivos brasil/regiões)."""
    base = unicodedata.normalize("NFKD", nome_aba.lower()).encode("ascii", "ignore").decode()
    if "inici" in base or "(ai)" in base:
        return "anos_iniciais"
    if "finai" in base or "(af)" in base:
        return "anos_finais"
    if "medio" in base or "(em)" in base:
        return "ensino_medio"
    return None


# ------------------------------------------------------------------ cabeçalho

def mapear_colunas(bruto):
    """
    Lê as linhas de cabeçalho e devolve (identificadores, blocos_por_ano).

    identificadores: {nome_logico: posicao}
    blocos_por_ano:  {ano: {'campos': {coluna_bd: posicao},
                            'series': {rotulo_serie: posicao}}}
    """
    bloco = bruto.iloc[LINHA_BLOCO].ffill()
    serie = bruto.iloc[LINHA_SERIE]
    codigos = bruto.iloc[LINHA_CODIGO]

    identificadores = {}
    blocos = {}

    for pos in range(bruto.shape[1]):
        cod = texto(codigos.iloc[pos])
        cod = cod.upper() if cod else None
        rotulo_bloco = texto(bloco.iloc[pos])

        if cod in COLUNAS_IDENT:
            identificadores[COLUNAS_IDENT[cod]] = pos
            continue
        if cod == "BRASIL":
            continue  # coluna constante com o texto 'Brasil'
        if cod is None and pos < 2 and rotulo_bloco:
            # regiões/UFs não traz código técnico nas 2 primeiras colunas
            chave = "nome_regiao_uf" if "regi" in rotulo_bloco.lower() else "rede"
            identificadores[chave] = pos
            continue
        if cod is None:
            continue

        # A linha 9 tem prioridade: no bloco de metas o rótulo da linha 7 é
        # 'Metas do 1º ciclo do Ideb (2007-2021)' e casaria 2007 nas 8 colunas,
        # enquanto a linha 9 traz o ano correto de cada meta.
        ano = extrair_ano(serie.iloc[pos], rotulo_bloco)
        if ano is None:
            continue
        destino = blocos.setdefault(ano, {"campos": {}, "series": {}})

        if cod.startswith("VL_APROVACAO"):
            # sufixo _SI_4 marca a taxa agregada do ciclo; as demais são por série
            if cod.endswith("_SI_4"):
                destino["campos"].setdefault("taxa_aprovacao_total", pos)
            else:
                rotulo_serie = texto(serie.iloc[pos])
                if rotulo_serie:
                    destino["series"].setdefault(rotulo_serie, pos)
            continue

        for prefixo, coluna_bd in CAMPOS_SIMPLES.items():
            if cod.startswith(prefixo):
                destino["campos"].setdefault(coluna_bd, pos)
                break

    return identificadores, blocos


# ------------------------------------------------------------ wide -> long

CAMPOS_BD = list(CAMPOS_SIMPLES.values()) + ["taxa_aprovacao_total"]


def montar_registros(bruto, identificadores, blocos, abrangencia, nivel_ensino):
    """Converte o formato largo (um bloco de colunas por ano) em uma linha por ano."""
    pos_rede = identificadores.get("rede")
    if pos_rede is None:
        raise ValueError("coluna 'Rede' não localizada no cabeçalho")

    dados = bruto.iloc[PRIMEIRA_LINHA_DADOS:]
    registros = []

    for linha in dados.itertuples(index=False, name=None):
        rede = normalizar_rede(linha[pos_rede])
        if rede is None:
            continue  # rodapé, linha em branco ou rede desconhecida

        ident = {chave: linha[pos] for chave, pos in identificadores.items()}

        if abrangencia == "escola":
            cod_entidade = codigo(ident.get("codigo_escola"))
            nome_entidade = texto(ident.get("nome_escola"))
            cod_municipio = codigo(ident.get("codigo_municipio"))
            cod_escola = cod_entidade
            sigla_uf = texto(ident.get("sigla_uf"))
        elif abrangencia == "municipio":
            cod_entidade = codigo(ident.get("codigo_municipio"))
            nome_entidade = texto(ident.get("nome_municipio"))
            cod_municipio = cod_entidade
            cod_escola = None
            sigla_uf = texto(ident.get("sigla_uf"))
        elif abrangencia == "regiao_uf":
            nome = texto(ident.get("nome_regiao_uf"))
            if nome is None:
                continue
            if nome not in UF_POR_NOME and nome not in REGIOES:
                continue  # rodapé ou linha de fonte
            sigla_uf = UF_POR_NOME.get(nome)          # None para região geográfica
            cod_entidade = sigla_uf or nome           # UF pela sigla, região pelo nome
            nome_entidade = nome
            cod_municipio = None
            cod_escola = None
        else:  # brasil
            cod_entidade = "BR"
            nome_entidade = "Brasil"
            sigla_uf = None
            cod_municipio = None
            cod_escola = None

        if not cod_entidade:
            continue

        for ano, mapa in blocos.items():
            valores = {c: numero(linha[p]) for c, p in mapa["campos"].items()}
            por_serie = {s: numero(linha[p]) for s, p in mapa["series"].items()}
            por_serie = {s: v for s, v in por_serie.items() if v is not None}

            # descarta ano sem nenhum indicador (ex.: escola aberta depois)
            if not any(valores.get(c) is not None for c in CAMPOS_BD) and not por_serie:
                continue

            registros.append({
                "abrangencia": abrangencia,
                "nivel_ensino": nivel_ensino,
                "ano": ano,
                "rede": rede,
                "codigo_entidade": cod_entidade,
                "nome_entidade": nome_entidade,
                "sigla_uf": sigla_uf,
                "codigo_municipio": cod_municipio,
                "codigo_escola": cod_escola,
                "taxa_aprovacao_total": valores.get("taxa_aprovacao_total"),
                "indicador_rendimento_p": valores.get("indicador_rendimento_p"),
                "nota_saeb_matematica": valores.get("nota_saeb_matematica"),
                "nota_saeb_portugues": valores.get("nota_saeb_portugues"),
                "nota_saeb_media_padronizada_n": valores.get("nota_saeb_media_padronizada_n"),
                "ideb": valores.get("ideb"),
                "meta_projetada": valores.get("meta_projetada"),
                "taxa_aprovacao_por_serie": (
                    json.dumps(por_serie, ensure_ascii=False) if por_serie else None
                ),
                "_nome_municipio": texto(ident.get("nome_municipio")),
            })

    return registros


def processar_aba(caminho: Path, aba: str, abrangencia: str, nivel_ensino: str) -> list[dict]:
    bruto = pd.read_excel(caminho, sheet_name=aba, header=None, dtype=object)
    identificadores, blocos = mapear_colunas(bruto)
    return montar_registros(bruto, identificadores, blocos, abrangencia, nivel_ensino)


# ------------------------------------------------------------- carga SQLite

SQL_FATO = """
INSERT OR REPLACE INTO ideb_resultados
    (abrangencia, nivel_ensino, ano, rede, codigo_entidade, nome_entidade,
     sigla_uf, codigo_municipio, codigo_escola, taxa_aprovacao_total,
     indicador_rendimento_p, nota_saeb_matematica, nota_saeb_portugues,
     nota_saeb_media_padronizada_n, ideb, meta_projetada, taxa_aprovacao_por_serie)
VALUES
    (:abrangencia, :nivel_ensino, :ano, :rede, :codigo_entidade, :nome_entidade,
     :sigla_uf, :codigo_municipio, :codigo_escola, :taxa_aprovacao_total,
     :indicador_rendimento_p, :nota_saeb_matematica, :nota_saeb_portugues,
     :nota_saeb_media_padronizada_n, :ideb, :meta_projetada, :taxa_aprovacao_por_serie)
"""


def gravar_municipios(conexao, registros):
    dim = {
        r["codigo_municipio"]: (r["codigo_municipio"], r["_nome_municipio"], r["sigla_uf"])
        for r in registros
        if r["codigo_municipio"] and r["_nome_municipio"] and r["sigla_uf"]
    }
    conexao.executemany(
        "INSERT OR IGNORE INTO municipios (codigo_municipio, nome_municipio, sigla_uf)"
        " VALUES (?, ?, ?)",
        list(dim.values()),
    )


def gravar_escolas(conexao, registros):
    dim = {
        r["codigo_escola"]: (
            r["codigo_escola"], r["nome_entidade"], r["codigo_municipio"], r["sigla_uf"]
        )
        for r in registros
        if r["codigo_escola"] and r["nome_entidade"] and r["sigla_uf"]
    }
    conexao.executemany(
        "INSERT OR IGNORE INTO escolas (codigo_escola, nome_escola, codigo_municipio, sigla_uf)"
        " VALUES (?, ?, ?, ?)",
        list(dim.values()),
    )


def gravar_fatos(conexao, registros):
    limpos = [{k: v for k, v in r.items() if not k.startswith("_")} for r in registros]
    conexao.executemany(SQL_FATO, limpos)
    return len(limpos)


def importar(conexao) -> int:
    """Percorre o catálogo de planilhas e carrega tudo. Devolve o total de fatos."""
    total = 0
    for planilha in por_layout("ideb"):
        if not planilha.xlsx.exists():
            logger.warning("[pulado] %s não encontrado", planilha.xlsx.name)
            continue

        for aba in pd.ExcelFile(planilha.xlsx).sheet_names:
            nivel = planilha.nivel_ensino or nivel_pela_aba(aba)
            if nivel is None:
                logger.warning("[aviso] %s / %s: nível de ensino não identificado",
                               planilha.base, aba)
                continue

            registros = processar_aba(planilha.xlsx, aba, planilha.abrangencia, nivel)

            # dimensões antes dos fatos: as FKs apontam para elas
            if planilha.abrangencia in ("municipio", "escola"):
                gravar_municipios(conexao, registros)
            if planilha.abrangencia == "escola":
                gravar_escolas(conexao, registros)

            n = gravar_fatos(conexao, registros)
            conexao.commit()
            total += n
            logger.info("%s / %s: %d registros", planilha.base, aba, n)
    return total


def main():
    # import local: importInse reaproveita os helpers deste módulo, e o import no
    # topo fecharia um ciclo
    from DataBase.importInse import importar as importar_inse

    garantir_planilhas()
    with conectar() as conexao:
        criar_schema(conexao)
        total = importar(conexao)
        total_inse = importar_inse(conexao)
        conexao.execute("PRAGMA optimize;")
    logger.info("Importação concluída: %d registros do IDEB, %d do INSE.", total, total_inse)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
