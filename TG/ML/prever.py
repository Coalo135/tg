"""
prever.py — Produto final: projeta o IDEB de um município para o próximo ciclo.

Fluxo:
  1. Escolhe, POR NÍVEL, o modelo com menor MAE na validação temporal (validacao.py).
  2. Re-treina esse modelo em toda a base de pares daquele nível.
  3. Para um município, monta as features do último ciclo disponível (T) e prevê
     o IDEB de T+1.
  4. Emite um veredito e salva um gráfico (histórico + ponto projetado + última meta).

O último ciclo é lido dos dados, não fixado no código. Antes estava escrito
`ULTIMO_CICLO = 2023`; com as planilhas de 2025 no banco, isso projetaria 2025 a
partir de 2023 ignorando o 2025 real — uma previsão de um ciclo que já aconteceu.

Observação sobre o veredito: o INEP só projetou metas até 2021, então NÃO existe
meta oficial para os ciclos recentes. O veredito compara a projeção com a última
meta oficial disponível e com o próprio IDEB do último ciclo (trajetória).
"""
import logging
import warnings

import matplotlib

matplotlib.use("Agg")  # backend sem display (salva PNG)
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from config import PASSO_CICLO, PASTA_ML  # noqa: E402
from ML.dados import carregar_base, ciclos  # noqa: E402
from ML.dataset import ANOS_POS_PANDEMIA, FEATURES, montar_pares, montar_xy  # noqa: E402
from ML.modelos import criar_modelos  # noqa: E402
from ML.validacao import validar  # noqa: E402

logger = logging.getLogger(__name__)


def escolher_e_treinar(pares: pd.DataFrame) -> dict:
    """Para cada nível, escolhe o modelo de menor MAE e re-treina na base completa."""
    tabela = validar(pares)
    modelos_finais = {}
    for nivel in tabela["nivel"].unique():
        bloco = tabela[tabela["nivel"] == nivel].sort_values("MAE")
        nome = bloco.iloc[0]["modelo"]
        mae = bloco.iloc[0]["MAE"]
        sub = pares[pares["nivel_ensino"] == nivel]
        X, y, _ = montar_xy(sub, FEATURES, verbose=False)
        modelo = criar_modelos()[nome]
        modelo.fit(X, y)
        modelos_finais[nivel] = {"modelo": modelo, "nome": nome, "mae": mae}
        logger.info("  %s: modelo oficial = %s (MAE validação = %.3f)", nivel, nome, mae)
    return modelos_finais


def _features_ultimo_ciclo(base: pd.DataFrame, codigo_municipio: str, nivel: str):
    """Monta a linha de features em T = último ciclo, para prever T+1."""
    ultimo = max(ciclos(base))
    anterior = ultimo - PASSO_CICLO
    proximo = ultimo + PASSO_CICLO

    sub = base[(base["codigo_municipio"] == str(codigo_municipio))
               & (base["nivel_ensino"] == nivel)].set_index("ano")
    if ultimo not in sub.index:
        return None, None, ultimo, proximo

    ideb_t = sub.loc[ultimo, "ideb"]
    ideb_ant = sub.loc[anterior, "ideb"] if anterior in sub.index else float("nan")
    feats = pd.DataFrame([{
        "ideb_T": ideb_t,
        "ideb_T_menos_1": ideb_ant,
        "variacao_ideb": ideb_t - ideb_ant,
        "rendimento_T": sub.loc[ultimo, "indicador_rendimento_p"],
        "saeb_T": sub.loc[ultimo, "nota_saeb_media_padronizada_n"],
        "flag_pos_pandemia": int(proximo in ANOS_POS_PANDEMIA),
    }])[FEATURES]
    return feats, sub, ultimo, proximo


