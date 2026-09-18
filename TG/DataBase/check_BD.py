"""
Checkup do banco sqlite_ideb.db.

Roda uma bateria de verificacoes e imprime OK / FALHA para cada uma.
Nao altera nada no banco -- e so leitura.

    python -m DataBase.check_BD

O caminho do banco e o mesmo de todo o resto do projeto (config.DB_PATH). Antes
era Path("sqlite_ideb.db"), relativo ao diretorio de execucao: rodar o checkup de
outra pasta abria um arquivo diferente -- ou criava um vazio -- e reportava falha
em um banco que estava intacto.
"""

import json
from datetime import date

from config import DB_PATH
from DataBase.conexao import conectar

ABRANGENCIAS = {"brasil", "regiao_uf", "municipio", "escola"}
NIVEIS = {"anos_iniciais", "anos_finais", "ensino_medio"}
REDES = {"Total", "Pública", "Privada", "Estadual", "Municipal", "Federal"}
REDES_INSE = {"Pública", "Privada", "Estadual", "Municipal", "Federal", "Estadual+Municipal"}
LOCALIZACOES_INSE = {"Total", "Urbana", "Rural"}
# Ciclos bienais do IDEB, de 2005 ate o ano corrente. Era um conjunto fixo
# terminando em 2025; assim a proxima divulgacao nao vira "ano inesperado".
ANOS = set(range(2005, date.today().year + 1, 2))

resultados = []


def titulo(texto):
    print(f"\n{'=' * 66}\n{texto}\n{'=' * 66}")


def checar(descricao, condicao, detalhe=""):
    """Registra o resultado de uma verificacao booleana."""
    marca = "OK  " if condicao else "FALHA"
    print(f"  [{marca}] {descricao}" + (f" -> {detalhe}" if detalhe else ""))
    resultados.append((descricao, condicao))
    return condicao


def uma(cur, sql, params=()):
    return cur.execute(sql, params).fetchone()[0]


# --------------------------------------------------------------- estrutura

