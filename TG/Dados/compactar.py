"""
compactar.py — Gera o .zip versionado a partir do .xlsx. É o inverso de descompactar.py.

Um .xlsx já é um zip deflate por dentro; re-zipá-lo economiza ~0,3%. O que rende
é abrir o pacote, pegar as partes OOXML cruas e recomprimir tudo com LZMA num
único .zip por planilha — nas planilhas do IDEB, 131 MB viram 60 MB. Esse .zip é
o que fica no git; o .xlsx é reconstruído localmente e está no `.gitignore`.

Os 8 zips originais do repositório foram gerados fora dele; este módulo existe
para que uma planilha nova (ou uma divulgação nova do INEP) entre no mesmo padrão
sem passo manual:

    python -m Dados.compactar            # todo .xlsx que ainda não tem .zip
    python -m Dados.compactar --forcar   # regera todos
"""
import logging
import sys
import zipfile
from pathlib import Path

from Dados.planilhas import PLANILHAS, Planilha

logger = logging.getLogger(__name__)

COMENTARIO = b"partes OOXML; reconstruir com Dados/descompactar.py"


def compactar_xlsx(caminho_xlsx: Path, destino_zip: Path) -> None:
    with zipfile.ZipFile(caminho_xlsx) as origem:
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_LZMA) as saida:
            saida.comment = COMENTARIO
            for nome in origem.namelist():
                saida.writestr(nome, origem.read(nome))


def round_trip_fiel(caminho_xlsx: Path, caminho_zip: Path) -> bool:
    """Mesmas partes, na mesma ordem, com o mesmo conteúdo byte a byte."""
    with zipfile.ZipFile(caminho_xlsx) as a, zipfile.ZipFile(caminho_zip) as b:
        if a.namelist() != b.namelist():
            return False
        return all(a.read(nome) == b.read(nome) for nome in a.namelist())


def compactar_planilha(planilha: Planilha, forcar: bool = False) -> Path | None:
    """Gera o .zip de uma planilha. Devolve o caminho, ou None se faltar o .xlsx."""
    if planilha.zip.exists() and not forcar:
        logger.debug("%s já existe", planilha.zip.name)
        return planilha.zip
    if not planilha.xlsx.exists():
        logger.warning("xlsx não encontrado: %s", planilha.xlsx)
        return None

    compactar_xlsx(planilha.xlsx, planilha.zip)
    if not round_trip_fiel(planilha.xlsx, planilha.zip):
        planilha.zip.unlink()
        raise RuntimeError(f"round-trip infiel em {planilha.base}; zip descartado")

    antes = planilha.xlsx.stat().st_size / 1e6
    depois = planilha.zip.stat().st_size / 1e6
    logger.info("Compactado: %s (%.1f MB -> %.1f MB, %.0f%%)",
                planilha.zip.name, antes, depois, 100 * (1 - depois / antes))
    return planilha.zip


def compactar(forcar: bool = False) -> list[Path]:
    caminhos = [compactar_planilha(p, forcar=forcar) for p in PLANILHAS]
    return [c for c in caminhos if c is not None]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    zips = compactar(forcar="--forcar" in sys.argv)
    print(f"\n{len(zips)}/{len(PLANILHAS)} zips disponíveis")
