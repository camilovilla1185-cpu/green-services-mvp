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
# Categorías de producto que dejan algo "instalado" en el cliente y generan
# renovaciones, soporte o reposición.
CATEGORIAS_INSTALABLES = {"Licenciamiento", "Infraestructura", "Almacenamiento"}
DIAS_AVISO_RENOVACION = 60  # alertar renovaciones que vencen en los próximos N días

# --- Modelo de riesgo ---
HORIZONTE_DIAS = 90     # ¿volverá a comprar en los próximos 90 días?
SEMILLA = 42

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
