"""Predicciones.

1. Probabilidad de que cada cliente vuelva a comprar en los próximos 90 días.
   Se entrena "mirando hacia atrás": se toma una fecha del pasado, se calculan
   los indicadores que se conocían ese día y se verifica quién compró después.
   Así el modelo aprende de lo que realmente pasó, sin ver el futuro.
2. Pronóstico de ventas de los próximos tres meses, con índice estacional.

Ambos se comparan contra una regla simple para saber si aportan algo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from src import config as cfg

VARIABLES = ["recencia", "frecuencia_12m", "monto_12m", "monto_3m", "tendencia",
             "antiguedad", "ciclo", "atraso_vs_ciclo", "n_categorias", "share_usd",
             "renovaciones_en_horizonte"]


def _variables(ventas: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    v = ventas[ventas.fecha <= corte]
    if v.empty:
        return pd.DataFrame()
    g = v.groupby("cliente_id")
    x = pd.DataFrame(index=g.size().index)
    x["recencia"] = (corte - g.fecha.max()).dt.days
    x["antiguedad"] = (corte - g.fecha.min()).dt.days
    v12 = v[v.fecha > corte - pd.DateOffset(months=12)]
    v6a = v[(v.fecha > corte - pd.DateOffset(months=12)) & (v.fecha <= corte - pd.DateOffset(months=6))]
    v6b = v[v.fecha > corte - pd.DateOffset(months=6)]
    v3 = v[v.fecha > corte - pd.DateOffset(months=3)]
    x["frecuencia_12m"] = v12.groupby("cliente_id").mes.nunique()
    x["monto_12m"] = v12.groupby("cliente_id").valor_cop.sum()
    x["monto_3m"] = v3.groupby("cliente_id").valor_cop.sum()
    a, b = v6a.groupby("cliente_id").valor_cop.sum(), v6b.groupby("cliente_id").valor_cop.sum()
    x["tendencia"] = (b.reindex(x.index).fillna(0) - a.reindex(x.index).fillna(0)) / (
        a.reindex(x.index).fillna(0) + b.reindex(x.index).fillna(0) + 1)
    ciclo = (v[["cliente_id", "fecha"]].drop_duplicates().sort_values("fecha")
             .groupby("cliente_id").fecha.apply(lambda s: s.diff().dt.days.median()))
    x["ciclo"] = ciclo
    x["atraso_vs_ciclo"] = x.recencia / x.ciclo.fillna(cfg.DIAS_ACTIVO).clip(lower=7)
    x["n_categorias"] = g.categoria.nunique()
    x["share_usd"] = (v[v.moneda == "USD"].groupby("cliente_id").valor_cop.sum()
                      / g.valor_cop.sum())
    # Renovaciones que caen dentro del horizonte (señal fuerte de recompra)
    r = v[v.meses_renovacion > 0].groupby(["cliente_id", "producto_id"]).agg(
        ult=("fecha", "max"), meses=("meses_renovacion", "first")).reset_index()
    r["vence"] = [d + pd.DateOffset(months=int(m)) for d, m in zip(r.ult, r.meses)]
    en_h = r[(r.vence > corte) & (r.vence <= corte + pd.Timedelta(days=cfg.HORIZONTE_DIAS))]
    x["renovaciones_en_horizonte"] = en_h.groupby("cliente_id").size()
    return x.fillna({"frecuencia_12m": 0, "monto_12m": 0, "monto_3m": 0, "share_usd": 0,
                     "renovaciones_en_horizonte": 0})


def _etiqueta(ventas, corte, indice) -> pd.Series:
    fut = ventas[(ventas.fecha > corte) &
                 (ventas.fecha <= corte + pd.Timedelta(days=cfg.HORIZONTE_DIAS))]
    return pd.Series(indice.isin(fut.cliente_id.unique()).astype(int), index=indice)


def _modelo():
    return HistGradientBoostingClassifier(max_iter=120, learning_rate=0.04, max_depth=3,
                                          min_samples_leaf=40, l2_regularization=2.0,
                                          random_state=cfg.SEMILLA)


class Regla:
    """Regla de referencia calibrada: tasa histórica de recompra según cuántos
    días lleva el cliente sin comprar. Es lo que haría una persona con Excel."""
    TRAMOS = [0, 30, 60, 90, 120, 180, 270, 365, 10_000]

    def fit(self, x, y):
        t = pd.cut(x.recencia, self.TRAMOS, include_lowest=True)
        self.tasas = y.groupby(t, observed=False).mean().fillna(y.mean())
        return self

    def predict(self, x):
        t = pd.cut(x.recencia, self.TRAMOS, include_lowest=True)
        return t.map(self.tasas).astype(float).to_numpy()


def _armar(ventas, c):
    x = _variables(ventas, c)
    x = x[x.recencia <= 540]                       # clientes con actividad reciente razonable
    return x, _etiqueta(ventas, c, x.index)


def _entrenar(ventas, hasta: pd.Timestamp, n_cortes: int = 16):
    """Entrena con cortes cuyo resultado ya se conocía en la fecha `hasta`."""
    h = pd.Timedelta(days=cfg.HORIZONTE_DIAS)
    bloques = [_armar(ventas, hasta - h - pd.DateOffset(months=k)) for k in range(n_cortes)]
    bloques = [b for b in bloques if len(b[0]) >= 20]
    x = pd.concat([b[0] for b in bloques])[VARIABLES]
    y = pd.concat([b[1] for b in bloques])
    return _modelo().fit(x, y), Regla().fit(x, y), len(x)


def _predecir(mod, regla, x):
    p_mod = mod.predict_proba(x[VARIABLES])[:, 1]
    p_regla = regla.predict(x)
    return p_mod, p_regla, 0.5 * p_mod + 0.5 * p_regla


def entrenar_y_puntuar(ventas: pd.DataFrame, corte: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Prueba hacia atrás en 4 cortes mensuales y luego puntúa a los clientes hoy.

    En cada corte de prueba el modelo solo ve lo que se sabía ese día.
    Se comparan tres alternativas: la regla de recencia, el modelo y la mezcla
    de ambos (promedio de probabilidades). La mezcla es la que se usa.
    """
    h = pd.Timedelta(days=cfg.HORIZONTE_DIAS)
    pruebas = []
    for k in range(4):
        c = corte - h - pd.DateOffset(months=k)
        x_te, y_te = _armar(ventas, c)
        mod, regla, n_tr = _entrenar(ventas, c)
        p_mod, p_regla, p_mix = _predecir(mod, regla, x_te)
        top = pd.Series(p_mix, index=x_te.index).nsmallest(30).index
        top_r = pd.Series(p_regla - x_te.recencia.to_numpy() / 1e6, index=x_te.index).nsmallest(30).index
        pruebas.append({
            "corte": str(c.date()), "clientes": int(len(x_te)), "filas_entrenamiento": n_tr,
            "tasa_recompra": float(y_te.mean()),
            "auc_regla": float(roc_auc_score(y_te, p_regla - x_te.recencia / 1e6)),
            "auc_modelo": float(roc_auc_score(y_te, p_mod)),
            "auc_mezcla": float(roc_auc_score(y_te, p_mix)),
            "acierto_top30_mezcla": float((1 - y_te.loc[top]).mean()),
            "acierto_top30_regla": float((1 - y_te.loc[top_r]).mean()),
            "brier_mezcla": float(np.mean((p_mix - y_te) ** 2)),
        })
    pr = pd.DataFrame(pruebas)
    metricas = {"pruebas": pruebas,
                **{f"{c}_promedio": float(pr[c].mean()) for c in
                   ["auc_regla", "auc_modelo", "auc_mezcla", "acierto_top30_mezcla",
                    "acierto_top30_regla", "brier_mezcla", "tasa_recompra"]},
                "cortes_donde_mezcla_supera_regla": int((pr.auc_mezcla > pr.auc_regla).sum())}

    # Modelo final: entrenado con todo lo conocido a la fecha de corte
    mod, regla, _ = _entrenar(ventas, corte)
    x_hoy = _variables(ventas, corte)
    _, _, p = _predecir(mod, regla, x_hoy)
    prob = pd.Series(p, index=x_hoy.index, name="prob_compra_90d")
    return prob.reset_index(), metricas


