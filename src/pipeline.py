"""Corre todo el proceso mensual de punta a punta.

    python -m src.pipeline            # usa los archivos de data/raw/
    python -m src.pipeline --demo     # genera datos sintéticos primero
    python -m src.pipeline --facturacion data/ejemplos/ventas_prueba_green_2.csv
                                      # importa una exportación plana de facturación

Deja en data/processed/ lo que lee el tablero y en outputs/ un Excel de
alertas para repartir al equipo comercial.
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from src import analitica, etl, modelo
from src.config import DATOS_PROCESADOS, SALIDAS


def ejecutar(demo: bool = False, facturacion=None, nombre_archivo: str | None = None) -> dict:
    if demo:
        from src.generar_datos import generar
        generar()
    elif facturacion is not None:
        from src.importar_facturacion import importar
        importar(facturacion, nombre_archivo=nombre_archivo)
    resumen = etl.ejecutar()

    ventas = pd.read_csv(DATOS_PROCESADOS / "ventas_consolidadas.csv", parse_dates=["fecha", "mes"])
    clientes = pd.read_csv(DATOS_PROCESADOS / "clientes.csv")
    corte = ventas.fecha.max().normalize()

    ficha = analitica.ficha_clientes(ventas, clientes, corte)
    prob, met_riesgo = modelo.entrenar_y_puntuar(ventas, corte)
    ficha = ficha.merge(prob, on="cliente_id", how="left")
    ren = analitica.renovaciones(ventas, corte)
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
                "pronostico": met_pron,
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
    a = p.parse_args()
    print(json.dumps(ejecutar(a.demo, a.facturacion), indent=2, ensure_ascii=False, default=str))
