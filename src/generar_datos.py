"""Genera datos de prueba inventados, con trazabilidad completa.

Los datos de Green Services and Solutions no se pueden divulgar, así que el
MVP se construye y se demuestra con datos ficticios pero verosímiles:
empresas cliente con su NIT y su persona de contacto, un equipo comercial,
productos en pesos y en dólares, facturas con varias líneas, órdenes de
compra a proveedores ligadas a cada línea y una TRM diaria.

TODOS LOS NOMBRES, NIT, CORREOS Y TELÉFONOS SON INVENTADOS. Cada archivo trae
la columna dato_ficticio = True y los correos usan el dominio reservado
.example, que no existe en internet. Cualquier coincidencia con una persona o
empresa real es casual.

Trazabilidad: cada registro tiene un ID único, el sistema del que "salió"
(ERP, CRM, compras, TRM) y su fecha de creación. Las ventas apuntan al
cliente, al producto y al comercial; cada orden de compra apunta a la factura
y la línea que la originó. Con eso cualquier cifra del tablero se puede
seguir hasta la fila exacta que la produjo.

Uso:  python -m src.generar_datos
"""
import unicodedata

import numpy as np
import pandas as pd

from src.config import DATOS_CRUDOS, SEMILLA

INICIO = pd.Timestamp("2024-01-01")
FIN = pd.Timestamp("2026-10-31")

PRODUCTOS = [
    # id, nombre, categoria, precio de lista, moneda, meses_renovacion
    ("P01", "Licencia antivirus corporativo (usuario/año)", "Licenciamiento", 38, "USD", 12),
    ("P02", "Licencia suite ofimática (usuario/año)", "Licenciamiento", 95, "USD", 12),
    ("P03", "Licencia software de respaldo (servidor/año)", "Licenciamiento", 620, "USD", 12),
    ("P04", "Licencia firewall de nueva generación (año)", "Licenciamiento", 1450, "USD", 12),
    ("P05", "Servidor rack 2U", "Infraestructura", 7800, "USD", 36),
    ("P06", "Switch administrable 48 puertos", "Infraestructura", 2100, "USD", 36),
    ("P07", "Equipo portátil empresarial", "Infraestructura", 1150, "USD", 36),
    ("P08", "Cabina de almacenamiento NAS 40 TB", "Almacenamiento", 5400, "USD", 36),
    ("P09", "Discos de respaldo (lote x10)", "Almacenamiento", 900, "USD", 24),
    ("P10", "Respaldo en la nube (TB/mes)", "Servicios gestionados", 180_000, "COP", 0),
    ("P11", "Mesa de ayuda (usuario/mes)", "Servicios gestionados", 45_000, "COP", 0),
    ("P12", "Monitoreo de infraestructura (mes)", "Servicios gestionados", 1_900_000, "COP", 0),
    ("P13", "Digitalización documental (1.000 folios)", "Gestión documental", 420_000, "COP", 0),
    ("P14", "Custodia de archivo físico (caja/mes)", "Gestión documental", 9_500, "COP", 0),
    ("P15", "Borrado seguro certificado (equipo)", "Ciclo de vida", 85_000, "COP", 0),
    ("P16", "Disposición final de equipos (lote)", "Ciclo de vida", 1_300_000, "COP", 0),
    ("P17", "Consultoría en gobierno de datos (hora)", "Consultoría", 260_000, "COP", 0),
    ("P18", "Implementación y puesta en marcha (proyecto)", "Consultoría", 14_000_000, "COP", 0),
]
CATEGORIAS = sorted({p[2] for p in PRODUCTOS})

# --- Piezas para inventar nombres (combinaciones al azar, no personas reales) ---
NOMBRES = ["Ana", "Carlos", "Daniela", "Felipe", "Gloria", "Hernán", "Isabel", "Jorge",
           "Katherine", "Luis", "Mónica", "Nicolás", "Olga", "Pablo", "Rocío", "Santiago",
           "Tatiana", "Vanessa", "Wilson", "Yesenia", "Alejandro", "Beatriz", "Diego",
           "Elena", "Fabián", "Juliana", "Mauricio", "Natalia", "Óscar", "Paola"]
