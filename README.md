# MVP · Inteligencia operativa y comercial
### Green Services and Solutions SAS · Reto empresarial 4 · EstudIA

Tablero que consolida compras, ventas y TRM en un solo lugar. Clasifica a cada
cliente (frecuente, ocasional, en riesgo, frío, nuevo y base instalada),
calcula su probabilidad de volver a comprar en 90 días, pronostica las ventas
de los próximos tres meses y entrega cada mes una lista de alertas por
comercial. Cada cifra se puede rastrear hasta la fila del archivo que la
originó.

> **Modo prueba.** Los datos incluidos son **inventados**: empresas, NIT,
> contactos, correos (dominio `.example`) y teléfonos. Cada archivo trae la
> columna `dato_ficticio = True`. Cualquier parecido con personas o empresas
> reales es casual.

---

## 1. Montar el tablero (10 minutos)

**Requisito:** Anaconda/Miniconda **o** Python 3.10 o superior
([python.org](https://www.python.org/downloads/)). Si instala Python, en la
primera pantalla marque *"Add python.exe to PATH"*.

### Opción rápida
- **Windows:** doble clic en `iniciar.bat`. Detecta solo si hay Anaconda
  (crea el entorno `green` con Python 3.11) o Python normal (crea `.venv`).
- **Mac / Linux:** `bash iniciar.sh`

La primera vez instala las librerías (unos minutos) y abre el tablero en el
navegador (`http://localhost:8501`). Las siguientes veces abre en segundos.
Para cerrarlo, cierre la ventana negra.

### Paso a paso (si prefiere hacerlo a mano)
```bash
cd green_mvp
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Mac / Linux:  source .venv/bin/activate
pip install -r requirements.txt

python -m src.pipeline --demo     # genera datos ficticios y los procesa
python -m pytest tests -q         # trazabilidad e importador (9 pruebas)
streamlit run app.py              # abre el tablero
```

### Publicarlo para que otros lo vean (Streamlit Community Cloud, gratis)
1. Suba la carpeta a un repositorio de GitHub (los datos procesados de prueba
   ya van incluidos, así que el tablero abre de inmediato).
2. Entre a [share.streamlit.io](https://share.streamlit.io) con su cuenta de
   GitHub → **Create app** → elija el repositorio, la rama `main` y el archivo
   `app.py`. En *Advanced settings* elija **Python 3.11**.
3. En un par de minutos queda en una dirección `https://<nombre>.streamlit.app`.
   Cualquier cambio que se suba a GitHub se publica solo.

Con datos reales **no** se publica en la nube pública: se corre en un equipo
o servidor interno de la empresa (la ficha del reto prohíbe divulgar los datos).

---

### Personalizar la marca (logo y colores)
En **Cargar datos → Personalizar marca** se sube el logo de la empresa (PNG, JPG o
SVG, ideal con fondo transparente), se cambia el nombre que aparece y se eligen
tres colores. Todo el tablero (encabezados, menú, indicadores y gráficas) toma
esos colores. Se guardan en `assets/logo_empresa.*` y `assets/marca.json`.
En la versión publicada, para que el logo no se pierda al reiniciar la app,
súbalo también al repositorio en `assets/logo_empresa.png`.

## 2. Qué muestra cada sección

| Sección | Para quién | Qué responde |
|---|---|---|
| Resumen | Gerencia, Gerencia Financiera | Ventas y margen de 12 meses, pronóstico de 3 meses, ventas por categoría, exposición a la TRM |
| Clientes y segmentos | Operaciones, comercial | Cuántos clientes hay en cada segmento y cuánto pesan; mapa de recencia contra valor |
| Ficha del cliente | Comercial | Contacto, qué se le ha vendido, base instalada, renovaciones, facturas, probabilidad de compra |
| Alertas del mes | Comercial | A quién llamar, por qué, con qué acción, valor en juego y factura que lo sustenta. Descargable en Excel |
| Trazabilidad | Operaciones, auditoría | De una alerta o factura a la fila de origen, la orden de compra, la TRM aplicada; bitácora y rechazos |
| Confiabilidad | Todos | Qué tan bien predice el modelo, probado hacia atrás contra una regla simple |
| Cargar datos | Operaciones | Subir los archivos del mes y reprocesar |

El filtro **Comercial** de la barra lateral deja a cada persona ver solo su cartera.

---

## 3. Cómo se rastrea cada dato

Ejemplo real de los datos de prueba:

```
Alerta AL-202610-0001 · Renovación vencida · Textiles Magdalena Ltda.
  └─ evidencia: Factura FE-11144 del 25/08/2025
       └─ línea 1 · Licencia firewall de nueva generación (año)
          registro VEN-11144-1 · ventas.csv fila 2355 · huella 1db3e6f9bca0 · lote L<fecha>-<hora>
            ├─ TRM 3.747,18 publicada el 25/08/2025 (registro TRM-20250825)
            └─ Orden de compra OC-52354 · Mayorista TecnoAndina S.A.S. · compras.csv fila 2355
```

- **`registro_id`**: identificador único en el sistema de origen.
- **`archivo_origen` + `fila_origen`**: dónde está la fila exacta.
- **`hash_registro`**: huella del contenido. Si alguien edita el archivo
  fuente, la huella cambia.
- **`lote_id`**: la corrida que lo procesó.
- **`bitacora_cargas.csv`**: una línea por archivo y lote, con huella del
  archivo y conteo de filas leídas, rechazadas y cargadas.
- **`rechazos.csv`**: lo que no entró y por qué (cliente inexistente, fecha
  inválida, precio negativo, duplicado, moneda desconocida).

---

## 4. Usarlo con datos reales

### Opción A · Una sola exportación de facturación
Si la plataforma de facturación exporta un archivo plano (una fila por línea
de factura), no hace falta armar cinco archivos. Columnas: **Fecha Factura,
No. Factura, NIT, Razón Social, Sector, Ciudad, Vendedor, Línea de negocio,
Descripción, Valor Total** (separador `;` o `,`, valores con punto de miles).

```bash
python -m src.pipeline --facturacion ruta/a/la/exportacion.csv
```
o en el tablero: **Cargar datos → Opción A**.

- Cada fila del original queda como una línea de venta en el mismo orden, así
  que `fila_origen` apunta a la fila exacta de la exportación.
- La línea de negocio se usa como categoría. Los meses de renovación de cada
  producto (para base instalada y alertas de renovación) se editan en
  `data/catalogo_facturacion.csv`, sin programar.
- Notas crédito, filas sin NIT y fechas inválidas van a **Rechazos** con su motivo.
- Esta exportación no trae costos ni contactos: el margen aparece como «—» y
  los contactos se completan cuando se cargue el maestro de clientes del CRM.
- Ejemplo incluido: `data/ejemplos/ventas_prueba_green_2.csv` (401 clientes
  ficticios, 2022–2026). Se activa en **Cargar datos → Datos de prueba**.

### Opción B · Un archivo por plataforma
Reemplace los archivos de `data/raw/` por las exportaciones reales (CSV o
Excel, mismo nombre) y corra `python -m src.pipeline` (sin `--demo`), o use la
sección **Cargar datos** del tablero.

| Archivo | Columnas mínimas | Recomendadas |
|---|---|---|
| `clientes` | cliente_id, nit, nombre, sector, ciudad, comercial | tamano, contacto_nombre, contacto_cargo, contacto_email, contacto_telefono |
| `productos` | producto_id, nombre, categoria, meses_renovacion | |
| `ventas` | fecha, factura, cliente_id, producto_id, cantidad, precio_unitario, moneda | registro_id, linea |
| `compras` (opcional) | fecha, orden, proveedor, producto_id, cantidad, costo_unitario, moneda | factura_relacionada, linea_relacionada |
| `trm` | fecha, valor | registro_id, fuente |

- Si las compras no traen la factura relacionada, el margen se calcula con el
  costo promedio del producto y así queda anotado en `metodo_costo`.
- La TRM oficial se puede descargar de datos.gov.co con
  `etl.trm_desde_datos_abiertos("2024-01-01", "2026-10-31")`.
- Umbrales (días para "en riesgo", "frío", categorías que cuentan como base
  instalada, horizonte de predicción) se ajustan en `src/config.py`.

---

## 5. Estructura

```
green_mvp/
├─ app.py                  tablero (Streamlit)
├─ iniciar.bat / .sh       arranque en un clic
├─ requirements.txt
├─ src/
│  ├─ config.py            umbrales y esquema de archivos
│  ├─ generar_datos.py     datos ficticios con trazabilidad
│  ├─ estilo.py            colores de marca, logo, CSS y plantilla de gráficas
│  ├─ etl.py               ingesta, validación, TRM, margen, bitácora
│  ├─ importar_facturacion.py  convierte una exportación plana de facturación
│  ├─ analitica.py         ficha 360, segmentos, renovaciones, alertas
│  ├─ modelo.py            probabilidad de recompra y pronóstico
│  └─ pipeline.py          corre todo el cierre mensual
├─ tests/                  pruebas de trazabilidad
├─ data/raw/               archivos de entrada
├─ data/catalogo_facturacion.csv  meses de renovación por producto (editable)
├─ data/ejemplos/          exportación de facturación de prueba
├─ data/processed/         modelo de datos consolidado
└─ outputs/                Excel de alertas por comercial
```

## 6. Declaración de herramientas de IA
El código y la documentación se desarrollaron con apoyo de Claude (Anthropic)
como asistente. Las decisiones de diseño, la validación de resultados y la
revisión final son responsabilidad del equipo.
