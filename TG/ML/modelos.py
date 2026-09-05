"""
modelos.py — Os três modelos de previsão, em ordem de complexidade.

1. BaselineIngenuo   : prevê que o IDEB não muda (ideb_previsto(T+1) = ideb(T)).
                       É o piso: um modelo que não bate isto não serve.
2. Regressão linear  : LinearRegression sobre as features padronizadas.
3. Random Forest     : RandomForestRegressor.

Todos expõem a mesma interface do scikit-learn (fit / predict), para a validação
tratá-los de forma uniforme.
"""
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class BaselineIngenuo(BaseEstimator, RegressorMixin):
    """Prevê ideb(T+1) = ideb(T). Ignora o treino; só repete a coluna ideb_T."""

    def __init__(self, coluna_ideb_t: str = "ideb_T"):
        self.coluna_ideb_t = coluna_ideb_t

    def fit(self, X, y=None):
        return self

    def predict(self, X):
        return X[self.coluna_ideb_t].to_numpy()


def criar_modelos() -> dict:
    """Fábrica dos modelos a comparar. Chave = nome legível."""
    return {
        "baseline": BaselineIngenuo(),
        "regressao_linear": Pipeline([
            ("scaler", StandardScaler()),
            ("reg", LinearRegression()),
        ]),
        "random_forest": RandomForestRegressor(
            n_estimators=300,
            max_depth=None,
            min_samples_leaf=5,
            n_jobs=-1,
            random_state=42,
        ),
    }
