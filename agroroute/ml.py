"""Modelos de Machine Learning do NOKAHI AgroRoute.

Três modelos práticos, treináveis com os dados que a operação já gera:

1. FuelCalibrator — calibra o modelo físico de consumo por veículo a partir da
   telemetria (litros previstos × litros reais). Fecha o loop de aprendizado:
   o custo estimado converge para o consumo medido de cada caminhão.

2. MaintenanceRiskModel — regressão logística que estima a probabilidade de um
   componente precisar de manutenção na próxima janela, a partir de desgaste,
   km desde a última troca, severidade do terreno e carga. Vem com pesos padrão
   calibrados por domínio (funciona sem dados) e pode ser re-treinado.

3. DemandForecaster — previsão de demanda diária de rotas na safra (tendência +
   sazonalidade semanal), para dimensionar frota e turnos.

Dependências: numpy, scikit-learn (já no ambiente).
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


# ---------------------------------------------------------------------------
# 1) Calibração de consumo por veículo
# ---------------------------------------------------------------------------

class FuelCalibrator:
    """Fator multiplicativo por veículo: litros_reais ≈ fator × litros_previstos.

    Mínimos quadrados pela origem (robusto a poucos pontos). Guarda métricas de
    qualidade (R², MAPE) para saber se vale aplicar a correção.
    """

    def __init__(self, factor: float = 1.0):
        self.factor = factor
        self.r2: float | None = None
        self.mape: float | None = None
        self.n: int = 0

    def fit(self, predicted, actual) -> "FuelCalibrator":
        p = np.asarray(predicted, dtype=float)
        a = np.asarray(actual, dtype=float)
        mask = (p > 0) & np.isfinite(p) & np.isfinite(a)
        p, a = p[mask], a[mask]
        self.n = int(p.size)
        if self.n == 0:
            self.factor = 1.0
            return self
        # least squares através da origem: factor = <p,a>/<p,p>
        self.factor = float(np.dot(p, a) / np.dot(p, p))
        pred = self.factor * p
        ss_res = float(np.sum((a - pred) ** 2))
        # modelo pela origem (sem intercepto) -> R² usa soma de quadrados NÃO
        # centrada (sum(a²)); a versão centrada dá R² negativo espúrio
        ss_tot = float(np.sum(a ** 2)) or 1.0
        self.r2 = 1.0 - ss_res / ss_tot
        self.mape = float(np.mean(np.abs((a - pred) / a))) if np.all(a != 0) else None
        return self

    def apply(self, predicted_liters: float) -> float:
        return predicted_liters * self.factor

    def as_dict(self) -> dict:
        return {"factor": round(self.factor, 4), "r2": self.r2, "mape": self.mape, "n": self.n}


# ---------------------------------------------------------------------------
# 2) Risco de manutenção (probabilidade de intervenção na próxima janela)
# ---------------------------------------------------------------------------

# features: [wear_pct/100, km_desde_troca/limite, severidade_terreno(0-1), carga(0-1)]
_DEFAULT_COEF = np.array([4.2, 1.6, 0.9, 0.5])   # calibrado por domínio
_DEFAULT_INTERCEPT = -3.0


class MaintenanceRiskModel:
    """Logística: P(precisa manutenção em ~30 dias) a partir de 4 features."""

    FEATURES = ["wear", "usage_ratio", "terrain_severity", "load"]

    def __init__(self):
        self._clf: LogisticRegression | None = None
        self.coef = _DEFAULT_COEF.copy()
        self.intercept = _DEFAULT_INTERCEPT

    def fit(self, X, y) -> "MaintenanceRiskModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        if len(np.unique(y)) < 2:
            return self  # sem as duas classes, mantém os pesos padrão
        self._clf = LogisticRegression(max_iter=1000)
        self._clf.fit(X, y)
        self.coef = self._clf.coef_[0]
        self.intercept = float(self._clf.intercept_[0])
        return self

    def risk(self, features) -> float:
        x = np.asarray(features, dtype=float)
        z = float(np.dot(self.coef, x) + self.intercept)
        return 1.0 / (1.0 + np.exp(-z))

    def risk_from_component(self, wear_pct: float, usage_ratio: float,
                            terrain_severity: float = 0.3, load: float = 0.7) -> float:
        return self.risk([wear_pct / 100.0, usage_ratio, terrain_severity, load])

    @staticmethod
    def label(prob: float) -> str:
        if prob >= 0.75:
            return "crítico"
        if prob >= 0.5:
            return "alto"
        if prob >= 0.25:
            return "moderado"
        return "baixo"


# ---------------------------------------------------------------------------
# 3) Previsão de demanda diária de rotas
# ---------------------------------------------------------------------------

class DemandForecaster:
    """Tendência linear + sazonalidade semanal (média por dia da semana)."""

    def __init__(self):
        self.slope = 0.0
        self.intercept = 0.0
        self.weekly = np.zeros(7)
        self.n = 0

    def fit(self, series) -> "DemandForecaster":
        y = np.asarray(series, dtype=float)
        self.n = int(y.size)
        if self.n < 2:
            self.intercept = float(y.mean()) if self.n else 0.0
            return self
        t = np.arange(self.n)
        # tendência por regressão linear simples
        A = np.vstack([t, np.ones_like(t)]).T
        self.slope, self.intercept = np.linalg.lstsq(A, y, rcond=None)[0]
        trend = self.slope * t + self.intercept
        resid = y - trend
        # sazonalidade semanal média (assume série diária começando na segunda)
        for d in range(7):
            vals = resid[d::7]
            self.weekly[d] = float(vals.mean()) if vals.size else 0.0
        return self

    def forecast(self, horizon: int = 14) -> list[float]:
        out = []
        for h in range(1, horizon + 1):
            t = self.n + h - 1
            val = self.slope * t + self.intercept + self.weekly[t % 7]
            out.append(round(max(0.0, float(val)), 1))
        return out