APELLIDOS = ["Restrepo", "Gómez", "Cárdenas", "Ospina", "Zapata", "Henao", "Montoya",
             "Salazar", "Quintero", "Vélez", "Arango", "Rendón", "Mejía", "Londoño",
             "Patiño", "Castaño", "Duque", "Giraldo", "Toro", "Valencia", "Bermúdez",
             "Correa", "Echeverri", "Franco", "Lozano", "Marín", "Naranjo", "Pineda"]
CARGOS = ["Director de TI", "Jefe de infraestructura", "Coordinador de compras",
          "Gerente administrativo", "Líder de gestión documental", "Analista de tecnología",
          "Director financiero", "Jefe de seguridad de la información"]
RAIZ_EMPRESA = ["Andina", "Cordillera", "Altiplano", "Pacífico", "Caribe", "Orinoco",
                "Nevado", "Guadua", "Ceiba", "Cóndor", "Llanura", "Bahía", "Sabana",
                "Magdalena", "Cauca", "Páramo", "Cafetal", "Roble", "Tayrona", "Quimbaya"]
GIRO = {"Salud": ["Clínica", "IPS", "Laboratorios"],
        "Educación": ["Colegio", "Instituto", "Fundación Universitaria"],
        "Financiero": ["Cooperativa", "Fondo de Empleados", "Inversiones"],
        "Manufactura": ["Industrias", "Plásticos", "Textiles"],
        "Comercio": ["Distribuidora", "Comercializadora", "Almacenes"],
        "Gobierno": ["Empresa de Servicios", "Instituto Municipal", "Secretaría"],
        "Logística": ["Transportes", "Logística", "Carga"],
        "Energía": ["Energías", "Hidroeléctrica", "Gas"]}
FORMA = ["S.A.S.", "S.A.", "Ltda.", "S.A.S. BIC"]
CIUDADES = ["Bogotá", "Medellín", "Cali", "Barranquilla", "Bucaramanga", "Pereira"]

EQUIPO_COMERCIAL = [
    ("V01", "Laura Vélez Cárdenas", "Medellín"),
    ("V02", "Andrés Ospina Toro", "Bogotá"),
    ("V03", "Camila Henao Marín", "Cali"),
    ("V04", "Julián Arango Duque", "Barranquilla"),
]
PROVEEDORES = [("PR01", "Mayorista TecnoAndina S.A.S."),
               ("PR02", "Distribuidora Global de TI S.A."),
               ("PR03", "Nube Latam S.A.S.")]

ARQUETIPOS = ["frecuente", "ocasional", "enfriandose", "nuevo", "perdido"]


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return t.lower().replace(" ", "").replace(".", "")


def digito_verificacion(nit: int) -> int:
    """Dígito de verificación según el algoritmo de la DIAN (módulo 11)."""
    pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    digitos = [int(d) for d in str(nit)][::-1]
    s = sum(d * p for d, p in zip(digitos, pesos)) % 11
    return s if s < 2 else 11 - s


def _trm(rng) -> pd.DataFrame:
    """Caminata aleatoria alrededor de valores típicos de la TRM (ficticia)."""
    dias = pd.date_range(INICIO, FIN, freq="D")
    valores = np.clip(3950 + np.cumsum(rng.normal(0, 14, len(dias))), 3600, 4500)
    return pd.DataFrame({"registro_id": [f"TRM-{d:%Y%m%d}" for d in dias],
                         "fecha": dias, "valor": valores.round(2),
                         "fuente": "Simulada (formato datos.gov.co)", "dato_ficticio": True})


