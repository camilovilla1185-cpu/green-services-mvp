"""Ingesta, validación y consolidación con trazabilidad.

Reemplaza el trabajo manual de bajar reportes de varias plataformas y
cruzarlos en Excel. Lee los archivos de data/raw/ (CSV o Excel), valida que
tengan las columnas mínimas, separa los registros con problemas, convierte
todo a pesos con la TRM del día de cada operación y deja un único modelo de
datos en data/processed/.

Trazabilidad que agrega a cada registro:
  lote_id        identificador de esta corrida (una por cierre mensual)
  archivo_origen nombre del archivo del que salió la fila
  fila_origen    número de fila en ese archivo (la 2 es la primera después del encabezado)
  hash_registro  huella del contenido original de la fila; si alguien cambia el
                 archivo fuente, la huella cambia y se nota

Además deja:
  data/processed/bitacora_cargas.csv  una línea por archivo y por lote (se acumula)
  data/processed/rechazos.csv         registros que no entraron y por qué

Uso:  python -m src.etl
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config import DATOS_CRUDOS, DATOS_PROCESADOS, ESQUEMA


class ErrorDeDatos(Exception):
    """Se lanza cuando un archivo no cumple el esquema mínimo."""


def _hash_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]


def _hash_filas(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str, index=df.index)
    # astype(object) + fillna: con pandas 3 los vacíos siguen siendo NaN tras astype(str)
    texto = df.astype(object).fillna("").astype(str).agg("|".join, axis=1)
    return texto.map(lambda t: hashlib.sha1(t.encode()).hexdigest()[:12])


def _leer(nombre: str, carpeta: Path, lote: str, bitacora: list,
          opcional: bool = False) -> pd.DataFrame:
    """Busca nombre.csv o nombre.xlsx, lo carga y le pone su sello de origen.
    Si el archivo es opcional y no existe, devuelve una tabla vacía con el esquema."""
    for ext in (".csv", ".xlsx", ".xls"):
        ruta = carpeta / f"{nombre}{ext}"
        if not ruta.exists():
            continue
        df = pd.read_csv(ruta) if ext == ".csv" else pd.read_excel(ruta)
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_", regex=False)
        faltan = set(ESQUEMA[nombre]) - set(df.columns)
        if faltan:
            raise ErrorDeDatos(f"{ruta.name}: faltan columnas {sorted(faltan)}")
        df["hash_registro"] = _hash_filas(df)
        df["archivo_origen"] = ruta.name
        df["fila_origen"] = range(2, len(df) + 2)
        df["lote_id"] = lote
        if "fecha" in df.columns:
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        bitacora.append({"lote_id": lote, "archivo": ruta.name,
                         "hash_archivo": _hash_archivo(ruta), "filas_leidas": len(df)})
        return df
    if opcional:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in ESQUEMA[nombre]}).assign(
            fecha=pd.Series(dtype="datetime64[ns]"), cantidad=pd.Series(dtype=float),
            archivo_origen=pd.Series(dtype=str), fila_origen=pd.Series(dtype=int),
            lote_id=pd.Series(dtype=str), registro_id=pd.Series(dtype=str))
    raise ErrorDeDatos(f"No se encontró {nombre}.csv ni {nombre}.xlsx en {carpeta}")


def _separar(df: pd.DataFrame, reglas: dict, rechazos: list) -> pd.DataFrame:
    """Aplica reglas de calidad; lo que no pasa va a rechazos con el motivo."""
    ok = pd.Series(True, index=df.index)
    for motivo, mascara_mala in reglas.items():
        malos = mascara_mala & ok
        for r in df[malos].itertuples():
            rechazos.append({"lote_id": r.lote_id, "archivo_origen": r.archivo_origen,
                             "fila_origen": r.fila_origen,
                             "registro_id": getattr(r, "registro_id", ""), "motivo": motivo})
        ok &= ~mascara_mala
    return df[ok].copy()


def trm_desde_datos_abiertos(desde: str, hasta: str) -> pd.DataFrame:
    """Opcional: descarga la TRM oficial del portal datos.gov.co (Superfinanciera).

    Requiere internet. Si falla, el pipeline usa data/raw/trm.csv.
    """
    import requests
    url = "https://www.datos.gov.co/resource/32sa-8pi3.json"
    params = {"$where": f"vigenciadesde between '{desde}T00:00:00' and '{hasta}T00:00:00'",
              "$limit": 5000}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json()).rename(columns={"vigenciadesde": "fecha"})[["fecha", "valor"]]
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.normalize()
    df["valor"] = df["valor"].astype(float)
    df["registro_id"] = "TRM-" + df["fecha"].dt.strftime("%Y%m%d")
    df["fuente"] = "datos.gov.co 32sa-8pi3"
    return df


def _trm_diaria(trm: pd.DataFrame, desde, hasta) -> pd.DataFrame:
    """Completa fines de semana y festivos con la última TRM publicada y deja
    anotado de qué día salió el valor (trm_fecha_publicada)."""
    t = (trm.dropna(subset=["fecha", "valor"]).drop_duplicates("fecha").sort_values("fecha")
         .assign(trm_fecha_publicada=lambda d: d.fecha)
         .set_index("fecha")[["valor", "trm_fecha_publicada", "registro_id"]])
    dias = pd.date_range(min(desde, t.index.min()), max(hasta, t.index.max()), freq="D")
    t = t.reindex(dias).ffill().bfill().rename_axis("fecha").reset_index()
    return t.rename(columns={"registro_id": "trm_registro_id"})


def _a_pesos(df: pd.DataFrame, columna_valor: str, trm: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(trm.rename(columns={"valor": "trm"}), on="fecha", how="left")
    df["moneda"] = df["moneda"].str.upper().str.strip()
    es_usd = df["moneda"].eq("USD")
    df["valor_original"] = df["cantidad"] * df[columna_valor]
    df["valor_cop"] = df["valor_original"].where(~es_usd, df["valor_original"] * df["trm"])
    # La TRM solo se anota en operaciones en dólares
    for col in ("trm", "trm_fecha_publicada", "trm_registro_id"):
        df[col] = df[col].where(es_usd)
    return df


def ejecutar(carpeta_entrada: Path = DATOS_CRUDOS,
             carpeta_salida: Path = DATOS_PROCESADOS) -> dict:
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    lote = "L" + datetime.now().strftime("%Y%m%d-%H%M%S")
    bitacora, rechazos = [], []

    clientes = _leer("clientes", carpeta_entrada, lote, bitacora)
    productos = _leer("productos", carpeta_entrada, lote, bitacora)
    ventas = _leer("ventas", carpeta_entrada, lote, bitacora)
    compras = _leer("compras", carpeta_entrada, lote, bitacora, opcional=True)
    trm = _leer("trm", carpeta_entrada, lote, bitacora)

    ventas = _separar(ventas, {
        "fecha vacía o inválida": ventas.fecha.isna(),
        "cliente no existe en el maestro": ~ventas.cliente_id.isin(clientes.cliente_id),
        "producto no existe en el maestro": ~ventas.producto_id.isin(productos.producto_id),
        "valor vacío": ventas.precio_unitario.isna() | ventas.cantidad.isna(),
        "cantidad o precio no positivos (nota crédito o error)": (ventas.cantidad <= 0) | (ventas.precio_unitario <= 0),
        "moneda distinta de COP o USD": ~ventas.moneda.str.upper().isin(["COP", "USD"]),
        "línea de factura duplicada": ventas.duplicated(["factura", "linea"]
                                                         if "linea" in ventas else ["factura", "producto_id"]),
    }, rechazos)
    compras = _separar(compras, {"fecha vacía o inválida": compras.fecha.isna()}, rechazos)

    fechas = pd.concat([ventas.fecha, compras.fecha]).dropna()
    trm_d = _trm_diaria(trm, fechas.min(), fechas.max())
    ventas = _a_pesos(ventas, "precio_unitario", trm_d)
    compras = _a_pesos(compras, "costo_unitario", trm_d)

    # Costo y margen: si la orden de compra está ligada a la línea de factura se
    # usa ese costo exacto y se guarda el número de orden; si no, costo promedio.
    if {"factura_relacionada", "linea_relacionada"} <= set(compras.columns):
        costo = (compras.groupby(["factura_relacionada", "linea_relacionada"])
                 .agg(costo_cop=("valor_cop", lambda x: x.sum(min_count=1)), orden_compra=("orden", "first"),
                      proveedor=("proveedor", "first"))
                 .reset_index().rename(columns={"factura_relacionada": "factura",
                                                "linea_relacionada": "linea"}))
        ventas = ventas.merge(costo, on=["factura", "linea"], how="left")
        ventas["metodo_costo"] = ventas.orden_compra.notna().map(
            {True: "orden de compra ligada", False: "sin costo"})
    else:
        unit = (compras.assign(u=compras.valor_cop / compras.cantidad)
                .groupby("producto_id")["u"].mean().rename("costo_unit"))
        ventas = ventas.merge(unit, on="producto_id", how="left")
        ventas["costo_cop"] = ventas["costo_unit"] * ventas["cantidad"]
        ventas["orden_compra"] = pd.NA
        ventas["proveedor"] = pd.NA
        ventas["metodo_costo"] = ventas.costo_cop.notna().map(
            {True: "costo promedio del producto", False: "sin costo (no hay datos de compras)"})
        ventas = ventas.drop(columns="costo_unit")
    ventas["margen_cop"] = ventas["valor_cop"] - ventas["costo_cop"]

    cols_cliente = [c for c in ["cliente_id", "nit", "nombre", "sector", "ciudad", "tamano",
                                "comercial", "contacto_nombre", "contacto_cargo",
                                "contacto_email", "contacto_telefono"] if c in clientes]
    ventas = (ventas
              .merge(productos[["producto_id", "nombre", "categoria", "meses_renovacion"]]
                     .rename(columns={"nombre": "producto"}), on="producto_id", how="left")
              .merge(clientes[cols_cliente], on="cliente_id", how="left"))
    ventas["mes"] = ventas["fecha"].dt.to_period("M").dt.to_timestamp()

    ventas.to_csv(carpeta_salida / "ventas_consolidadas.csv", index=False)
    compras.to_csv(carpeta_salida / "compras_consolidadas.csv", index=False)
    trm_d.to_csv(carpeta_salida / "trm_diaria.csv", index=False)
    clientes.to_csv(carpeta_salida / "clientes.csv", index=False)
    productos.to_csv(carpeta_salida / "productos.csv", index=False)

    # Bitácora acumulada y rechazos del lote
    rech = pd.DataFrame(rechazos, columns=["lote_id", "archivo_origen", "fila_origen",
                                           "registro_id", "motivo"])
    rech.to_csv(carpeta_salida / "rechazos.csv", index=False)
    bit = pd.DataFrame(bitacora)
    bit["filas_rechazadas"] = bit.archivo.map(rech.archivo_origen.value_counts()).fillna(0).astype(int)
    bit["filas_cargadas"] = bit.filas_leidas - bit.filas_rechazadas
    bit["fecha_carga"] = datetime.now().isoformat(timespec="seconds")
    ruta_bit = carpeta_salida / "bitacora_cargas.csv"
    if ruta_bit.exists():
        bit = pd.concat([pd.read_csv(ruta_bit), bit], ignore_index=True)
    bit.to_csv(ruta_bit, index=False)

    resumen = {"lote_id": lote, "lineas_venta": len(ventas),
               "facturas": int(ventas["factura"].nunique()),
               "clientes": int(clientes["cliente_id"].nunique()),
               "desde": str(ventas["fecha"].min().date()),
               "hasta": str(ventas["fecha"].max().date()),
               "ventas_total_cop": float(ventas["valor_cop"].sum()),
               "participacion_usd": float(ventas.loc[ventas.moneda == "USD", "valor_cop"].sum()
                                          / ventas["valor_cop"].sum()),
               "lineas_con_costo": float(ventas.costo_cop.notna().mean()),
               "lineas_con_costo_ligado": float(ventas.orden_compra.notna().mean()),
               "rechazos": rech.motivo.value_counts().to_dict()}
    (carpeta_salida / "resumen_etl.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False))
    return resumen


if __name__ == "__main__":
    print(json.dumps(ejecutar(), indent=2, ensure_ascii=False))
