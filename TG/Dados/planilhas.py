"""
planilhas.py — Catálogo único das planilhas de divulgação do IDEB (INEP).

Fonte única de verdade sobre quais planilhas o projeto usa. Antes os mesmos 8
nomes de arquivo apareciam repetidos em três módulos, com a ordem mantida em
sincronia na mão — editar uma cópia sem editar as outras apontava silenciosamente
para o arquivo errado.

Além do nome, cada entrada carrega a `abrangencia` e o `nivel_ensino` que o
arquivo representa. Esses dois campos estavam duplicados numa lista separada
dentro de `DataBase/importData.py`; agora vêm daqui, então acrescentar uma
planilha nova é mexer num lugar só.

`nivel_ensino=None` significa que o arquivo cobre os três níveis em abas
diferentes — nesse caso a importação deduz o nível pelo nome da aba.
"""
from pathlib import Path
from typing import NamedTuple

from config import PASTA_PLANILHAS

ANO_DIVULGACAO = 2025


class Planilha(NamedTuple):
    chave: str
    base: str
    abrangencia: str
    nivel_ensino: str | None

    @property
    def xlsx(self) -> Path:
        """Caminho do .xlsx descompactado (arquivo de trabalho, fora do git)."""
        return PASTA_PLANILHAS / f"{self.base}.xlsx"

    @property
    def zip(self) -> Path:
        """Caminho do .zip versionado no git."""
        return PASTA_PLANILHAS / f"{self.base}.zip"


PLANILHAS: tuple[Planilha, ...] = (
    Planilha("anos_iniciais_municipios",
             f"divulgacao_anos_iniciais_municipios_{ANO_DIVULGACAO}",
             "municipio", "anos_iniciais"),
    Planilha("anos_finais_municipios",
             f"divulgacao_anos_finais_municipios_{ANO_DIVULGACAO}",
             "municipio", "anos_finais"),
    Planilha("ensino_medio_municipios",
             f"divulgacao_ensino_medio_municipios_{ANO_DIVULGACAO}",
             "municipio", "ensino_medio"),
    Planilha("anos_iniciais_escolas",
             f"divulgacao_anos_iniciais_escolas_{ANO_DIVULGACAO}",
             "escola", "anos_iniciais"),
    Planilha("anos_finais_escolas",
             f"divulgacao_anos_finais_escolas_{ANO_DIVULGACAO}",
             "escola", "anos_finais"),
    Planilha("ensino_medio_escolas",
             f"divulgacao_ensino_medio_escolas_{ANO_DIVULGACAO}",
             "escola", "ensino_medio"),
    Planilha("brasil_ideb",
             f"divulgacao_brasil_ideb_{ANO_DIVULGACAO}",
             "brasil", None),
    Planilha("regioes_ufs_ideb",
             f"divulgacao_regioes_ufs_ideb_{ANO_DIVULGACAO}",
             "regiao_uf", None),
)


def por_chave(chave: str) -> Planilha:
    """Busca uma planilha pela chave nomeada (ex.: "brasil_ideb")."""
    for planilha in PLANILHAS:
        if planilha.chave == chave:
            return planilha
    raise KeyError(
        f"Planilha desconhecida: {chave!r}. "
        f"Chaves válidas: {', '.join(p.chave for p in PLANILHAS)}"
    )
