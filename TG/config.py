# Aqui estão os caminhos dos PATHS dos arquivos para não quebrar em outras maquinas
#

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PASTA_PLANILHAS = Path(os.environ.get("IDEB_PLANILHAS", BASE_DIR / "Planilhas"))
DB_PATH = Path(os.environ.get("IDEB_DB", BASE_DIR / "sqlite_ideb.db"))

PASTA_EXPORTACAO = BASE_DIR / "Exportacao" / "saidas"
PASTA_GRAFICOS = BASE_DIR / "Visualizacao" / "saidas"
PASTA_MODELOS = BASE_DIR / "Modelos" / "saidas"

ABRANGENCIAS = ("brasil", "regiao_uf", "municipio", "escola")
NIVEIS_ENSINO = ("anos_iniciais", "anos_finais", "ensino_medio")
REDES = ("Total", "Pública", "Privada", "Estadual", "Municipal", "Federal")
