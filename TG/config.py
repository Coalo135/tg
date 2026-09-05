# Aqui estão os caminhos dos PATHS dos arquivos para não quebrar em outras maquinas
#

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PASTA_PLANILHAS = Path(os.environ.get("IDEB_PLANILHAS", BASE_DIR / "Planilhas"))
DB_PATH = Path(os.environ.get("IDEB_DB", BASE_DIR / "sqlite_ideb.db"))

PASTA_EXPORTACAO = BASE_DIR / "Exportacao" / "saidas"
PASTA_GRAFICOS = BASE_DIR / "Visualizacao" / "saidas"
PASTA_ML = BASE_DIR / "ML" / "saidas"

# O IDEB é bienal. Usado pelo módulo ML para deslocar ciclos (T+1 = T + 2 anos).
PASSO_CICLO = 2

ABRANGENCIAS = ("brasil", "regiao_uf", "municipio", "escola")
NIVEIS_ENSINO = ("anos_iniciais", "anos_finais", "ensino_medio")
REDES = ("Total", "Pública", "Privada", "Estadual", "Municipal", "Federal")