def _clientes(rng, n: int = 220) -> pd.DataFrame:
    filas, usados = [], set()
    tipos = rng.choice(ARQUETIPOS, size=n, p=[0.20, 0.38, 0.17, 0.10, 0.15])
    for i in range(1, n + 1):
        sector = rng.choice(list(GIRO))
        while True:
            razon = f"{rng.choice(GIRO[sector])} {rng.choice(RAIZ_EMPRESA)} {rng.choice(FORMA)}"
            if razon not in usados:
                usados.add(razon)
                break
        nit = int(rng.integers(900_100_000, 901_899_999))
        nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        primero, apellido = nombre.split()[0], nombre.split()[1]
        dominio = _sin_tildes(razon.split(" S.")[0].split(" Ltda")[0])[:22]
        comercial = EQUIPO_COMERCIAL[int(rng.integers(0, len(EQUIPO_COMERCIAL)))]
        filas.append({
            "cliente_id": f"C{i:04d}",
            "nit": f"{nit}-{digito_verificacion(nit)}",
            "nombre": razon,
            "sector": sector,
            "ciudad": rng.choice(CIUDADES),
            "tamano": rng.choice(["Pequeña", "Mediana", "Grande"], p=[0.45, 0.40, 0.15]),
            "comercial_id": comercial[0],
            "comercial": comercial[1],
            "contacto_nombre": nombre,
            "contacto_cargo": rng.choice(CARGOS),
            "contacto_email": f"{_sin_tildes(primero)}.{_sin_tildes(apellido)}@{dominio}.example",
            "contacto_telefono": f"+57 000 {int(rng.integers(100, 999))} {int(rng.integers(1000, 9999))}",
            "fuente": "CRM (simulado)",
            "creado_en": INICIO - pd.Timedelta(days=int(rng.integers(0, 900))),
            "dato_ficticio": True,
            "_arquetipo": tipos[i - 1],
        })
    return pd.DataFrame(filas)


def _ventas(rng, clientes, productos) -> pd.DataFrame:
    filas, n_factura = [], 10_000
    meses = pd.date_range(INICIO, FIN, freq="MS")
    escala = {"Pequeña": 1, "Mediana": 2.5, "Grande": 5}
    prob = {"frecuente": 0.70, "ocasional": 0.20, "enfriandose": 0.45, "nuevo": 0.6, "perdido": 0.35}

    for c in clientes.to_dict("records"):
        tipo = c["_arquetipo"]
        alta = (FIN - pd.Timedelta(days=int(rng.integers(20, 115))) if tipo == "nuevo"
                else INICIO + pd.Timedelta(days=int(rng.integers(0, 300))))
        baja = {"enfriandose": FIN - pd.Timedelta(days=int(rng.integers(100, 330))),
                "perdido": FIN - pd.Timedelta(days=int(rng.integers(400, 700)))}.get(tipo, FIN)
        # Cada cliente compra de 2 a 4 categorías: no todos tienen base instalada
        cats = set(rng.choice(CATEGORIAS, size=int(rng.integers(2, 5)), replace=False))
        candidatos = productos[productos.categoria.isin(cats)]
        pesos = rng.dirichlet(np.ones(len(candidatos)))
        renov = {}

        def facturar(fecha, items):
            nonlocal n_factura
            n_factura += 1
            for linea, (pid, motivo) in enumerate(items, start=1):
                p = productos.loc[pid]
                base = escala[c["tamano"]]
                cant = (int(max(1, rng.poisson(base * 0.5)))
                        if p.categoria in ("Infraestructura", "Almacenamiento", "Consultoría")
                        else int(max(1, rng.poisson(base * 5))))
                filas.append({
                    "registro_id": f"VEN-{n_factura}-{linea}",
                    "fecha": pd.Timestamp(fecha).normalize(),
                    "factura": f"FE-{n_factura}", "linea": linea,
                    "cliente_id": c["cliente_id"], "comercial_id": c["comercial_id"],
                    "producto_id": pid, "cantidad": cant,
                    "precio_unitario": round(p.precio * rng.uniform(0.92, 1.08), 2),
                    "moneda": p.moneda, "motivo": motivo,
                    "fuente": "ERP facturación (simulado)", "dato_ficticio": True,
                })
                if p.meses_renovacion > 0:
                    renov[pid] = pd.Timestamp(fecha) + pd.DateOffset(months=int(p.meses_renovacion))

        for mes in meses:
            if mes < alta.replace(day=1) or mes > baja:
                continue
            # Renovaciones de lo que ya tiene instalado (80 % se renueva)
            for pid, vence in list(renov.items()):
                if vence.to_period("M") == mes.to_period("M"):
                    if rng.random() < 0.8 and vence <= baja:
                        facturar(vence, [(pid, "Renovación")])
                    else:
                        renov.pop(pid)
            estacional = 1.25 if mes.month in (3, 6, 11, 12) else 1.0
            if rng.random() < min(prob[tipo] * estacional, 0.95):
                dia = mes + pd.Timedelta(days=int(rng.integers(0, 27)))
                if dia > baja:
                    continue
                k = int(rng.integers(1, 4))
                elegidos = rng.choice(candidatos.index, size=min(k, len(candidatos)),
                                      replace=False, p=pesos)
                facturar(dia, [(pid, "Venta nueva") for pid in elegidos])
    v = pd.DataFrame(filas)
    return v[v.fecha <= FIN].sort_values(["fecha", "factura", "linea"]).reset_index(drop=True)


