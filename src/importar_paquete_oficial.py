"""Importa el paquete oficial de recursos de prueba del reto
(Green_Services_Recursos_de_Prueba: carpeta 01_Datos + parametros_prueba.json)
y lo convierte en los archivos de entrada que espera el ETL (data/raw/).

Qué se respeta del paquete:
  - Ventas anuladas: pasan al ETL, que las rechaza con su motivo (no suman).
  - Descuento: precio neto = precio_unitario × (1 − descuento_pct / 100).
  - TRM de prueba del mismo día de cada venta (cop_por_usd).
  - Base instalada real (fecha_inicio / fecha_fin) para las renovaciones.
  - Parámetros oficiales: fecha de corte, días para cliente frío, transacciones para
    cliente frecuente, días de aviso de renovación y horizonte de predicción.
  - Cifras de referencia (05_Validacion) para comparar automáticamente.

El paquete no trae comerciales: todos los clientes quedan como «Sin asignar».

Uso:
    python -m src.importar_paquete_oficial ruta/al/paquete(.zip o carpeta)
    python -m src.pipeline --paquete data/ejemplos/paquete_oficial
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from src.config import DATOS_CRUDOS

ARCHIVOS = ["clientes.csv", "productos.csv", "ventas.csv", "compras.csv", "proveedores.csv",
            "trm_prueba.csv", "base_instalada.csv"]


class ErrorPaquete(Exception):
    """El archivo no es el paquete oficial de recursos de prueba."""


def _ubicar(raiz: Path) -> tuple[Path, Path | None, Path | None]:
    """Devuelve (carpeta con los CSV, parametros.json, carpeta de validación)."""
    candidatos = [p.parent for p in raiz.rglob("ventas.csv") if (p.parent / "base_instalada.csv").exists()]
    if not candidatos:
        raise ErrorPaquete("No se encontró una carpeta con ventas.csv y base_instalada.csv "
                           "(01_Datos del paquete oficial).")
    datos = candidatos[0]
    params = next(iter(raiz.rglob("parametros_prueba.json")), None) or next(iter(raiz.rglob("parametros.json")), None)
    valid = next((p.parent for p in raiz.rglob("Referencia_resumen_prueba.json")), None)
    return datos, params, valid


def _leer(carpeta: Path, nombre: str) -> pd.DataFrame:
    return pd.read_csv(carpeta / nombre, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def importar(fuente, destino: Path = DATOS_CRUDOS) -> dict:
    """`fuente`: carpeta del paquete, ruta a un .zip o bytes de un .zip."""
    tmp = None
    if isinstance(fuente, (bytes, bytearray)) or str(fuente).lower().endswith(".zip"):
        tmp = Path(tempfile.mkdtemp())
        z = zipfile.ZipFile(io.BytesIO(fuente) if isinstance(fuente, (bytes, bytearray)) else fuente)
        for m in z.infolist():  # sin rutas absolutas ni «..»
            if m.is_dir() or m.filename.startswith("/") or ".." in Path(m.filename).parts:
                continue
            z.extract(m, tmp)
        raiz = tmp
    else:
        raiz = Path(fuente)
    try:
        datos, params, valid = _ubicar(raiz)
        faltan = [a for a in ARCHIVOS if not (datos / a).exists()]
        if faltan:
            raise ErrorPaquete("Al paquete le faltan: " + ", ".join(faltan))
        t = {a.removesuffix(".csv"): _leer(datos, a) for a in ARCHIVOS}

        clientes = pd.DataFrame({
            "cliente_id": t["clientes"].cliente_id,
            "nit": t["clientes"].cliente_id,           # el paquete no trae NIT
            "nombre": t["clientes"].nombre_prueba,
            "sector": t["clientes"].sector_prueba,
            "ciudad": t["clientes"].ciudad_prueba,
            "tamano": "",
            "comercial_id": "SA", "comercial": "Sin asignar",
            "contacto_nombre": "",
            "contacto_cargo": "Canal preferido: " + t["clientes"].canal_preferido_prueba,
            "contacto_email": "", "contacto_telefono": "",
            "fecha_alta": t["clientes"].fecha_alta,
            "fuente": "Paquete oficial de recursos de prueba (clientes.csv)",
            "dato_ficticio": True,
        })
        comerciales = pd.DataFrame({"comercial_id": ["SA"], "nombre": ["Sin asignar"],
                                    "sede": [""], "dato_ficticio": [True]})
        pr = t["productos"]
        productos = pd.DataFrame({
            "producto_id": pr.producto_id, "nombre": pr.nombre_prueba, "categoria": pr.familia_prueba,
            "tipo": pr.tipo_prueba, "precio_lista": pr.precio_lista, "moneda": pr.moneda_lista,
            "costo_referencia": pr.costo_referencia, "meses_renovacion": pr.vigencia_meses,
            "fuente": "Paquete oficial de recursos de prueba (productos.csv)", "dato_ficticio": True,
        })
        v = t["ventas"]
        desc = pd.to_numeric(v.descuento_pct, errors="coerce").fillna(0)
        precio = pd.to_numeric(v.precio_unitario, errors="coerce") * (1 - desc / 100)
        ventas = pd.DataFrame({
            "registro_id": v.venta_id, "fecha": v.fecha, "factura": v.venta_id, "linea": 1,
            "cliente_id": v.cliente_id, "comercial_id": "SA", "producto_id": v.producto_id,
            "cantidad": v.cantidad, "precio_unitario": precio, "descuento_pct": desc,
            "precio_lista_venta": v.precio_unitario, "moneda": v.moneda, "estado": v.estado,
            "motivo": "Venta", "fuente": "Paquete oficial de recursos de prueba (ventas.csv)",
            "dato_ficticio": True,
        })
        prov = dict(zip(t["proveedores"].proveedor_id, t["proveedores"].nombre_prueba))
        c = t["compras"]
        compras = pd.DataFrame({
            "registro_id": c.compra_id, "fecha": c.fecha, "orden": c.compra_id,
            "proveedor_id": c.proveedor_id, "proveedor": c.proveedor_id.map(prov).fillna(c.proveedor_id),
            "producto_id": c.producto_id, "cantidad": c.cantidad, "costo_unitario": c.costo_unitario,
            "moneda": c.moneda, "fuente": "Paquete oficial de recursos de prueba (compras.csv)",
            "dato_ficticio": True,
        })
        tr = t["trm_prueba"]
        trm = pd.DataFrame({"registro_id": "TRM-" + tr.fecha.str.replace("-", ""), "fecha": tr.fecha,
                            "valor": tr.cop_por_usd, "fuente": tr.origen, "dato_ficticio": True})

        destino.mkdir(parents=True, exist_ok=True)
        for viejo in list(destino.glob("*.csv")) + list(destino.glob("*.json")):
            viejo.unlink()
        for nombre, tabla in {"clientes": clientes, "comerciales": comerciales, "productos": productos,
                              "ventas": ventas, "compras": compras, "trm": trm,
                              "base_instalada": t["base_instalada"]}.items():
            tabla.to_csv(destino / f"{nombre}.csv", index=False)
        if params:
            shutil.copy(params, destino / "parametros.json")
        if valid:
            shutil.copy(valid / "Referencia_resumen_prueba.json", destino / "referencia_oficial.json")
            if (valid / "Referencia_resumen_clientes.csv").exists():
                shutil.copy(valid / "Referencia_resumen_clientes.csv", destino / "referencia_clientes.csv")
        return {"clientes": len(clientes), "productos": len(productos), "ventas": len(ventas),
                "compras": len(compras), "instalaciones": len(t["base_instalada"]),
                "parametros": bool(params), "referencia": bool(valid)}
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("fuente")
    print(importar(p.parse_args().fuente))