def pronostico_ventas(ventas: pd.DataFrame, meses: int = 3) -> tuple[pd.DataFrame, dict]:
    """Nivel reciente × índice estacional del mes. Simple, explicable y verificable."""
    serie = ventas.groupby("mes").valor_cop.sum().sort_index()
    serie = serie[serie.index < serie.index.max()] if _mes_incompleto(ventas) else serie

    def indice_estacional(hist: pd.Series) -> pd.Series:
        """Razón contra la media móvil centrada de 12 meses: separa la estacionalidad
        del crecimiento de la cartera."""
        mm = hist.rolling(12, center=True).mean().rolling(2).mean().shift(-1)
        razon = (hist / mm).dropna()
        idx = razon.groupby(razon.index.month).mean()
        idx = idx.reindex(range(1, 13)).fillna(1.0)
        return idx / idx.mean()

    def predecir(hist: pd.Series, objetivo: pd.Timestamp) -> float:
        idx = indice_estacional(hist)
        recientes = hist.iloc[-6:]
        nivel = (recientes / idx.loc[recientes.index.month].to_numpy()).mean()
        return float(nivel * idx.loc[objetivo.month])

    # Prueba hacia atrás en los últimos 6 meses
    errores, errores_ingenuo = [], []
    for i in range(6, 0, -1):
        hist, real = serie.iloc[:-i], serie.iloc[-i]
        errores.append(abs(predecir(hist, serie.index[-i]) - real) / real)
        errores_ingenuo.append(abs(hist.iloc[-1] - real) / real)
    futuro = pd.date_range(serie.index.max() + pd.DateOffset(months=1), periods=meses, freq="MS")
    pron = pd.DataFrame({"mes": futuro,
                         "pronostico_cop": [predecir(serie, m) for m in futuro]})
    margen = np.mean(errores)
    pron["minimo_cop"] = pron.pronostico_cop * (1 - margen)
    pron["maximo_cop"] = pron.pronostico_cop * (1 + margen)
    return pron, {"mape_pronostico": float(np.mean(errores)),
                  "mape_mes_anterior": float(np.mean(errores_ingenuo))}


def _mes_incompleto(ventas: pd.DataFrame) -> bool:
    ultimo = ventas.fecha.max()
    return ultimo.day < 25
