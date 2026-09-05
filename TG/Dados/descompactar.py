"""
descompactar.py — Reconstrói os .xlsx das planilhas a partir dos .zip de `Planilhas/`.

Por que os .zip existem
-----------------------
Os 8 .xlsx de divulgação somam ~127 MB. Versioná-los direto no git é ruim: são
binários, então cada nova divulgação do INEP grava outros 127 MB no histórico,
sem delta possível. Só que zipar um .xlsx não adianta nada — o .xlsx **já é** um
zip deflate por dentro, e re-comprimi-lo economiza ~0,3%.

O que dá resultado é abrir o .xlsx, pegar as partes OOXML de dentro dele (os XML
crus, descomprimidos) e recomprimir tudo com LZMA num único .zip por planilha:
127 MB caem para ~55 MB. É esse .zip que fica no git; o .xlsx é gerado aqui e
fica de fora do versionamento (ver `.gitignore`).

Formatos aceitos
----------------
A extração aceita as duas formas que aparecem no projeto, então o mesmo comando
serve tanto para os zips do repositório quanto para um download novo do INEP:

1. **Zip de partes OOXML** (o formato do repositório): o conteúdo é
   `[Content_Types].xml`, `xl/`, `_rels/`... — o .xlsx é remontado a partir dele.
2. **Zip contendo .xlsx** (o formato que o INEP entrega em `GET /baixar`): o
   .xlsx é extraído, inclusive de dentro de uma subpasta, e vai direto para
   `Planilhas/`.

A limpeza de cabeçalho (`limpo_<arquivo>.xlsx`) que existia neste fluxo foi
removida: `DataBase/importData.py` lê o cabeçalho mesclado das 4 linhas direto do
arquivo bruto, então o .xlsx intermediário só duplicava dados em disco.
"""
import logging
import zipfile
from pathlib import Path

from config import PASTA_PLANILHAS
from Dados.planilhas import PLANILHAS, Planilha

logger = logging.getLogger(__name__)

# Presente na raiz de todo pacote OOXML — é o que distingue um zip de partes
# internas de um zip que simplesmente contém um .xlsx.
MARCADOR_OOXML = "[Content_Types].xml"


def _e_pacote_ooxml(arquivo_zip: zipfile.ZipFile) -> bool:
    return MARCADOR_OOXML in arquivo_zip.namelist()


def _remontar_xlsx(caminho_zip: Path, destino: Path) -> None:
    """Reconstrói o .xlsx a partir das partes OOXML guardadas no .zip.

    Grava as partes com deflate, que é o que o formato .xlsx espera — o LZMA
    serve só para o arquivo ficar pequeno no git, não para o Excel abrir.
    """
    with zipfile.ZipFile(caminho_zip) as origem:
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as saida:
            for nome in origem.namelist():
                saida.writestr(nome, origem.read(nome))


def extrair_xlsx_de_zip(caminho_zip: Path, destino: Path) -> bool:
    """Extrai o .xlsx de dentro do .zip (formato do download do INEP).

    O INEP às vezes empacota o arquivo dentro de uma subpasta com o mesmo nome do
    zip. Aqui o conteúdo é lido e gravado direto em `destino`, o que achata essa
    estrutura — a versão anterior deste módulo extraía tudo e depois precisava
    mover o .xlsx e apagar a subpasta órfã.

    Usado tanto na descompactação normal quanto pela rota `/baixar` da API, que
    recebe exatamente esse formato do INEP.
    """
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        internos = [n for n in arquivo_zip.namelist() if n.lower().endswith(".xlsx")]
        if not internos:
            return False
        destino.parent.mkdir(parents=True, exist_ok=True)
        with arquivo_zip.open(internos[0]) as origem:
            destino.write_bytes(origem.read())
    return True


def descompactar_planilha(planilha: Planilha, forcar: bool = False) -> Path | None:
    """Garante o .xlsx de uma planilha. Devolve o caminho, ou None se faltar o .zip.

    Sem `forcar`, um .xlsx já existente é mantido como está — descompactar de novo
    custa tempo e produz exatamente o mesmo arquivo.
    """
    if planilha.xlsx.exists() and not forcar:
        logger.debug("%s já descompactado", planilha.xlsx.name)
        return planilha.xlsx

    if not planilha.zip.exists():
        logger.warning("Zip não encontrado: %s", planilha.zip)
        return None

    with zipfile.ZipFile(planilha.zip) as arquivo_zip:
        pacote_ooxml = _e_pacote_ooxml(arquivo_zip)

    if pacote_ooxml:
        _remontar_xlsx(planilha.zip, planilha.xlsx)
    elif not extrair_xlsx_de_zip(planilha.zip, planilha.xlsx):
        logger.error("Nenhum .xlsx dentro de %s", planilha.zip.name)
        return None

    tamanho_mb = planilha.xlsx.stat().st_size / 1e6
    logger.info("Descompactado: %s (%.1f MB)", planilha.xlsx.name, tamanho_mb)
    return planilha.xlsx


def descompactar(forcar: bool = False) -> list[Path]:
    """Descompacta todas as planilhas do catálogo. Devolve os .xlsx disponíveis."""
    PASTA_PLANILHAS.mkdir(parents=True, exist_ok=True)
    caminhos = [descompactar_planilha(p, forcar=forcar) for p in PLANILHAS]
    return [c for c in caminhos if c is not None]


def garantir_planilhas() -> list[Path]:
    """Descompacta só o que estiver faltando. É o que a importação chama."""
    faltando = [p for p in PLANILHAS if not p.xlsx.exists()]
    if faltando:
        logger.info("Descompactando %d planilha(s)...", len(faltando))
    return descompactar(forcar=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    arquivos = descompactar()
    print(f"\n{len(arquivos)}/{len(PLANILHAS)} planilhas disponíveis em {PASTA_PLANILHAS}")
