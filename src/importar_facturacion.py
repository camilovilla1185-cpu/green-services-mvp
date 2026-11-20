"""Importa una exportación plana de facturación (una fila por línea de factura)
y la convierte en los archivos de entrada que espera el ETL (data/raw/).

Formato esperado (como ventas_prueba_green_2.csv; separador ; o , y valores
con punto de miles):

    Fecha Factura; No. Factura; NIT; Razón Social; Sector; Ciudad; Vendedor;
    Línea de negocio; Descripción; Valor Total

Qué hace:
  - clientes.csv     un registro por NIT (comercial = vendedor con más facturas)
  - comerciales.csv  un registro por vendedor
  - productos.csv    un registro por descripción; la categoría es la línea de
                     negocio y los meses de renovación salen del catálogo
                     editable data/catalogo_facturacion.csv
  - ventas.csv       una fila por fila del archivo original, EN EL MISMO ORDEN,
                     para que «fila_origen» coincida con la fila de la exportación
  - compras.csv      vacío (la exportación no trae costos; el margen queda «sin costo»)
  - trm.csv          TRM oficial de datos.gov.co si hay internet; si no, se
                     reutiliza la existente o se deja una serie de respaldo marcada

Las filas con problemas (NIT vacío, fecha inválida, valor negativo como una
nota crédito) NO se borran aquí: pasan al ETL, que las manda a rechazos con su
motivo. Así la trazabilidad queda completa.

Uso:
    python -m src.importar_facturacion ruta/al/archivo.csv
    python -m src.pipeline --facturacion ruta/al/archivo.csv   (importa y procesa)
"""
from __future__ import annotations

import argparse
import hashlib
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import DATOS_CRUDOS, PRODUCTOS_GENERICOS, RAIZ
from src.productos import generizar

CATALOGO = RAIZ / "data" / "catalogo_facturacion.csv"

# Nombres de columna aceptados (se comparan sin tildes, mayúsculas ni signos)
ALIAS = {
    "fecha": ["fecha factura", "fecha", "fecha de factura", "fecha emision"],
    "factura": ["no factura", "numero factura", "factura", "no. factura", "nro factura"],
    "nit": ["nit", "nit cliente", "identificacion"],
    "nombre": ["razon social", "cliente", "nombre cliente", "nombre"],
    "sector": ["sector"],
    "ciudad": ["ciudad"],
    "vendedor": ["vendedor", "comercial", "asesor"],
    "linea_negocio": ["linea de negocio", "linea negocio", "linea", "categoria"],
    "descripcion": ["descripcion", "producto", "detalle"],
    "valor": ["valor total", "valor", "total", "valor factura"],
}
OBLIGATORIAS = ["fecha", "factura", "nit", "nombre", "descripcion", "valor"]


class ErrorFormato(Exception):
    """El archivo no tiene el formato de exportación de facturación."""


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", t.lower().replace(".", " ")).strip()


def _mapear_columnas(columnas) -> dict:
    norm = {_normalizar(c): c for c in columnas}
    mapa = {}
    for destino, alias in ALIAS.items():
        for a in alias:
            if _normalizar(a) in norm:
                mapa[norm[_normalizar(a)]] = destino
                break
    faltan = [c for c in OBLIGATORIAS if c not in mapa.values()]
    if faltan:
        raise ErrorFormato(
            "El archivo no parece una exportación de facturación. Faltan columnas para: "
            + ", ".join(faltan) + f". Columnas encontradas: {', '.join(map(str, columnas))}")
    return mapa