def _compras(rng, ventas, productos) -> pd.DataFrame:
    """Cada línea de venta tiene una orden de compra al proveedor, días antes."""
    filas = []
    for i, v in enumerate(ventas.itertuples(), start=1):
        p = productos.loc[v.producto_id]
        costo = rng.uniform(0.68, 0.82) if p.moneda == "USD" else rng.uniform(0.45, 0.65)
        prov = PROVEEDORES[0] if (p.moneda == "USD" and rng.random() < 0.6) else \
            PROVEEDORES[int(rng.integers(0, len(PROVEEDORES)))]
        filas.append({
            "registro_id": f"COM-{i:06d}",
            "fecha": v.fecha - pd.Timedelta(days=int(rng.integers(2, 20))),
            "orden": f"OC-{50_000 + i}",
            "proveedor_id": prov[0], "proveedor": prov[1],
            "producto_id": v.producto_id, "cantidad": v.cantidad,
            "costo_unitario": round(v.precio_unitario * costo, 2), "moneda": p.moneda,
            "factura_relacionada": v.factura, "linea_relacionada": v.linea,
            "fuente": "Módulo de compras (simulado)", "dato_ficticio": True,
        })
    return pd.DataFrame(filas)


def generar() -> None:
    rng = np.random.default_rng(SEMILLA)
    DATOS_CRUDOS.mkdir(parents=True, exist_ok=True)
    productos = pd.DataFrame(PRODUCTOS, columns=["producto_id", "nombre", "categoria",
                                                  "precio", "moneda", "meses_renovacion"]
                             ).set_index("producto_id")
    trm = _trm(rng)
    clientes = _clientes(rng)
    ventas = _ventas(rng, clientes, productos)
    compras = _compras(rng, ventas, productos)
    comerciales = pd.DataFrame(EQUIPO_COMERCIAL, columns=["comercial_id", "nombre", "sede"])
    comerciales["dato_ficticio"] = True

    clientes.drop(columns="_arquetipo").to_csv(DATOS_CRUDOS / "clientes.csv", index=False)
    comerciales.to_csv(DATOS_CRUDOS / "comerciales.csv", index=False)
    (productos.reset_index().rename(columns={"precio": "precio_lista"})
     .assign(fuente="ERP maestro de productos (simulado)", dato_ficticio=True)
     .to_csv(DATOS_CRUDOS / "productos.csv", index=False))
    ventas.to_csv(DATOS_CRUDOS / "ventas.csv", index=False)
    compras.to_csv(DATOS_CRUDOS / "compras.csv", index=False)
    trm.to_csv(DATOS_CRUDOS / "trm.csv", index=False)
    # El comportamiento simulado se guarda aparte solo para auditar el modelo.
    clientes[["cliente_id", "_arquetipo"]].to_csv(DATOS_CRUDOS / "_verdad_sintetica.csv",
                                                  index=False)
    print(f"Clientes: {len(clientes)} | Facturas: {ventas.factura.nunique()} "
          f"({len(ventas)} líneas) | Órdenes de compra: {len(compras)} | TRM: {len(trm)} días")


if __name__ == "__main__":
    generar()
