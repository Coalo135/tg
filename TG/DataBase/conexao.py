# Centraliza a abertura do banco de dados por um unico lugar
# para garantir que o banco inicie com o "PRAGMA foreign_key = ON"
# assim garante que o banco de dados esteja conectado com as chaves estrageiras corretamente
#
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config


class BancoNaoEncontrado(FileNotFoundError):
    """O arquivo .db ainda não foi criado — falta rodar a importação."""


def _aplicar_pragmas(conexao: sqlite3.Connection) -> None:
    conexao.execute("PRAGMA foreign_keys = ON;") #banco de dados esteja conectado com as chaves estrageiras corretamente
    conexao.execute("PRAGMA journal_mode = WAL;") #leitura e escrita concorrerem sem travar uma à outra
    conexao.execute("PRAGMA synchronous = NORMAL;") #carga em lote fica rápida, ao custo de perder a última transação num desligamento abrupto

@contextmanager
def conectar(caminho: Path | None = None, exigir_existente: bool = False):
    caminho = Path(caminho or config.DB_PATH)
    if exigir_existente and not caminho.exists():
        raise BancoNaoEncontrado(
            f"Banco não encontrado em {caminho}. "
            "Rode `python -m DataBase.importData` para criá-lo a partir das planilhas."
        )

    conexao = sqlite3.connect(caminho)
    try:
        _aplicar_pragmas(conexao)
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