def checar_estrutura(cur):
    titulo("1. ESTRUTURA DAS TABELAS")

    tabelas = {r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("municipios", "escolas", "ideb_resultados", "inse_municipios"):
        checar(f"tabela '{t}' existe", t in tabelas)

    esperadas = {
        "id", "abrangencia", "nivel_ensino", "ano", "rede", "codigo_entidade",
        "nome_entidade", "sigla_uf", "codigo_municipio", "codigo_escola",
        "taxa_aprovacao_total", "indicador_rendimento_p", "nota_saeb_matematica",
        "nota_saeb_portugues", "nota_saeb_media_padronizada_n", "ideb",
        "meta_projetada", "taxa_aprovacao_por_serie",
    }
    existentes = {r[1] for r in cur.execute("PRAGMA table_info(ideb_resultados)")}
    faltando = esperadas - existentes
    checar("todas as colunas de ideb_resultados presentes", not faltando,
           f"faltando: {sorted(faltando)}" if faltando else "")

    indices = {r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='ideb_resultados'")}
    for idx in ("idx_ideb_filtro", "idx_ideb_municipio",
                "idx_ideb_escola", "idx_ideb_sigla_uf"):
        checar(f"indice '{idx}' criado", idx in indices)


# -------------------------------------------------------------- volumetria

def checar_volumetria(cur):
    titulo("2. VOLUMETRIA")

    n_mun = uma(cur, "SELECT COUNT(*) FROM municipios")
    n_esc = uma(cur, "SELECT COUNT(*) FROM escolas")
    n_fat = uma(cur, "SELECT COUNT(*) FROM ideb_resultados")

    print(f"  municipios ....... {n_mun:>9,}")
    print(f"  escolas .......... {n_esc:>9,}")
    print(f"  ideb_resultados .. {n_fat:>9,}")
    if DB_PATH.exists():
        print(f"  tamanho do arquivo {DB_PATH.stat().st_size / 1e6:>8.1f} MB")

    # o Brasil tem 5.570 municipios + Distrito Federal na base do INEP
    checar("total de municipios plausivel (5.500-5.600)", 5500 <= n_mun <= 5600, f"{n_mun}")
    checar("ha escolas carregadas", n_esc > 10_000, f"{n_esc}")
    checar("ha fatos carregados", n_fat > 100_000, f"{n_fat}")

    print("\n  distribuicao abrangencia x nivel:")
    combinacoes = set()
    for abr, niv, qtd in cur.execute(
            "SELECT abrangencia, nivel_ensino, COUNT(*) FROM ideb_resultados "
            "GROUP BY 1, 2 ORDER BY 1, 2"):
        print(f"    {abr:<11} {niv:<15} {qtd:>9,}")
        combinacoes.add((abr, niv))

    checar("as 12 combinacoes abrangencia x nivel existem",
           len(combinacoes) == 12, f"{len(combinacoes)} de 12")


# ----------------------------------------------------------------- dominios

def checar_dominios(cur):
    titulo("3. DOMINIOS (valores permitidos)")

    def distintos(coluna):
        return {r[0] for r in cur.execute(
            f"SELECT DISTINCT {coluna} FROM ideb_resultados")}

    for coluna, permitido in (("abrangencia", ABRANGENCIAS),
                              ("nivel_ensino", NIVEIS),
                              ("rede", REDES)):
        encontrados = distintos(coluna)
        invalidos = encontrados - permitido
        checar(f"'{coluna}' sem valores fora do dominio", not invalidos,
               f"invalidos: {sorted(str(v) for v in invalidos)}" if invalidos else
               f"{sorted(str(v) for v in encontrados)}")

    anos = {r[0] for r in cur.execute("SELECT DISTINCT ano FROM ideb_resultados")}
    checar("anos dentro dos ciclos do IDEB", anos <= ANOS,
           f"inesperados: {sorted(anos - ANOS)}" if anos - ANOS else f"{sorted(anos)}")

    for coluna in ("abrangencia", "nivel_ensino", "ano", "codigo_entidade"):
        nulos = uma(cur, f"SELECT COUNT(*) FROM ideb_resultados WHERE {coluna} IS NULL")
        checar(f"'{coluna}' sem NULL", nulos == 0, f"{nulos} nulos")


# --------------------------------------------- coerencia do star schema

def checar_coerencia_abrangencia(cur):
    titulo("4. COERENCIA POR ABRANGENCIA")

    regras = [
        ("escola: codigo_escola sempre preenchido",
         "abrangencia='escola' AND codigo_escola IS NULL"),
        ("escola: codigo_entidade = codigo_escola",
         "abrangencia='escola' AND codigo_entidade <> codigo_escola"),
        ("escola: codigo_municipio sempre preenchido",
         "abrangencia='escola' AND codigo_municipio IS NULL"),
        ("municipio: codigo_escola sempre nulo",
         "abrangencia='municipio' AND codigo_escola IS NOT NULL"),
        ("municipio: codigo_entidade = codigo_municipio",
         "abrangencia='municipio' AND codigo_entidade <> codigo_municipio"),
        ("municipio: sigla_uf sempre preenchida",
         "abrangencia='municipio' AND sigla_uf IS NULL"),
        ("regiao_uf: sem vinculo com municipio ou escola",
         "abrangencia='regiao_uf' AND (codigo_municipio IS NOT NULL "
         "OR codigo_escola IS NOT NULL)"),
        ("brasil: codigo_entidade sempre 'BR'",
         "abrangencia='brasil' AND codigo_entidade <> 'BR'"),
        ("brasil: sem vinculo geografico",
         "abrangencia='brasil' AND (sigla_uf IS NOT NULL "
         "OR codigo_municipio IS NOT NULL OR codigo_escola IS NOT NULL)"),
    ]
    for descricao, condicao in regras:
        n = uma(cur, f"SELECT COUNT(*) FROM ideb_resultados WHERE {condicao}")
        checar(descricao, n == 0, f"{n} linhas violam" if n else "")

    # regiao_uf deve ter 5 regioes + 27 unidades da federacao
    n_ent = uma(cur, "SELECT COUNT(DISTINCT codigo_entidade) FROM ideb_resultados "
                     "WHERE abrangencia='regiao_uf'")
    checar("regiao_uf tem 32 entidades (5 regioes + 27 UFs)", n_ent == 32, f"{n_ent}")

    n_uf = uma(cur, "SELECT COUNT(DISTINCT sigla_uf) FROM ideb_resultados "
                    "WHERE abrangencia='regiao_uf' AND sigla_uf IS NOT NULL")
    checar("27 siglas de UF distintas em regiao_uf", n_uf == 27, f"{n_uf}")


# --------------------------------------------------- integridade referencial

def checar_chaves(cur):
    titulo("5. CHAVES E INTEGRIDADE REFERENCIAL")

    orfas_esc = uma(cur, """
        SELECT COUNT(*) FROM ideb_resultados f
        LEFT JOIN escolas e ON e.codigo_escola = f.codigo_escola
        WHERE f.codigo_escola IS NOT NULL AND e.codigo_escola IS NULL""")
    checar("nenhum fato aponta para escola inexistente", orfas_esc == 0, f"{orfas_esc}")

    orfas_mun = uma(cur, """
        SELECT COUNT(*) FROM ideb_resultados f
        LEFT JOIN municipios m ON m.codigo_municipio = f.codigo_municipio
        WHERE f.codigo_municipio IS NOT NULL AND m.codigo_municipio IS NULL""")
    checar("nenhum fato aponta para municipio inexistente", orfas_mun == 0, f"{orfas_mun}")

    orfas_dim = uma(cur, """
        SELECT COUNT(*) FROM escolas e
        LEFT JOIN municipios m ON m.codigo_municipio = e.codigo_municipio
        WHERE e.codigo_municipio IS NOT NULL AND m.codigo_municipio IS NULL""")
    checar("nenhuma escola aponta para municipio inexistente", orfas_dim == 0, f"{orfas_dim}")

    dup = uma(cur, """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM ideb_resultados
            GROUP BY abrangencia, nivel_ensino, ano, codigo_entidade, rede
            HAVING COUNT(*) > 1)""")
    checar("chave unica sem duplicatas", dup == 0, f"{dup} grupos duplicados")

    # o codigo IBGE de municipio tem 7 digitos; o codigo INEP de escola, 8
    mal_mun = uma(cur, "SELECT COUNT(*) FROM municipios "
                       "WHERE LENGTH(codigo_municipio) <> 7")
    checar("codigos de municipio com 7 digitos", mal_mun == 0, f"{mal_mun} fora do padrao")

    mal_esc = uma(cur, "SELECT COUNT(*) FROM escolas WHERE LENGTH(codigo_escola) <> 8")
    checar("codigos de escola com 8 digitos", mal_esc == 0, f"{mal_esc} fora do padrao")

    inconsistente = uma(cur, """
        SELECT COUNT(*) FROM ideb_resultados f
        JOIN escolas e ON e.codigo_escola = f.codigo_escola
        WHERE f.sigla_uf IS NOT NULL AND e.sigla_uf <> f.sigla_uf""")
    checar("UF do fato bate com a UF da escola", inconsistente == 0, f"{inconsistente}")


# ------------------------------------------------------- faixas dos valores

def checar_faixas(cur):
    titulo("6. FAIXAS DOS INDICADORES")

    faixas = [
        ("taxa_aprovacao_total", 0, 100),
        ("indicador_rendimento_p", 0, 1),
        ("nota_saeb_matematica", 0, 500),
        ("nota_saeb_portugues", 0, 500),
        ("nota_saeb_media_padronizada_n", 0, 10),
        ("ideb", 0, 10),
        ("meta_projetada", 0, 10),
    ]
    for coluna, minimo, maximo in faixas:
        fora = uma(cur, f"SELECT COUNT(*) FROM ideb_resultados "
                        f"WHERE {coluna} IS NOT NULL "
                        f"AND ({coluna} < ? OR {coluna} > ?)", (minimo, maximo))
        obs = cur.execute(f"SELECT MIN({coluna}), MAX({coluna}) "
                          f"FROM ideb_resultados WHERE {coluna} IS NOT NULL").fetchone()
        intervalo = f"observado {obs[0]}..{obs[1]}" if obs[0] is not None else "sem dados"
        checar(f"{coluna} dentro de [{minimo}, {maximo}]", fora == 0,
               f"{fora} fora | {intervalo}")

    # texto de ausencia ('-', 'ND') deveria ter virado NULL, nunca zero
    zeros = uma(cur, "SELECT COUNT(*) FROM ideb_resultados WHERE ideb = 0")
    checar("nenhum IDEB igual a zero (marcador nao virou 0)", zeros == 0, f"{zeros}")


# --------------------------------------------------- consistencia do calculo

def checar_formula_ideb(cur):
    """IDEB = N x P, arredondado a 1 casa. Valida se as colunas nao trocaram."""
    titulo("7. CONSISTENCIA DA FORMULA IDEB = N x P")

    total = uma(cur, """
        SELECT COUNT(*) FROM ideb_resultados
        WHERE ideb IS NOT NULL AND nota_saeb_media_padronizada_n IS NOT NULL
          AND indicador_rendimento_p IS NOT NULL""")

    divergentes = uma(cur, """
        SELECT COUNT(*) FROM ideb_resultados
        WHERE ideb IS NOT NULL AND nota_saeb_media_padronizada_n IS NOT NULL
          AND indicador_rendimento_p IS NOT NULL
          AND ABS(ideb - ROUND(nota_saeb_media_padronizada_n * indicador_rendimento_p, 1)) > 0.1""")

    print(f"  linhas com N, P e IDEB preenchidos: {total:,}")
    proporcao = divergentes / total if total else 1
    checar("IDEB confere com N x P em >99% das linhas", proporcao < 0.01,
           f"{divergentes:,} divergencias ({proporcao:.3%})")

    if divergentes:
        print("  exemplos de divergencia:")
        for r in cur.execute("""
                SELECT abrangencia, nivel_ensino, ano, codigo_entidade, rede,
                       nota_saeb_media_padronizada_n, indicador_rendimento_p, ideb
                FROM ideb_resultados
                WHERE ideb IS NOT NULL AND nota_saeb_media_padronizada_n IS NOT NULL
                  AND indicador_rendimento_p IS NOT NULL
                  AND ABS(ideb - ROUND(nota_saeb_media_padronizada_n
                                       * indicador_rendimento_p, 1)) > 0.1
                LIMIT 5"""):
            print(f"    {r[0]}/{r[1]}/{r[2]} {r[3]} {r[4]}: "
                  f"N={r[5]} P={r[6]} -> esperado {round(r[5] * r[6], 1)}, gravado {r[7]}")


# ------------------------------------------------------------- coluna JSON

def checar_json(cur):
    titulo("8. COLUNA JSON taxa_aprovacao_por_serie")

    invalidos = uma(cur, "SELECT COUNT(*) FROM ideb_resultados "
                         "WHERE taxa_aprovacao_por_serie IS NOT NULL "
                         "AND json_valid(taxa_aprovacao_por_serie) = 0")
    checar("todo JSON gravado e valido", invalidos == 0, f"{invalidos} invalidos")

    print("\n  series encontradas por nivel de ensino:")
    for nivel in sorted(NIVEIS):
        chaves = set()
        for (texto_json,) in cur.execute("""
                SELECT taxa_aprovacao_por_serie FROM ideb_resultados
                WHERE nivel_ensino = ? AND taxa_aprovacao_por_serie IS NOT NULL
                LIMIT 500""", (nivel,)):
            chaves.update(json.loads(texto_json).keys())
        print(f"    {nivel:<15} {sorted(chaves)}")

    # json_extract deve funcionar em consulta -- e assim que o sistema vai ler
    amostra = cur.execute("""
        SELECT ano, json_extract(taxa_aprovacao_por_serie, '$.\"5º\"')
        FROM ideb_resultados
        WHERE abrangencia='brasil' AND nivel_ensino='anos_iniciais'
          AND rede='Total' AND taxa_aprovacao_por_serie IS NOT NULL
        ORDER BY ano LIMIT 3""").fetchall()
    checar("json_extract funciona em consulta", len(amostra) > 0
           and all(v is not None for _, v in amostra), f"{amostra}")

    fora = uma(cur, """
        SELECT COUNT(*) FROM ideb_resultados r, json_each(r.taxa_aprovacao_por_serie) j
        WHERE r.taxa_aprovacao_por_serie IS NOT NULL
          AND (j.value < 0 OR j.value > 100)""")
    checar("todas as taxas por serie entre 0 e 100", fora == 0, f"{fora} fora da faixa")


# ---------------------------------------------------------------- cobertura

def checar_cobertura(cur):
    titulo("9. COBERTURA DOS DADOS (informativo)")

    total = uma(cur, "SELECT COUNT(*) FROM ideb_resultados")
    colunas = ["taxa_aprovacao_total", "indicador_rendimento_p", "nota_saeb_matematica",
               "nota_saeb_portugues", "nota_saeb_media_padronizada_n", "ideb",
               "meta_projetada", "taxa_aprovacao_por_serie"]
    for coluna in colunas:
        n = uma(cur, f"SELECT COUNT({coluna}) FROM ideb_resultados")
        print(f"  {coluna:<32} {100 * n / total:5.1f}%  ({n:,})")

    print("\n  observacao: lacunas sao esperadas. O SAEB so avalia escolas com numero")
    print("  minimo de participantes, e as metas do 1o ciclo cobrem apenas 2007-2021.")

    vazios = uma(cur, """
        SELECT COUNT(*) FROM ideb_resultados
        WHERE ideb IS NULL AND taxa_aprovacao_total IS NULL
          AND nota_saeb_matematica IS NULL AND meta_projetada IS NULL
          AND taxa_aprovacao_por_serie IS NULL""")
    checar("nenhuma linha totalmente vazia", vazios == 0, f"{vazios}")


# ------------------------------------------------- amostra ponta a ponta

def amostra_final(cur):
    titulo("10. AMOSTRA: Brasilia (5300108), anos iniciais, rede Publica")

    linhas = cur.execute("""
        SELECT ano, taxa_aprovacao_total, indicador_rendimento_p,
               nota_saeb_matematica, nota_saeb_portugues, ideb, meta_projetada
        FROM ideb_resultados
        WHERE abrangencia='municipio' AND codigo_municipio='5300108'
          AND nivel_ensino='anos_iniciais' AND rede='Pública'
        ORDER BY ano""").fetchall()

    def fmt(v, casas=1):
        """Valor ausente aparece como '-', nunca como 0 (ver secao 6)."""
        return f"{v:.{casas}f}" if v is not None else "-"

    print(f"  {'ano':<6}{'aprov':>7}{'P':>10}{'mat':>9}{'port':>9}{'IDEB':>7}{'meta':>7}")
    for r in linhas:
        print(f"  {r[0]:<6}{fmt(r[1]):>7}{fmt(r[2], 4):>10}{fmt(r[3]):>9}"
              f"{fmt(r[4]):>9}{fmt(r[5]):>7}{fmt(r[6]):>7}")

    ciclos_possiveis = sorted(a for a in ANOS if a <= max(ANOS))
    checar("serie historica do municipio de teste cobre todos os ciclos",
           len(linhas) == len(ciclos_possiveis),
           f"{len(linhas)} anos (esperado {len(ciclos_possiveis)})")


# -------------------------------------------------------------------- INSE

def checar_inse(cur):
    titulo("11. INSE (inse_municipios)")

    indices = {r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='inse_municipios'")}
    for idx in ("idx_inse_municipio", "idx_inse_filtro"):
        checar(f"indice '{idx}' criado", idx in indices)

    n = uma(cur, "SELECT COUNT(*) FROM inse_municipios")
    if not checar("inse_municipios tem linhas", n > 0, f"{n} linhas"):
        return

    anos = {r[0] for r in cur.execute("SELECT DISTINCT ano FROM inse_municipios")}
    checar("anos do INSE sao ciclos do IDEB", anos <= ANOS, f"{sorted(anos)}")
    for coluna, dominio in (("rede", REDES_INSE), ("localizacao", LOCALIZACOES_INSE)):
        valores = {r[0] for r in cur.execute(f"SELECT DISTINCT {coluna} FROM inse_municipios")}
        fora = valores - dominio
        checar(f"{coluna} do INSE dentro do vocabulario", not fora,
               f"inesperados: {sorted(fora)}" if fora else "")

    niveis = [f"pc_nivel_{i}" for i in range(1, 9)]
    todos_nulos = " AND ".join(f"{c} IS NULL" for c in niveis)
    fora_de_faixa = " OR ".join(f"{c} < 0 OR {c} > 100" for c in niveis)
    soma = " + ".join(f"COALESCE({c}, 0)" for c in niveis)
    regras = [
        ("nenhum media_inse = 0 (ausencia nunca vira zero)", "media_inse = 0"),
        ("media_inse dentro da escala do indicador (2 a 7)",
         "media_inse IS NOT NULL AND (media_inse < 2 OR media_inse > 7)"),
        ("nenhuma linha sem indicador algum", f"media_inse IS NULL AND {todos_nulos}"),
        ("percentuais por nivel entre 0 e 100", fora_de_faixa),
        ("percentuais por nivel somam 100 onde ha media",
         f"media_inse IS NOT NULL AND ({soma} < 99.5 OR {soma} > 100.5)"),
        ("codigo_municipio com 7 digitos", "LENGTH(codigo_municipio) <> 7"),
    ]
    for descricao, condicao in regras:
        n = uma(cur, f"SELECT COUNT(*) FROM inse_municipios WHERE {condicao}")
        checar(descricao, n == 0, f"{n} linhas violam" if n else "")

    n = uma(cur, """
        SELECT COUNT(*) FROM inse_municipios i
        LEFT JOIN municipios m ON m.codigo_municipio = i.codigo_municipio
        WHERE m.codigo_municipio IS NULL""")
    checar("nenhum municipio orfao no INSE", n == 0, f"{n} orfaos" if n else "")

    n = uma(cur, """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM inse_municipios
            GROUP BY ano, codigo_municipio, rede, localizacao HAVING COUNT(*) > 1)""")
    checar("chave (ano, municipio, rede, localizacao) sem duplicata", n == 0)

    # O par INSE x IDEB e a base dos modelos: quantos municipios com INSE tem IDEB
    # no mesmo ano e rede? Abaixo da metade, a analise perde chao.
    for ano in sorted(anos):
        total = uma(cur, """
            SELECT COUNT(*) FROM inse_municipios
            WHERE ano = ? AND rede = 'Pública' AND localizacao = 'Total'
              AND media_inse IS NOT NULL""", (ano,))
        pares = uma(cur, """
            SELECT COUNT(*) FROM inse_municipios i
            JOIN ideb_resultados r
              ON r.abrangencia = 'municipio' AND r.nivel_ensino = 'anos_iniciais'
             AND r.ano = i.ano AND r.codigo_entidade = i.codigo_municipio AND r.rede = i.rede
            WHERE i.ano = ? AND i.rede = 'Pública' AND i.localizacao = 'Total'
              AND i.media_inse IS NOT NULL AND r.ideb IS NOT NULL""", (ano,))
        fracao = pares / total if total else 0
        checar(f"par INSE x IDEB (publica, anos iniciais) cobre a maioria em {ano}",
               fracao >= 0.5, f"{pares}/{total} municipios ({100 * fracao:.0f}%)")


def main():
    if not DB_PATH.exists():
        print(f"Banco nao encontrado em {DB_PATH}.")
        print("Rode `python -m DataBase.importData` para cria-lo.")
        return

    with conectar(exigir_existente=True) as conexao:
        cur = conexao.cursor()

        checar_estrutura(cur)
        checar_volumetria(cur)
        checar_dominios(cur)
        checar_coerencia_abrangencia(cur)
        checar_chaves(cur)
        checar_faixas(cur)
        checar_formula_ideb(cur)
        checar_json(cur)
        checar_cobertura(cur)
        amostra_final(cur)
        checar_inse(cur)

    titulo("RESUMO")
    falhas = [d for d, ok in resultados if not ok]
    print(f"  {len(resultados) - len(falhas)} de {len(resultados)} verificacoes passaram")
    if falhas:
        print("\n  verificacoes que falharam:")
        for d in falhas:
            print(f"    - {d}")
    else:
        print("  banco integro: todas as verificacoes passaram")


if __name__ == "__main__":
    main()