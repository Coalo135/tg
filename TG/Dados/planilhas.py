"""
planilhas.py — Catálogo único das planilhas que o projeto usa.

Fonte única de verdade sobre cada arquivo: nome, o que ele representa, de onde
baixá-lo e com que parser ele é lido. Antes os mesmos 8 nomes de arquivo apareciam
repetidos em três módulos, com a ordem mantida em sincronia na mão — editar uma
cópia sem editar as outras apontava silenciosamente para o arquivo errado. A URL
de download também morava fora daqui, montada na API a partir do nome, o que só
funcionava enquanto todas as planilhas viessem do mesmo diretório do INEP.

Dois layouts convivem no catálogo, e `layout` diz qual importador lê cada um:

- `ideb` — as 8 planilhas de divulgação do IDEB, cabeçalho mesclado de 4 linhas
  (`DataBase/importData.py`). `nivel_ensino=None` significa que o arquivo cobre os
  três níveis em abas diferentes, e a importação deduz o nível pelo nome da aba.
- `inse` — Indicador de Nível Socioeconômico por município, cabeçalho de uma linha
  só (`DataBase/importInse.py`). Não tem nível de ensino: o indicador descreve os
  alunos do município, não uma etapa.
"""
from pathlib import Path
from typing import NamedTuple

from config import PASTA_PLANILHAS

ANO_DIVULGACAO = 2025

URL_IDEB = "https://download.inep.gov.br/ideb/resultados/"
URL_INSE = "https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/"


class Planilha(NamedTuple):
    chave: str
    base: str
    abrangencia: str
    nivel_ensino: str | None
    url: str
    layout: str = "ideb"

    @property
    def xlsx(self) -> Path:
        """Caminho do .xlsx descompactado (arquivo de trabalho, fora do git)."""
        return PASTA_PLANILHAS / f"{self.base}.xlsx"

    @property
    def zip(self) -> Path:
        """Caminho do .zip versionado no git."""
        return PASTA_PLANILHAS / f"{self.base}.zip"


def _ideb(chave: str, abrangencia: str, nivel_ensino: str | None) -> Planilha:
    base = f"divulgacao_{chave}_{ANO_DIVULGACAO}"
    return Planilha(chave, base, abrangencia, nivel_ensino, url=f"{URL_IDEB}{base}.zip")


def _inse(ano: int) -> Planilha:
    base = f"INSE_{ano}_municipios"
    return Planilha(f"inse_municipios_{ano}", base, "municipio", None,
                    url=f"{URL_INSE}{ano}/nivel_socioeconomico/{base}.xlsx", layout="inse")


PLANILHAS: tuple[Planilha, ...] = (
    _ideb("anos_iniciais_municipios", "municipio", "anos_iniciais"),
    _ideb("anos_finais_municipios", "municipio", "anos_finais"),
    _ideb("ensino_medio_municipios", "municipio", "ensino_medio"),
    _ideb("anos_iniciais_escolas", "escola", "anos_iniciais"),
    _ideb("anos_finais_escolas", "escola", "anos_finais"),
    _ideb("ensino_medio_escolas", "escola", "ensino_medio"),
    _ideb("brasil_ideb", "brasil", None),
    _ideb("regioes_ufs_ideb", "regiao_uf", None),
    _inse(2023),
    _inse(2021),
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


def por_layout(layout: str) -> tuple[Planilha, ...]:
    """Só as planilhas que um dado importador sabe ler."""
    return tuple(p for p in PLANILHAS if p.layout == layout)