def prever_ideb(codigo_municipio: str, nivel: str, base: pd.DataFrame,
                modelos_finais: dict, salvar_grafico: bool = True) -> dict:
    """Projeta o IDEB do próximo ciclo para um município/nível e emite veredito."""
    if nivel not in modelos_finais:
        raise ValueError(f"Sem modelo treinado para o nível {nivel!r}")

    feats, serie, ultimo, proximo = _features_ultimo_ciclo(base, codigo_municipio, nivel)
    if feats is None or feats.isna().any(axis=None):
        raise ValueError(
            f"Features insuficientes para prever {codigo_municipio}/{nivel} "
            f"(dados ausentes no ciclo {ultimo})"
        )

    info = modelos_finais[nivel]
    previsao = float(info["modelo"].predict(feats)[0])
    ideb_ultimo = float(feats["ideb_T"].iloc[0])

    # última meta oficial disponível (INEP não projetou após 2021)
    metas = serie["meta_projetada"].dropna()
    ultima_meta = float(metas.iloc[-1]) if not metas.empty else None
    ano_ultima_meta = int(metas.index[-1]) if not metas.empty else None

    if previsao > ideb_ultimo:
        tendencia = "alta"
    elif previsao < ideb_ultimo:
        tendencia = "queda"
    else:
        tendencia = "estável"

    if ultima_meta is not None:
        veredito = ("acima da última meta oficial" if previsao >= ultima_meta
                    else "abaixo da última meta oficial")
    else:
        veredito = "sem meta oficial de referência"

    nome = serie["nome_entidade"].iloc[-1] if "nome_entidade" in serie else str(codigo_municipio)
    resultado = {
        "municipio": nome,
        "codigo_municipio": str(codigo_municipio),
        "nivel_ensino": nivel,
        "ano_base": ultimo,
        "ideb_ano_base": round(ideb_ultimo, 2),
        "ano_previsto": proximo,
        "previsao": round(previsao, 2),
        "tendencia": tendencia,
        "ultima_meta_oficial": ultima_meta,
        "ano_ultima_meta": ano_ultima_meta,
        "veredito": veredito,
        "modelo": info["nome"],
        "mae_validacao": round(info["mae"], 3),
    }
    if salvar_grafico:
        resultado["grafico"] = _grafico(serie, previsao, resultado)
    return resultado


def _grafico(serie: pd.DataFrame, previsao: float, r: dict) -> str:
    PASTA_ML.mkdir(parents=True, exist_ok=True)
    hist = serie["ideb"].dropna()

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(hist.index, hist.values, "-o", label="IDEB observado", color="#2563eb")
    ax.plot([r["ano_previsto"]], [previsao], "D", markersize=11, color="#dc2626",
            label=f"Projeção {r['ano_previsto']}")
    ax.plot([r["ano_base"], r["ano_previsto"]], [r["ideb_ano_base"], previsao],
            "--", color="#dc2626", alpha=0.6)
    if r["ultima_meta_oficial"] is not None:
        ax.axhline(r["ultima_meta_oficial"], ls=":", color="#059669",
                   label=f"Última meta oficial ({r['ano_ultima_meta']})")
    ax.set_title(f"{r['municipio']} — {r['nivel_ensino']}\n"
                 f"Projeção {r['ano_previsto']}: {previsao:.2f} ({r['tendencia']}) | "
                 f"modelo: {r['modelo']}")
    ax.set_xlabel("Ano do ciclo IDEB")
    ax.set_ylabel("IDEB")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()

    caminho = PASTA_ML / f"projecao_{r['codigo_municipio']}_{r['nivel_ensino']}.png"
    fig.savefig(caminho, dpi=110)
    plt.close(fig)
    return str(caminho)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    warnings.filterwarnings("ignore")
    base = carregar_base()
    pares = montar_pares(base)
    logger.info("Treinando modelos oficiais por nível...")
    modelos_finais = escolher_e_treinar(pares)

    # Vitrine: Sobral/CE (referência da literatura) + a capital Fortaleza/CE
    exemplos = [("2312908", "Sobral/CE"), ("2304400", "Fortaleza/CE")]
    for codigo, rotulo in exemplos:
        for nivel in ("anos_iniciais", "anos_finais"):
            print(f"\n=== {rotulo} — {nivel} ===")
            try:
                r = prever_ideb(codigo, nivel, base, modelos_finais)
            except ValueError as erro:
                print(f"  não foi possível prever: {erro}")
                continue
            for k, v in r.items():
                print(f"  {k}: {v}")
