"""Pruebas del importador de exportaciones planas de facturación."""
import pandas as pd

from src.importar_facturacion import _a_numero, importar

CSV = """Fecha Factura;No. Factura;NIT;Razón Social;Sector;Ciudad;Vendedor;Línea de negocio;Descripción;Valor Total
01/01/2024;GS-1;900-1;Cliente Uno S.A.S.;Educación;Medellín;Ana Gómez;Ciberseguridad;Protección de endpoints;12.479.000
01/01/2024;GS-1;900-1;Cliente Uno S.A.S.;Educación;Medellín;Ana Gómez;Servicios Profesionales;Soporte y mesa de ayuda;2.750.000
15/02/2024;GS-2;900-2;Cliente Dos Ltda.;Salud;Bogotá;Luis Pérez;End User Solutions;Portátiles Dell Latitude;42.412.000
20/02/2024;GS-3;900-2;Cliente Dos Ltda.;Salud;Bogotá;Luis Pérez;Ciberseguridad;Nota crédito;-1.000.000
31/02/2024;GS-4;900-1;Cliente Uno S.A.S.;Educación;Medellín;Ana Gómez;Ciberseguridad;Protección de endpoints;1.000.000
""".encode("utf-8")


def test_numeros_con_punto_de_miles():
    s = _a_numero(pd.Series(["12.479.000", "-1.000.000", "2750", "1.234,50"]))
    assert s.tolist() == [12479000, -1000000, 2750, 1234.5]


def test_importa_una_fila_por_fila_original(tmp_path, monkeypatch):
    monkeypatch.setattr("src.importar_facturacion.PRODUCTOS_GENERICOS", False)
    r = importar(CSV, destino=tmp_path, nombre_archivo="prueba.csv")
    ventas = pd.read_csv(tmp_path / "ventas.csv")
    assert len(ventas) == 5 and r["clientes"] == 2 and r["comerciales"] == 2
    # El orden se conserva: la fila 2 del original es la primera línea
    assert ventas.factura.tolist() == ["GS-1", "GS-1", "GS-2", "GS-3", "GS-4"]
    assert ventas.linea.tolist() == [1, 2, 1, 1, 1]
    # La fecha inválida (31/02) y la nota crédito llegan al ETL para que las rechace con motivo
    assert ventas.fecha.isna().sum() == 1
    assert (ventas.precio_unitario < 0).sum() == 1
    productos = pd.read_csv(tmp_path / "productos.csv").set_index("nombre")
    assert productos.loc["Protección de endpoints", "meses_renovacion"] == 12
    assert productos.loc["Soporte y mesa de ayuda", "meses_renovacion"] == 0


def test_nombres_genericos_por_linea(tmp_path, monkeypatch):
    monkeypatch.setattr("src.importar_facturacion.PRODUCTOS_GENERICOS", True)
    importar(CSV, destino=tmp_path, nombre_archivo="prueba.csv")
    productos = pd.read_csv(tmp_path / "productos.csv")
    assert productos.nombre.str.match(r"^Producto [A-Z]+$").all()
    assert set(productos.categoria) == {"Ciberseguridad", "Servicios Profesionales", "End User Solutions"}
    # Los meses de renovación se siguen asignando con la descripción original
    assert productos.meses_renovacion.sum() == 12 + 36 + 12 * 0