def _a_numero(serie: pd.Series) -> pd.Series:
    """'12.479.000' -> 12479000 ; '-1.234,5' -> -1234.5 ; '12479000.0' -> 12479000"""
    s = serie.astype(str).str.strip().str.replace(r"[$\s]", "", regex=True)
    con_coma_decimal = s.str.contains(r",\d{1,2}$")
    s = s.where(~con_coma_decimal, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    miles_con_punto = s.str.match(r"^-?\d{1,3}(\.\d{3})+$")
    s = s.where(~miles_con_punto, s.str.replace(".", "", regex=False))
    return pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce")


def leer_exportacion(fuente) -> pd.DataFrame:
    """Lee CSV (separador ; o ,) o Excel. `fuente` puede ser ruta o bytes."""
    import io
    if isinstance(fuente, io.BytesIO) or (isinstance(fuente, (str, Path))
                                          and str(fuente).lower().endswith((".xlsx", ".xls"))):
        df = pd.read_excel(fuente, dtype=str).fillna("")
    else:
        datos = Path(fuente).read_bytes() if isinstance(fuente, (str, Path)) else fuente
        texto = datos.decode("utf-8-sig", errors="replace")
        sep = ";" if texto.split("\n", 1)[0].count(";") >= texto.split("\n", 1)[0].count(",") else ","
        df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
    return df.rename(columns=_mapear_columnas(df.columns))


def _id_corto(texto: str, prefijo: str) -> str:
    return prefijo + hashlib.sha1(texto.encode()).hexdigest()[:6].upper()


def _catalogo() -> pd.DataFrame:
    if CATALOGO.exists():
        return pd.read_csv(CATALOGO)
    return pd.DataFrame(columns=["descripcion", "meses_renovacion"])


def _trm(desde: pd.Timestamp, hasta: pd.Timestamp, destino: Path) -> pd.DataFrame:
    from src.etl import trm_desde_datos_abiertos
    try:
        trm = trm_desde_datos_abiertos(f"{desde:%Y-%m-%d}", f"{hasta:%Y-%m-%d}")
        if len(trm) > 30:
            trm["dato_ficticio"] = False
            return trm
    except Exception:
        pass
    previa = destino / "trm.csv"
    if previa.exists():
        t = pd.read_csv(previa, parse_dates=["fecha"])
        if t.fecha.min() <= desde and t.fecha.max() >= hasta - pd.Timedelta(days=10):
            return t
    # Respaldo: serie suave y marcada como simulada (las ventas de este archivo están en COP,
    # así que la TRM solo se usa como referencia en el tablero)
    fechas = pd.date_range(desde, hasta, freq="D")
    rng = np.random.default_rng(42)
    valores = np.empty(len(fechas))
    valores[0] = 4000.0
    for i in range(1, len(fechas)):  # vuelve poco a poco hacia 4.000 (no se dispara ni se pega)
        valores[i] = valores[i - 1] + 0.02 * (4000 - valores[i - 1]) + rng.normal(0, 15)
    return pd.DataFrame({"registro_id": "TRM-" + fechas.strftime("%Y%m%d"), "fecha": fechas,
                         "valor": valores.round(2),
                         "fuente": "Respaldo simulado (sin conexión)", "dato_ficticio": True})


def importar(fuente, destino: Path = DATOS_CRUDOS, nombre_archivo: str | None = None,
             dato_ficticio: bool = True) -> dict:
    """Convierte la exportación en los 6 archivos de data/raw/. Devuelve un resumen."""
    df = leer_exportacion(fuente)
    nombre_archivo = nombre_archivo or (Path(fuente).name if isinstance(fuente, (str, Path)) else "exportacion.csv")
    destino.mkdir(parents=True, exist_ok=True)

    for col in ["sector", "ciudad", "vendedor", "linea_negocio"]:
        if col not in df:
            df[col] = "Sin dato"
    df = df.apply(lambda s: s.str.strip() if s.dtype == object else s)
    df["fecha_dt"] = pd.to_datetime(df["fecha"], format="%d/%m/%Y", errors="coerce").fillna(
        pd.to_datetime(df["fecha"], errors="coerce", dayfirst=True, format="mixed"))
    df["valor_num"] = _a_numero(df["valor"])
    df["nit"] = df["nit"].replace("", np.nan)

    # --- Comerciales
    vend = sorted(v for v in df["vendedor"].replace("", np.nan).dropna().unique())
    comerciales = pd.DataFrame({"comercial_id": [f"V{i:02d}" for i in range(1, len(vend) + 1)],
                                "nombre": vend, "sede": "Sin dato", "dato_ficticio": dato_ficticio})
    id_vend = dict(zip(comerciales.nombre, comerciales.comercial_id))

    # --- Clientes (un registro por NIT)
    validos = df.dropna(subset=["nit"])
    ultimo = validos.sort_values("fecha_dt").groupby("nit").last()
    vendedor_principal = (validos.groupby(["nit", "vendedor"]).size().reset_index(name="n")
                          .sort_values("n").groupby("nit").vendedor.last())
    clientes = pd.DataFrame({
        "cliente_id": [_id_corto(n, "C") for n in ultimo.index],
        "nit": ultimo.index,
        "nombre": ultimo["nombre"].values,
        "sector": ultimo["sector"].values,
        "ciudad": ultimo["ciudad"].values,
        "tamano": "",
        "comercial": vendedor_principal.reindex(ultimo.index).values,
    })
    clientes["comercial_id"] = clientes.comercial.map(id_vend)
    for c in ["contacto_nombre", "contacto_cargo", "contacto_email", "contacto_telefono"]:
        clientes[c] = ""  # la exportación de facturación no trae contactos (vienen del CRM)
    clientes["fuente"] = f"Exportación de facturación ({nombre_archivo})"
    clientes["dato_ficticio"] = dato_ficticio
    id_cliente = dict(zip(clientes.nit, clientes.cliente_id))

    # --- Productos (un registro por descripción)
    cat = _catalogo()
    prods = (df.groupby("descripcion")["linea_negocio"]
             .agg(lambda s: s.mode().iat[0] if len(s.mode()) else "Sin dato").reset_index())
    prods = prods.merge(cat[["descripcion", "meses_renovacion"]], on="descripcion", how="left")
    sin_catalogo = prods.meses_renovacion.isna().sum()
    prods["meses_renovacion"] = prods.meses_renovacion.fillna(0).astype(int)
    productos = pd.DataFrame({
        "producto_id": [_id_corto(d, "P") for d in prods.descripcion],
        "nombre": prods.descripcion, "categoria": prods.linea_negocio,
        "precio_lista": np.nan, "moneda": "COP", "meses_renovacion": prods.meses_renovacion,
        "fuente": "Derivado de la exportación + catálogo editable", "dato_ficticio": dato_ficticio,
    })
    id_prod = dict(zip(productos.nombre, productos.producto_id))  # se mapea con la descripción original
    if PRODUCTOS_GENERICOS:
        productos = generizar(productos)

    # --- Ventas: misma cantidad y orden de filas que el archivo original
    linea = df.groupby("factura").cumcount() + 1
    ventas = pd.DataFrame({
        "registro_id": "VEN-" + df["factura"].astype(str) + "-" + linea.astype(str),
        "fecha": df["fecha_dt"].dt.strftime("%Y-%m-%d"),
        "factura": df["factura"], "linea": linea,
        "cliente_id": df["nit"].map(id_cliente).fillna("SIN-NIT"),
        "comercial_id": df["vendedor"].map(id_vend),
        "producto_id": df["descripcion"].map(id_prod),
        "cantidad": 1,
        "precio_unitario": df["valor_num"],
        "moneda": "COP",
        "motivo": np.where(df["valor_num"] < 0, "Nota crédito / ajuste", "Venta"),
        "fuente": f"Exportación de facturación ({nombre_archivo})",
        "dato_ficticio": dato_ficticio,
    })

    compras = pd.DataFrame(columns=["registro_id", "fecha", "orden", "proveedor_id", "proveedor",
                                    "producto_id", "cantidad", "costo_unitario", "moneda",
                                    "fuente", "dato_ficticio"])
    desde = df.fecha_dt.min() - pd.Timedelta(days=7)
    hasta = df.fecha_dt.max()
    trm = _trm(desde, hasta, destino)

    # Se reemplazan los archivos de entrada (los demás, como _verdad_sintetica, se quitan)
    for viejo in destino.glob("*.csv"):
        viejo.unlink()
    for nombre, tabla in {"clientes": clientes, "comerciales": comerciales, "productos": productos,
                          "ventas": ventas, "compras": compras, "trm": trm}.items():
        tabla.to_csv(destino / f"{nombre}.csv", index=False)

    return {"archivo": nombre_archivo, "filas": len(df), "clientes": len(clientes),
            "comerciales": len(comerciales), "productos": len(productos),
            "productos_sin_catalogo": int(sin_catalogo),
            "trm": str(trm["fuente"].iloc[0]) if "fuente" in trm else "datos.gov.co"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("archivo")
    print(importar(p.parse_args().archivo))
