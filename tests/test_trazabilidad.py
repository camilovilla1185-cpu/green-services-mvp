"""Pruebas de trazabilidad y consistencia.

Correr después del pipeline:   python -m pytest tests -q
(o sin pytest:                 python tests/test_trazabilidad.py)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import DATOS_CRUDOS, DATOS_PROCESADOS as P  # noqa: E402

V = pd.read_csv(P / "ventas_consolidadas.csv")
A = pd.read_csv(P / "alertas.csv")
C = pd.read_csv(P / "compras_consolidadas.csv")
F = pd.read_csv(P / "ficha_clientes.csv")


def test_toda_linea_tiene_origen():
    for col in ["registro_id", "archivo_origen", "fila_origen", "hash_registro", "lote_id"]:
        assert V[col].notna().all(), f"hay ventas sin {col}"


def test_fila_origen_apunta_a_la_fila_correcta():
    crudo = pd.read_csv(DATOS_CRUDOS / "ventas.csv")
    muestra = V.sample(50, random_state=1)
    for r in muestra.itertuples():
        original = crudo.iloc[r.fila_origen - 2]
        assert original.registro_id == r.registro_id


def test_toda_alerta_tiene_factura_que_existe():
    facturas = set(V.factura)
    base_p = P / "base_instalada.csv"
    instalaciones = set(pd.read_csv(base_p).instalacion_id) if base_p.exists() else set()
    for ev in A.evidencia:
        if ev.startswith("Base instalada: "):   # la fuente trae la base instalada real
            num = ev.split(": ")[1].split(" ")[0]
            assert num in instalaciones, f"la alerta cita la instalación {num}, que no existe"
        else:
            num = ev.split("ctura ")[1].split(" ")[0]
            assert num in facturas, f"la alerta cita {num}, que no existe"


def test_dolares_llevan_trm_y_pesos_no():
    usd = V[V.moneda == "USD"]
    assert usd.trm.notna().all() and usd.trm_registro_id.notna().all()
    assert V[V.moneda == "COP"].trm.isna().all()
    assert ((usd.valor_cop - usd.valor_original * usd.trm).abs() < 1).all()


def test_costo_ligado_a_orden_de_compra():
    if not V.metodo_costo.astype(str).str.contains("orden de compra").any():
        # La fuente no liga compras a facturas (paquete oficial: costo promedio) o no trae
        # compras (exportación de facturación: sin costo). Lo que haya debe ser positivo.
        con_costo = V.costo_cop.dropna()
        assert (con_costo > 0).all()
        assert V.loc[V.costo_cop.isna(), "metodo_costo"].astype(str).str.startswith("sin costo").all()
        return
    assert V.orden_compra.notna().all()
    assert V.orden_compra.isin(C.orden).all()
    assert (V.costo_cop > 0).all()


def test_totales_cuadran():
    assert abs(F.ventas_historicas_cop.sum() - V.valor_cop.sum()) < 1


def test_datos_marcados_como_ficticios():
    crudo = pd.read_csv(DATOS_CRUDOS / "clientes.csv")
    if "dato_ficticio" in crudo:
        assert crudo.dato_ficticio.all()
        correos = crudo.contacto_email.dropna().astype(str)
        correos = correos[correos.str.strip() != ""]
        assert correos.str.endswith(".example").all()  # nunca correos que parezcan reales


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok ", nombre)
