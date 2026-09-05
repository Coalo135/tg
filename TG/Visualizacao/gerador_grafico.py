"""
gerador_grafico.py — GeradorGrafico: camada de visualização.

Consome as médias/séries já calculadas pelo módulo Estatística (taxa de aprovação
por série, evolução do IDEB, comparação Mat x Port etc.) e transforma em gráficos:
linha para evolução temporal, barra para comparações (série/rede/localidade/matérias).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sem display (salva PNG)
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="dark")


class GeradorGrafico:
    def __init__(self, pasta_saida=None):
        self.pasta_saida = Path(pasta_saida or Path(__file__).resolve().parent / "saidas")
        self.pasta_saida.mkdir(parents=True, exist_ok=True)

    def linha_evolucao_temporal(self, evolucao, titulo="Evolução do IDEB",
                                 nome_arquivo="evolucao_ideb.png"):
        """evolucao: dict {ano: ideb_medio}, como devolvido por
        `Estatistica.separacao_valores.evolucao_ideb`."""
        anos = sorted(evolucao)
        valores = [evolucao[ano] for ano in anos]

        fig, ax = plt.subplots(figsize=(8, 4.5))
        sns.lineplot(x=anos, y=valores, marker="o", markersize=9,
                     linewidth=2.5, color="#2563eb", ax=ax, zorder=3)

        for ano, valor in zip(anos, valores):
            ax.annotate(f"{valor:.2f}", (ano, valor), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=9, fontweight="bold")

        ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("Ano")
        ax.set_ylabel("IDEB")
        ax.set_xticks(anos)
        ax.set_axisbelow(True)
        ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.6, zorder=0)
        sns.despine(ax=ax)
        return self._salvar(fig, nome_arquivo)

    def barra_comparacao(self, valores, titulo, eixo_y="Valor", nome_arquivo="comparacao.png"):
        """valores: dict {rótulo: número} — serve pra série, rede, localidade ou Mat x Port."""
        rotulos = list(valores.keys())
        alturas = list(valores.values())

        fig, ax = plt.subplots(figsize=(8, 4.5))
        sns.barplot(x=rotulos, y=alturas, color="#2563eb", edgecolor="none", ax=ax, zorder=3)
        ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel(eixo_y)
        ax.bar_label(ax.containers[0], fmt="%.1f", padding=3, fontsize=9, fontweight="bold")
        ax.set_axisbelow(True)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.8, alpha=0.6, zorder=0)
        sns.despine(ax=ax)
        return self._salvar(fig, nome_arquivo)

    def heatmap_rendimento_desempenho(self, df, titulo="Rendimento x Desempenho",
                                       nome_arquivo="heatmap_rendimento_desempenho.png"):
        """Dispersão de Rendimento (P) x Desempenho (N), dividida em 4 quadrantes
        pela mediana de cada eixo. Cada ponto é um registro real de `df` — mostra
        se o IDEB alto vem de aprovação inflada (P alto, N baixo) ou de
        aprendizado real (P alto, N alto).

        Um heatmap de contagem por quadrante fica sem informação quando o filtro
        tem pouca variedade de localidade (ex: só um município por vários anos):
        a mediana sempre separa ~metade dos registros, seja qual for o valor.
        O scatter mostra os pontos de verdade, então funciona com qualquer volume
        de dados.

        df precisa ter as colunas indicador_rendimento_p e nota_saeb_media_padronizada_n.
        Se `df` tiver a coluna "ano" e houver poucos pontos (<=15), cada ponto é
        rotulado com o ano pra facilitar a leitura.
        """
        colunas = ["indicador_rendimento_p", "nota_saeb_media_padronizada_n"]
        if "ano" in df.columns:
            colunas.append("ano")
        eixos = ["indicador_rendimento_p", "nota_saeb_media_padronizada_n"]
        dados = df[colunas].dropna(subset=eixos)
        dados = dados.astype(dict.fromkeys(eixos, float))

        mediana_p = dados["indicador_rendimento_p"].median()
        mediana_n = dados["nota_saeb_media_padronizada_n"].median()

        alto_p_alto_n = ((dados["indicador_rendimento_p"] >= mediana_p) &
                          (dados["nota_saeb_media_padronizada_n"] >= mediana_n)).sum()
        alto_p_baixo_n = ((dados["indicador_rendimento_p"] >= mediana_p) &
                           (dados["nota_saeb_media_padronizada_n"] < mediana_n)).sum()
        baixo_p_alto_n = ((dados["indicador_rendimento_p"] < mediana_p) &
                           (dados["nota_saeb_media_padronizada_n"] >= mediana_n)).sum()
        baixo_p_baixo_n = ((dados["indicador_rendimento_p"] < mediana_p) &
                            (dados["nota_saeb_media_padronizada_n"] < mediana_n)).sum()

        fig, ax = plt.subplots(figsize=(8, 6.5))

        # margem em volta dos pontos pra sobrar espaço pros rótulos de quadrante
        amplitude_p = dados["indicador_rendimento_p"].max() - dados["indicador_rendimento_p"].min()
        amplitude_n = (dados["nota_saeb_media_padronizada_n"].max()
                       - dados["nota_saeb_media_padronizada_n"].min())
        # `or 1`: com um único ponto a amplitude é 0 e os limites do eixo
        # colapsariam, deixando o ponto exatamente em cima da borda.
        margem_x = amplitude_p * 0.15 or 1
        margem_y = amplitude_n * 0.15 or 1
        xmin = dados["indicador_rendimento_p"].min() - margem_x
        xmax = dados["indicador_rendimento_p"].max() + margem_x
        ymin = dados["nota_saeb_media_padronizada_n"].min() - margem_y
        ymax = dados["nota_saeb_media_padronizada_n"].max() + margem_y

        # sombreado de fundo por quadrante (cor = leitura pedagógica do quadrante)
        from matplotlib.patches import Rectangle
        ax.add_patch(Rectangle((mediana_p, mediana_n), xmax - mediana_p, ymax - mediana_n,
                                color="#16a34a", alpha=0.08, zorder=0))
        ax.add_patch(Rectangle((xmin, mediana_n), mediana_p - xmin, ymax - mediana_n,
                                color="#d97706", alpha=0.08, zorder=0))
        ax.add_patch(Rectangle((mediana_p, ymin), xmax - mediana_p, mediana_n - ymin,
                                color="#dc2626", alpha=0.08, zorder=0))
        ax.add_patch(Rectangle((xmin, ymin), mediana_p - xmin, mediana_n - ymin,
                                color="#7f1d1d", alpha=0.08, zorder=0))

        ax.axvline(mediana_p, color="#64748b", linestyle="--", linewidth=1, zorder=1)
        ax.axhline(mediana_n, color="#64748b", linestyle="--", linewidth=1, zorder=1)

        ax.scatter(dados["indicador_rendimento_p"], dados["nota_saeb_media_padronizada_n"],
                   s=100, color="#2563eb", edgecolor="white", linewidth=1, zorder=3)

        if "ano" in dados.columns and len(dados) <= 15:
            for _, row in dados.iterrows():
                ax.annotate(str(int(row["ano"])),
                           (row["indicador_rendimento_p"], row["nota_saeb_media_padronizada_n"]),
                           textcoords="offset points", xytext=(0, 8),
                           ha="center", fontsize=8, fontweight="bold", zorder=4)

        # rótulos explicando o que cada quadrante significa + quantos registros caem nele
        rotulos_quadrante = [
            (xmax, ymax, "right", "top", f"Aprendizado real ({alto_p_alto_n})", "#15803d"),
            (xmin, ymax, "left", "top", f"Reprovação rigorosa ({baixo_p_alto_n})", "#b45309"),
            (xmax, ymin, "right", "bottom", f"Aprovação inflada ({alto_p_baixo_n})", "#b91c1c"),
            (xmin, ymin, "left", "bottom", f"Situação crítica ({baixo_p_baixo_n})", "#7f1d1d"),
        ]
        for x, y, ha, va, texto, cor in rotulos_quadrante:
            deslocamento_x = -0.015 * (xmax - xmin) if ha == "right" else 0.015 * (xmax - xmin)
            deslocamento_y = -0.03 * (ymax - ymin) if va == "top" else 0.03 * (ymax - ymin)
            ax.text(x + deslocamento_x, y - deslocamento_y, texto, ha=ha, va=va,
                    fontsize=9, fontweight="bold", color=cor)

        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel(f"Indicador de Rendimento — P  (mediana = {mediana_p:.2f})")
        ax.set_ylabel(f"Nota SAEB padronizada — N  (mediana = {mediana_n:.2f})")
        ax.set_axisbelow(True)
        ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.4, zorder=0)
        sns.despine(ax=ax)
        return self._salvar(fig, nome_arquivo)

    def _salvar(self, fig, nome_arquivo):
        caminho = self.pasta_saida / nome_arquivo
        fig.tight_layout()
        fig.savefig(caminho, dpi=110)
        plt.close(fig)
        return str(caminho)