"""
inep_download.py — Baixa uma planilha do INEP e deixa o .xlsx pronto em `Planilhas/`.

Por que a verificação de certificado precisa de ajuda
------------------------------------------------------
`download.inep.gov.br` envia só o certificado do servidor, sem o intermediário que
o assina (RNP ICPEdu GR46 OV TLS CA 2025). Qualquer cliente com verificação ligada
— requests, curl, navegador em modo estrito — falha com "unable to verify the
first certificate". A rota `GET /baixar` da API caía sempre nesse erro, e o
handler de SSLError que ela tem devolvia 502 em toda chamada.

A saída correta não é desligar a verificação, é fornecer o elo que falta: o
intermediário fica versionado em `Dados/certs/` e é concatenado ao bundle do
`certifi`, gerando o arquivo que vai em `verify=`.

Quando o intermediário vencer, o download volta a falhar com o mesmo erro. Para
renovar: `openssl s_client -connect download.inep.gov.br:443 -servername
download.inep.gov.br </dev/null | openssl x509 -noout -text` mostra, em
"Authority Information Access", a URL do intermediário atual (CA Issuers). Baixe,
converta com `openssl x509 -inform DER` e substitua o .pem.

Uso
---
    python -m Dados.inep_download inse_municipios_2023 inse_municipios_2021
    python -m Dados.inep_download            # lista as chaves do catálogo
"""
import logging
import sys
from pathlib import Path

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import PASTA_PLANILHAS
from Dados.descompactar import extrair_xlsx_de_zip
from Dados.planilhas import PLANILHAS, Planilha, por_chave

logger = logging.getLogger(__name__)

PASTA_CERTS = Path(__file__).resolve().parent / "certs"
INTERMEDIARIO = PASTA_CERTS / "rnp_icpedu_gr46.pem"
BUNDLE = PASTA_CERTS / "ca-bundle.pem"  # gerado; fora do git

# Os downloads do INEP vão para uma subpasta própria. Os .zip de `Planilhas/` são
# os arquivos versionados no git (partes OOXML recomprimidas); gravar o download
# do INEP com o mesmo nome sobrescreveria o arquivo do repositório.
PASTA_DOWNLOADS = PASTA_PLANILHAS / "downloads"

CABECALHOS = {"User-Agent": "Mozilla/5.0"}

# O servidor do INEP derruba conexões com alguma frequência ("connection reset by
# peer") antes mesmo de responder; três tentativas com espera crescente resolvem.
RETENTATIVAS = Retry(total=3, backoff_factor=2, status_forcelist=(502, 503, 504))


def bundle_ca() -> Path:
    """Bundle = certifi + intermediário da RNP. Regenerado se alguma fonte mudou."""
    fontes = (Path(certifi.where()), INTERMEDIARIO)
    if not BUNDLE.exists() or BUNDLE.stat().st_mtime < max(f.stat().st_mtime for f in fontes):
        BUNDLE.write_bytes(b"\n".join(f.read_bytes() for f in fontes))
    return BUNDLE


def baixar(url: str, destino: Path, timeout: int = 120) -> Path:
    """Download em streaming, com a cadeia de certificados completa."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    sessao = requests.Session()
    sessao.mount("https://", HTTPAdapter(max_retries=RETENTATIVAS))
    with sessao.get(url, headers=CABECALHOS, stream=True, timeout=timeout,
                    verify=str(bundle_ca())) as resposta:
        resposta.raise_for_status()
        with open(destino, "wb") as arquivo:
            for pedaco in resposta.iter_content(chunk_size=1 << 16):
                arquivo.write(pedaco)
    return destino


def baixar_planilha(planilha: Planilha) -> Path:
    """Baixa `planilha.url` e devolve o caminho do .xlsx pronto.

    O INEP entrega o IDEB como .zip com o .xlsx dentro, e o INSE como .xlsx direto;
    a extensão da URL decide o que fazer com o arquivo baixado.
    """
    if planilha.url.endswith(".xlsx"):
        return baixar(planilha.url, planilha.xlsx)

    destino_zip = baixar(planilha.url, PASTA_DOWNLOADS / f"{planilha.base}.zip")
    if not extrair_xlsx_de_zip(destino_zip, planilha.xlsx):
        raise ValueError(f"Nenhum .xlsx dentro de {destino_zip.name}")
    return planilha.xlsx


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    chaves = sys.argv[1:]
    if not chaves:
        print("Uso: python -m Dados.inep_download <chave> [<chave> ...]\nChaves:")
        for p in PLANILHAS:
            print(f"  {p.chave:28} {p.url}")
        sys.exit(0)
    for chave in chaves:
        caminho = baixar_planilha(por_chave(chave))
        logger.info("%s -> %s (%.1f MB)", chave, caminho, caminho.stat().st_size / 1e6)
