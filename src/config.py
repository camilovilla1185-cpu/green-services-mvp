"""Configuración central del MVP.

Todo lo que el negocio puede querer ajustar sin tocar la lógica está aquí:
rutas, umbrales de segmentación y horizonte de predicción.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS_CRUDOS = RAIZ / "data" / "raw"          # aquí se dejan los Excel/CSV exportados
DATOS_PROCESADOS = RAIZ / "data" / "processed"  # salidas del pipeline (las lee el tablero)
SALIDAS = RAIZ / "outputs"                      # reportes para el equipo comercial

# --- Segmentación (días desde la última compra) ---
DIAS_ACTIVO = 90        # compró en los últimos 90 días -> activo
DIAS_RIESGO = 180       # entre 90 y 180 días sin comprar -> en riesgo
# más de 180 días sin comprar -> frío

MIN_COMPRAS_FRECUENTE = 4   # meses distintos con compra en los últimos 12 meses
DIAS_CLIENTE_NUEVO = 120    # primera compra hace menos de esto -> nuevo

# --- Base instalada ---
# Un producto deja algo "instalado" en el cliente (y genera renovaciones, soporte o
# reposición) si tiene meses_renovacion > 0 en el maestro de productos. Si además se
# quiere marcar líneas completas como instalables, se agregan aquí.
CATEGORIAS_INSTALABLES: set[str] = set()
# Líneas de negocio oficiales de Green (greencss.com). Se usan como categoría.
LINEAS_NEGOCIO = ["Cloud & Data Center", "Cybersecurity", "End User Solutions", "FLEX GPT",
                  "Professional Services"]
# Mientras no haya un catálogo confiable de Green, los productos se muestran como
# «Producto A», «Producto B»… dentro de su línea de negocio. Con datos reales: False.
PRODUCTOS_GENERICOS = True
DIAS_AVISO_RENOVACION = 60  # alertar renovaciones que vencen en los próximos N días

# --- Modelo de riesgo ---
HORIZONTE_DIAS = 90     # ¿volverá a comprar en los próximos 90 días?
SEMILLA = 42

# Regla de cliente frecuente: por defecto, meses distintos con compra en 12 meses
# (MIN_COMPRAS_FRECUENTE). Si la fuente define otra regla (p. ej. el paquete oficial
# del reto: 8 transacciones confirmadas), se usa MIN_TRANSACCIONES_FRECUENTE.
MIN_TRANSACCIONES_FRECUENTE: int | None = None
FECHA_CORTE = None  # None = la fecha de la última venta
MONEDAS_ADMITIDAS = {"COP", "USD"}

# --- Parámetros de la fuente de datos ---------------------------------------
# Si en data/raw/ hay un parametros.json (como parametros_prueba.json del paquete
# oficial), sus valores reemplazan a los de arriba. Se aplican con aplicar_parametros().
ARCHIVO_PARAMETROS = DATOS_CRUDOS / "parametros.json"
_DEFECTO = {k: globals()[k] for k in ("DIAS_ACTIVO", "DIAS_RIESGO", "MIN_COMPRAS_FRECUENTE",
                                       "DIAS_CLIENTE_NUEVO", "DIAS_AVISO_RENOVACION",
                                       "HORIZONTE_DIAS", "MIN_TRANSACCIONES_FRECUENTE",
                                       "FECHA_CORTE")}


def aplicar_parametros() -> dict:
    """Restablece los valores por defecto y aplica los de data/raw/parametros.json, si existe.
    Devuelve los parámetros en uso (para mostrarlos en el tablero)."""
    import json
    g = globals()
    g.update(_DEFECTO)
    fuente = "valores por defecto del MVP"
    if ARCHIVO_PARAMETROS.exists():
        p = json.loads(ARCHIVO_PARAMETROS.read_text(encoding="utf-8-sig"))
        if "frio_dias_sin_compra" in p:
            g["DIAS_RIESGO"] = int(p["frio_dias_sin_compra"])
            g["DIAS_ACTIVO"] = max(30, int(p["frio_dias_sin_compra"]) * 2 // 3)
            g["DIAS_CLIENTE_NUEVO"] = min(_DEFECTO["DIAS_CLIENTE_NUEVO"], int(p["frio_dias_sin_compra"]))
        if "frecuente_min_transacciones" in p:
            g["MIN_TRANSACCIONES_FRECUENTE"] = int(p["frecuente_min_transacciones"])
        if "renovacion_dias" in p:
            g["DIAS_AVISO_RENOVACION"] = int(p["renovacion_dias"])
        if "horizonte_prediccion_dias" in p:
            g["HORIZONTE_DIAS"] = int(p["horizonte_prediccion_dias"])
        if "fecha_corte" in p:
            g["FECHA_CORTE"] = p["fecha_corte"]
        fuente = "parametros.json de la fuente de datos"
    return {"fuente": fuente, **{k: g[k] for k in _DEFECTO}}


# Columnas mínimas que el ETL espera en cada archivo de entrada.
ESQUEMA = {
    "clientes": ["cliente_id", "nit", "nombre", "sector", "ciudad", "comercial"],
    "productos": ["producto_id", "nombre", "categoria", "meses_renovacion"],
    "ventas": ["fecha", "factura", "cliente_id", "producto_id", "cantidad",
               "precio_unitario", "moneda"],
    "compras": ["fecha", "orden", "proveedor", "producto_id", "cantidad",
                "costo_unitario", "moneda"],
    "trm": ["fecha", "valor"],
}
