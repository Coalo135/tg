# Cria o Banco de dados sqlite 
# chamar - criar_schema() 

import logging

from DataBase.conexao import conectar

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS municipios (
    codigo_municipio TEXT PRIMARY KEY,
    nome_municipio   TEXT NOT NULL,
    sigla_uf         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escolas (
    codigo_escola    TEXT PRIMARY KEY,
    nome_escola      TEXT NOT NULL,
    codigo_municipio TEXT REFERENCES municipios(codigo_municipio),
    sigla_uf         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ideb_resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    abrangencia   TEXT NOT NULL,   -- 'brasil' | 'regiao_uf' | 'municipio' | 'escola'
    nivel_ensino  TEXT NOT NULL,   -- 'anos_iniciais' | 'anos_finais' | 'ensino_medio'
    ano           INTEGER NOT NULL,
    rede          TEXT,            -- 'Total' | 'Pública' | 'Municipal' | 'Estadual' | ...

    codigo_entidade  TEXT NOT NULL,  -- 'BR', sigla da UF, código IBGE ou código INEP
    nome_entidade    TEXT,
    sigla_uf         TEXT,
    codigo_municipio TEXT REFERENCES municipios(codigo_municipio),
    codigo_escola    TEXT REFERENCES escolas(codigo_escola),

    taxa_aprovacao_total          NUMERIC,
    indicador_rendimento_p        NUMERIC,
    nota_saeb_matematica          NUMERIC,
    nota_saeb_portugues           NUMERIC,
    nota_saeb_media_padronizada_n NUMERIC,
    ideb                          NUMERIC,
    meta_projetada                NUMERIC,

    -- JSON serializado como TEXT; consultável via json_extract/json_each (json1)
    taxa_aprovacao_por_serie TEXT,

    -- Torna a importação repetível: reimportar a mesma planilha atualiza a linha
    -- em vez de duplicá-la (ver INSERT OR REPLACE em importData.py).
    UNIQUE (abrangencia, nivel_ensino, ano, codigo_entidade, rede)
);

CREATE INDEX IF NOT EXISTS idx_ideb_filtro    ON ideb_resultados (nivel_ensino, ano, abrangencia);
CREATE INDEX IF NOT EXISTS idx_ideb_municipio ON ideb_resultados (codigo_municipio);
CREATE INDEX IF NOT EXISTS idx_ideb_escola    ON ideb_resultados (codigo_escola);
CREATE INDEX IF NOT EXISTS idx_ideb_sigla_uf  ON ideb_resultados (sigla_uf);

-- A consulta mais frequente do módulo ML e da API é "município + rede + nível";
-- sem este índice ela varre a tabela inteira.
CREATE INDEX IF NOT EXISTS idx_ideb_abrangencia_rede
    ON ideb_resultados (abrangencia, rede, nivel_ensino, ano);

CREATE INDEX IF NOT EXISTS idx_municipios_uf ON municipios (sigla_uf);
CREATE INDEX IF NOT EXISTS idx_escolas_municipio ON escolas (codigo_municipio);
"""


def criar_schema(conexao=None) -> None:
    """Cria tabelas e índices se ainda não existirem. Idempotente."""
    if conexao is not None:
        conexao.executescript(DDL)
        return
    with conectar() as nova_conexao:
        nova_conexao.executescript(DDL)
    logger.info("Esquema criado/verificado.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    criar_schema()
    print("Esquema pronto.")
