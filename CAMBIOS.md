# MVP Green Services: qué ajustamos y cómo usarlo

Hackatón EstudIA 2026 · Reto 4, IA en operaciones · Green Services and
Solutions SAS

Bitácora técnica para el equipo · 14 de noviembre de 2026

# 1. En una página

Tomamos el MVP que construyó el equipo (green_mvp) y lo dejamos
funcionando en un PC con Windows y publicado en internet. No cambiamos
su lógica de segmentación, modelo ni alertas. Agregamos tres cosas y
corregimos dos fallos.

- **Tablero publicado:**
  [<u>https://green-services-mvp-4ppjv5cikxyzcsiyouvxbb.streamlit.app</u>](https://green-services-mvp-4ppjv5cikxyzcsiyouvxbb.streamlit.app)

- **Código en GitHub:**
  [<u>https://github.com/camilovilla1185-cpu/green-services-mvp</u>](https://github.com/camilovilla1185-cpu/green-services-mvp)

- **Nuevo:** el tablero ahora lee una exportación plana de facturación
  (un solo archivo, como ventas_prueba_green_2.csv), además de los 5
  archivos originales.

- **Nuevo:** iniciar.bat detecta solo si el PC tiene Anaconda o Python y
  lo instala todo con doble clic.

- **Corregido:** un fallo con pandas 3 (la versión que se instala hoy) y
  la configuración que tumbaba la app en Streamlit Cloud.

**Importante:** todos los datos que se ven son ficticios. Con datos
reales de Green el tablero se usa solo en un equipo interno, nunca en la
versión publicada.

# 2. Qué recibimos

| **Material**              | **Qué es**                                                                                                                                                                                                                                                    |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| green_mvp.zip             | Código del MVP: ETL con trazabilidad, ficha 360°, segmentos, renovaciones, alertas, modelo de recompra (mezcla de gradient boosting y regla de días sin comprar), pronóstico y tablero Streamlit de 7 secciones. 220 clientes ficticios generados por código. |
| Propuesta MVP (.docx)     | Por qué esta solución, qué se dejó por fuera y cómo se usaría cada mes.                                                                                                                                                                                       |
| Informe técnico (.docx)   | Cómo se generaron los datos de prueba, cómo se calculan los indicadores y cómo se verificó.                                                                                                                                                                   |
| ventas_prueba_green_2.csv | Exportación plana de facturación ficticia: 7.723 líneas, 401 clientes, 6 vendedores, 5 líneas de negocio y 20 productos, de enero de 2022 a octubre de 2026. Separador «;» y valores con punto de miles.                                                      |

# 3. Qué cambiamos y por qué

| **Problema encontrado**                                                                                                             | **Qué hicimos**                                                                                                                                                                                 |
|-------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| El CSV de facturación no se podía cargar: el ETL espera 5 archivos (clientes, productos, ventas, compras y TRM) con otras columnas. | Nuevo módulo src/importar_facturacion.py que convierte la exportación plana en esos 5 archivos. Conserva el orden de filas, así que «fila_origen» apunta a la fila exacta del archivo original. |
| La exportación no trae costos, así que el ETL fallaba al no encontrar compras.csv.                                                  | compras ahora es opcional. Sin compras, el margen aparece como «—» y la línea queda marcada «sin costo (no hay datos de compras)».                                                              |
| Con pandas 3, el cálculo de la huella (hash) fallaba si un campo venía vacío.                                                       | Corregido en src/etl.py. Los resultados con los datos del generador no cambian: siguen siendo 69 alertas y 174 clientes con base instalada, igual que en los documentos.                        |
| Las notas crédito, las filas sin NIT y los valores vacíos no se rechazaban con un motivo claro.                                     | Nuevas reglas en el ETL: «valor vacío» y «cantidad o precio no positivos (nota crédito o error)». Todo queda en Trazabilidad → Rechazos.                                                        |
| La base instalada solo se reconocía por los nombres de categoría del generador.                                                     | También cuenta como base instalada cualquier producto con meses de renovación mayores que 0. Con los datos del generador el resultado es el mismo.                                              |
| iniciar.bat exigía Python en el PATH, así que no funcionaba en PCs que solo tienen Anaconda.                                        | Reescrito: si hay Anaconda crea el entorno «green» con Python 3.11; si no, usa Python normal con .venv. La primera vez instala todo y luego abre en segundos.                                   |
| En Streamlit Cloud la app se caía al arrancar.                                                                                      | .streamlit/config.toml tenía headless = false, así que el servidor se quedaba esperando un correo. Se cambió a true; el arranque local sigue abriendo el navegador.                             |
| Varias secciones fallaban o mostraban «nan» sin costos ni ventas en dólares.                                                        | Resumen, Exposición cambiaria y Trazabilidad ahora explican qué falta en lugar de fallar.                                                                                                       |
| Streamlit anuncia que use_container_width dejará de funcionar.                                                                      | Se reemplazó por width="stretch" y se pide streamlit 1.48 o superior.                                                                                                                           |

# 4. Cómo correrlo en un PC

## Windows (con Anaconda o con Python)

1.  Descomprimir green_mvp.zip, o descargar el código desde GitHub con
    **Code → Download ZIP**.

2.  Doble clic en **iniciar.bat**. Si Windows muestra «Windows protegió
    su PC», elegir «Más información» → «Ejecutar de todas formas».

3.  La primera vez tarda unos minutos instalando librerías. Al final se
    abre el navegador en http://localhost:8501.

4.  Para cerrarlo, cerrar la ventana negra.

Si el PC no tiene ni Anaconda ni Python: instalar Python 3.11 desde
python.org y, en la primera pantalla, marcar **«Add python.exe to
PATH»**.

## Mac / Linux

> bash iniciar.sh

## A mano (cualquier sistema)

> pip install -r requirements.txt
>
> python -m src.pipeline --demo \# datos del generador (220 clientes)
>
> python -m pytest tests -q \# 9 pruebas
>
> streamlit run app.py

# 5. Cómo usar la exportación de facturación

Hay dos formas de cargar ventas_prueba_green_2.csv, o la exportación
real de Green cuando la entreguen:

- **En el tablero:** sección Cargar datos → «Opción A · Exportación de
  facturación» (subir el archivo) o «Datos de prueba» → «Usar
  ventas_prueba_green_2».

- **Por consola:**

> python -m src.pipeline --facturacion
> data/ejemplos/ventas_prueba_green_2.csv

Columnas esperadas: **Fecha Factura, No. Factura, NIT, Razón Social,
Sector, Ciudad, Vendedor, Línea de negocio, Descripción, Valor Total**.
Acepta CSV con «;» o «,» y Excel. Los nombres se reconocen aunque
cambien tildes o mayúsculas.

**Catálogo de renovaciones (revisar en equipo).**
data/catalogo_facturacion.csv dice cada cuántos meses se renueva cada
producto. Con eso se calculan la base instalada y las alertas de
renovación. Los valores son supuestos nuestros: 12 meses para licencias,
suscripciones y contratos (Microsoft 365, endpoints, SOC, Veeam,
Omnissa, Equinix, FLEX GPT), 36 meses para equipos (Dell, Nutanix,
Juniper) y 0 para servicios por proyecto o consumo (AWS, soporte,
consultoría). Se edita en Excel sin programar.

**Qué no trae la exportación:** costos (por eso el margen sale «—») y
contactos (las alertas salen sin nombre ni teléfono). Se completan
cargando también compras y el maestro de clientes del CRM.

# 6. Resultados con cada conjunto de datos

| **Indicador**                                         | **Generador (green_mvp)**                                                                          | **ventas_prueba_green_2**                                                                          |
|-------------------------------------------------------|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Clientes                                              | 220                                                                                                | 401                                                                                                |
| Periodo                                               | Ene 2024 – oct 2026                                                                                | Ene 2022 – oct 2026 (corte 27/10/2026)                                                             |
| Segmentos                                             | 69 frecuentes · 33 ocasionales · 24 nuevos · 20 en riesgo · 70 fríos · 4 sin compras               | 155 frecuentes · 55 ocasionales · 25 nuevos · 26 en riesgo · 139 fríos · 1 sin compras             |
| Clientes con base instalada                           | 174                                                                                                | 381                                                                                                |
| Alertas del mes                                       | 69 (11 renovaciones vencidas, 25 próximas, 12 clientes valiosos en riesgo, 21 reactivaciones)      | 270 (82 renovaciones vencidas, 116 próximas, 20 clientes valiosos en riesgo, 52 reactivaciones)    |
| Modelo de recompra (AUC promedio, prueba hacia atrás) | Mezcla 0,81 frente a regla 0,79; gana en 3 de 4 fechas; acierta en el 93 % de los 30 más riesgosos | Mezcla 0,83 frente a regla 0,79; gana en 4 de 4 fechas; acierta en el 85 % de los 30 más riesgosos |
| Pronóstico de ventas (MAPE)                           | 15 % (repetir el mes anterior: 19 %)                                                               | 22 % (repetir el mes anterior: 21 %)                                                               |
| Filas rechazadas                                      | Las sembradas por el generador                                                                     | 3: una nota crédito, una fila sin NIT y una fecha inválida                                         |
| Tiempo de proceso                                     | ≈ 30 s                                                                                             | ≈ 18 s                                                                                             |

*Ojo para la sustentación: con ventas_prueba_green_2 hay muchas alertas
de renovación porque el catálogo marca 14 de los 20 productos como
renovables. Si el jurado lo pregunta, explicar que el catálogo se ajusta
con Green. Además, con estos datos el pronóstico no le gana a «repetir
el mes anterior» (con los del generador sí): se dice con honestidad,
igual que en la sección Confiabilidad.*

# 7. La versión publicada

- **Dónde:** Streamlit Community Cloud (gratis), conectado al
  repositorio de GitHub. Cada cambio que se sube a GitHub se publica
  solo en 1 o 2 minutos.

- **Con qué datos abre:** los del generador (220 clientes), que son los
  mismos de los documentos del equipo. El CSV se activa desde Cargar
  datos.

- **Si sale «removeChild… NotFoundError»:** es la traducción automática
  de Chrome. Hay que desactivarla para esa página («Mostrar original» o
  «No traducir nunca este sitio») y recargar.

- **Si la app «se durmió»:** Streamlit Cloud apaga las apps sin visitas
  por varios días. Basta con hacer clic en «Yes, get this app back up» y
  esperar un minuto.

- **Datos reales:** nunca en la versión publicada, porque la ficha del
  reto prohíbe divulgarlos. Con datos reales se corre con iniciar.bat en
  un equipo de la empresa.

# 8. Pendientes para el equipo

1.  Revisar y ajustar los meses de renovación en
    data/catalogo_facturacion.csv.

2.  Confirmar con Jacob Arochi qué es el recurso «com» y en qué formato
    exportan facturación, compras y CRM.

3.  Decidir con qué conjunto de datos se hace la demo ante el jurado
    (recomendamos el del generador, porque muestra costos, contactos y
    órdenes de compra).

4.  Probar la URL publicada desde otro PC antes de la sustentación.

# 9. Archivos que cambiaron

| **Archivo**                               | **Cambio**                                                                                             |
|-------------------------------------------|--------------------------------------------------------------------------------------------------------|
| src/importar_facturacion.py               | Nuevo: importador de la exportación plana                                                              |
| data/catalogo_facturacion.csv             | Nuevo: meses de renovación por producto (editable)                                                     |
| data/ejemplos/ventas_prueba_green_2.csv   | Nuevo: datos de prueba del equipo                                                                      |
| tests/test_importar_facturacion.py        | Nuevo: 2 pruebas (ahora son 9 en total)                                                                |
| src/etl.py                                | Compras opcional, arreglo para pandas 3 y nuevas reglas de rechazo                                     |
| src/analitica.py                          | Base instalada también por meses de renovación; margen vacío si no hay costos                          |
| src/pipeline.py                           | Nueva opción --facturacion                                                                             |
| app.py                                    | Cargar datos con opción A/B y datos de prueba; secciones que toleran datos sin costos; width="stretch" |
| iniciar.bat / iniciar.sh                  | Detección de Anaconda o Python; abre el navegador                                                      |
| .streamlit/config.toml                    | headless = true, necesario para Streamlit Cloud                                                        |
| requirements.txt · README.md · .gitignore | streamlit ≥ 1.48; instrucciones nuevas; se ignoran .venv y data/real/                                  |

Los ajustes se hicieron con apoyo de Claude (Anthropic). Se verificaron
con las pruebas automáticas (9 de 9) y abriendo cada sección del tablero
con los dos conjuntos de datos en Python 3.11, 3.12 y 3.13.


# Ajustes del 20 de noviembre de 2026 (sugerencias del equipo)

## 1. Marca alineada con el sitio oficial (greencss.com)
- Colores tomados del sitio: morado corporativo **#3F2683**, verde azulado **#00AA90**,
  azul **#2571B4** y azul oscuro **#203456**; degradados de morado a verde azulado como en la web.
- Tipografía **Montserrat**, la misma del sitio.
- El logo de Green no se copió del sitio: hay que pedirlo a la empresa en buena calidad
  (PNG con fondo transparente o SVG) y subirlo en **Cargar datos → Personalizar marca**,
  o dejarlo en `assets/logo_empresa.png` del repositorio para que quede fijo en la versión publicada.

## 2. Pronóstico de ventas
**Qué pasaba:** el modelo leía el arranque de los datos (ventas casi en cero a inicios de 2024,
mientras «llegan» los clientes simulados) como si enero fuera siempre un mes malísimo, y solo
promediaba los últimos 6 meses sin mirar la tendencia. Por eso pronosticaba una caída fuerte.

**Qué se cambió (src/modelo.py):**
- Se ignoran los primeros meses si la historia arranca «desde cero».
- El índice estacional se suaviza cuando hay pocos años de historia (no exagera picos).
- Nivel y tendencia con suavizado de Holt amortiguado; el tablero **elige solo** la configuración
  que menos se equivocó pronosticando cada uno de los últimos 6 meses, y la muestra en pantalla.
- El gráfico compara cada mes pronosticado con **el mismo mes del año anterior**, con su variación.

**Resultado:**
| Datos | Error antes | Error ahora | Repetir mes anterior |
|---|---|---|---|
| Generador (220 clientes) | 15,3 % | 14,7 % | 19,3 % |
| ventas_prueba_green_2 | 21,6 % | 16,3 % | 20,8 % |

**Ojo:** en `ventas_prueba_green_2` las ventas crecen de 2022 a 2025, pero **2026 viene más bajo**
(enero–octubre: −19 % frente a 2025; septiembre y octubre: −36 %). El pronóstico refleja eso.
Si ese archivo se construyó para mostrar crecimiento, hay que revisar los datos de 2026.

## 3. Productos sin supuestos
- Los productos se muestran como **«Producto A», «Producto B»…** dentro de su línea de negocio,
  porque no hay un catálogo confiable de lo que vende Green.
- Las categorías del generador son ahora las **5 líneas de negocio oficiales**: Cloud & Data Center,
  Cybersecurity, End User Solutions, FLEX GPT y Professional Services.
- Con datos reales de Green se cambia `PRODUCTOS_GENERICOS = False` en `src/config.py` para ver los nombres reales.
- Los meses de renovación por producto siguen siendo un supuesto (`data/catalogo_facturacion.csv`):
  conviene validarlos con Green.
- Los segmentos, la base instalada (174) y las alertas (69) no cambian con esto.
