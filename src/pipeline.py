"""Corre todo el proceso mensual de punta a punta.

    python -m src.pipeline            # usa los archivos de data/raw/
    python -m src.pipeline --demo     # genera datos sintéticos primero
    python -m src.pipeline --facturacion data/ejemplos/ventas_prueba_green_2.csv
                                      # importa una exportación plana de facturación
    python -m src.pipeline --paquete data/ejemplos/paquete_oficial
                                      # importa el paquete oficial de recursos del reto

Deja en data/processed/ lo que lee el tablero y en outputs/ un Excel de
alertas para repartir al equipo comercial.
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from src import analitica, etl, modelo
from src import config as cfg
from src.config import DATOS_CRUDOS, DATOS_PROCESADOS, SALIDAS


def _limpiar_extras_de_fuente() -> None:
    """Archivos que solo trae el paquete oficial; al cambiar de fuente se quitan."""
    for nombre in ("base_instalada.csv", "parametros.json", "referencia_oficial.json",
                   "referencia_clientes.csv"):
        (DATOS_CRUDOS / nombre).unlink(missing_ok=True)


def validar_contra_referencia(ventas: pd.DataFrame, ficha: pd.DataFrame, clientes: pd.DataFrame,
                              ren_base: pd.DataFrame | None, corte: pd.Timestamp) -> dict | None:
    """Compara con las cifras de referencia del paquete oficial (05_Validacion)."""
    ref_p = DATOS_CRUDOS / "referencia_oficial.json"
    if not ref_p.exists():
        return None
    ref = json.loads(ref_p.read_text(encoding="utf-8-sig"))
    v = ventas[ventas.fecha <= corte]
    recencia = ficha.set_index("cliente_id").recencia_dias.reindex(clientes.cliente_id)
    nuestro = {
        "clientes": int(len(clientes)),
        "transacciones_confirmadas": int(len(v)),
        "ingreso_cop": round(float(v.valor_cop.sum()), 2),
        "clientes_frios": int((recencia >= cfg.DIAS_RIESGO).sum()),
    }
    filas = []
    for k, val in nuestro.items():
        r = ref.get(k)
        ok = r is not None and abs(float(val) - float(r)) <= max(1.0, abs(float(r)) * 1e-6)
        filas.append({"indicador": k, "referencia": r, "tablero": val, "coincide": bool(ok)})
    ref_c = DATOS_CRUDOS / "referencia_clientes.csv"
    if ref_c.exists() and ren_base is not None:
        rc = pd.read_csv(ref_c, encoding="utf-8-sig")
        prox = int(((ren_base.dias_para_vencer >= 0) &
                    (ren_base.dias_para_vencer <= cfg.DIAS_AVISO_RENOVACION)).sum())
        filas.append({"indicador": "renovaciones_proximas (instalación más reciente por cliente y producto)",
                      "referencia": int(rc.renovaciones_proximas.sum()), "tablero": prox,
                      "coincide": prox == int(rc.renovaciones_proximas.sum())})
    return {"fecha_corte_referencia": ref.get("fecha_corte"), "comparacion": filas,
            "todo_coincide": all(f["coincide"] for f in filas[:4])}


def ejecutar(demo: bool = False, facturacion=None, nombre_archivo: str | None = None,
             paquete=None) -> dict:
    if demo:
        from src.generar_datos import generar
        _limpiar_extras_de_fuente()
        generar()
    elif paquete is not None:
        from src.importar_paquete_oficial import importar as importar_paquete
        importar_paquete(paquete)
    elif facturacion is not None:
        from src.importar_facturacion import importar
        _limpiar_extras_de_fuente()
        importar(facturacion, nombre_archivo=nombre_archivo)
    parametros = cfg.aplicar_parametros()
    resumen = etl.ejecutar()

    ventas = pd.read_csv(DATOS_PROCESADOS / "ventas_consolidadas.csv", parse_dates=["fecha", "mes"])
    clientes = pd.read_csv(DATOS_PROCESADOS / "clientes.csv")
    corte = (pd.Timestamp(cfg.FECHA_CORTE) if cfg.FECHA_CORTE else ventas.fecha.max()).normalize()
    productos = pd.read_csv(DATOS_PROCESADOS / "productos.csv")
    base_p = DATOS_CRUDOS / "base_instalada.csv"
    base = pd.read_csv(base_p, dtype=str) if base_p.exists() else None

    ficha = analitica.ficha_clientes(ventas, clientes, corte)
    prob, met_riesgo = modelo.entrenar_y_puntuar(ventas, corte)
    ficha = ficha.merge(prob, on="cliente_id", how="left")
    if base is not None:  # la fuente trae la base instalada real
        ren = analitica.renovaciones_desde_base(base, ventas, productos, corte)
        inicio = pd.to_datetime(base.fecha_inicio, errors="coerce")
        con_base = set(base.loc[inicio <= corte, "cliente_id"])
        ficha["base_instalada"] = ficha.cliente_id.isin(con_base)
        base.to_csv(DATOS_PROCESADOS / "base_instalada.csv", index=False)
    else:
        ren = analitica.renovaciones(ventas, corte)
        (DATOS_PROCESADOS / "base_instalada.csv").unlink(missing_ok=True)
    al = analitica.alertas(ficha, ren, corte)
    pron, met_pron = modelo.pronostico_ventas(ventas)

    ficha.to_csv(DATOS_PROCESADOS / "ficha_clientes.csv", index=False)
    ren.to_csv(DATOS_PROCESADOS / "renovaciones.csv", index=False)
    al.to_csv(DATOS_PROCESADOS / "alertas.csv", index=False)
    pron.to_csv(DATOS_PROCESADOS / "pronostico.csv", index=False)

    SALIDAS.mkdir(parents=True, exist_ok=True)
    archivo = SALIDAS / f"alertas_comerciales_{corte:%Y-%m}.xlsx"
    with pd.ExcelWriter(archivo) as xl:
        for comercial, grupo in al.groupby("comercial"):
            grupo.drop(columns="comercial").to_excel(xl, sheet_name=comercial[:31], index=False)
        ficha.to_excel(xl, sheet_name="Ficha clientes", index=False)

    metricas = {"corte": str(corte.date()), "etl": resumen, "riesgo": met_riesgo,
                "pronostico": met_pron, "parametros": parametros,
                "validacion_oficial": validar_contra_referencia(
                    ventas, ficha, clientes, ren if base is not None else None, corte),
                "segmentos": ficha.segmento.value_counts().to_dict(),
                "base_instalada": int(ficha.base_instalada.fillna(False).sum()),
                "alertas": al.tipo.value_counts().to_dict() if not al.empty else {}}
    (DATOS_PROCESADOS / "metricas.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False, default=str))
    return metricas


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true", help="generar datos sintéticos antes de correr")
    p.add_argument("--facturacion", help="ruta a una exportación plana de facturación (CSV o Excel)")
    p.add_argument("--paquete", help="carpeta o .zip del paquete oficial de recursos de prueba")
    a = p.parse_args()
    print(json.dumps(ejecutar(a.demo, a.facturacion, paquete=a.paquete), indent=2,
                     ensure_ascii=False, default=str))
