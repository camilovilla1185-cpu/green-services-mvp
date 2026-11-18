"""Tablero de Operaciones – Green Services and Solutions (MVP).

Ejecutar:  streamlit run app.py
Lee lo que deja el pipeline en data/processed/. Si no hay datos, ofrece
generarlos (modo demostración con datos ficticios).
"""
from __future__ import annotations

import io
import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config as cfg
from src import estilo, pipeline
from src.estilo import COLOR_ALERTA, COLOR_SEG, encabezado

P = cfg.DATOS_PROCESADOS
ORDEN_SEG = list(COLOR_SEG)

st.set_page_config(page_title="Operaciones · Green Services", page_icon="🌿", layout="wide")
MARCA = estilo.aplicar_estilo()
VERDE = MARCA["color_principal"]


# ---------------------------------------------------------------- utilidades
def cop(x: float) -> str:
    """Formato de pesos abreviado: $1.234 M o $12,3 mil M."""
    if pd.isna(x):
        return "—"
    if abs(x) >= 1e9:
        return f"${x / 1e9:,.1f} mil M".replace(",", "X").replace(".", ",").replace("X", ".")
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.0f} M".replace(",", ".")
    return f"${x:,.0f}".replace(",", ".")


@st.cache_data(show_spinner=False)
def cargar(_marca: float):
    leer = lambda n, fechas=(): pd.read_csv(P / n, parse_dates=list(fechas))
    d = {
        "ventas": leer("ventas_consolidadas.csv", ["fecha", "mes", "trm_fecha_publicada"]),
        "ficha": leer("ficha_clientes.csv", ["primera_compra", "ultima_compra",
                                             "proxima_compra_estimada"]),
        "alertas": leer("alertas.csv", ["fecha_limite", "fecha_corte"]),
        "ren": leer("renovaciones.csv", ["ultima_compra", "vence"]),
        "pron": leer("pronostico.csv", ["mes"]),
        "compras": leer("compras_consolidadas.csv", ["fecha"]),
        "bitacora": leer("bitacora_cargas.csv"),
        "rechazos": leer("rechazos.csv"),
        "met": json.loads((P / "metricas.json").read_text()),
    }
    return d


def marca_datos() -> float:
    f = P / "metricas.json"
    return f.stat().st_mtime if f.exists() else 0.0


def a_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xl:
        df.to_excel(xl, index=False)
    return buf.getvalue()


# ---------------------------------------------------------------- sin datos
if not (P / "metricas.json").exists():
    encabezado("Tablero de Operaciones", "Inteligencia operativa y comercial")
    st.info("Todavía no hay datos procesados. Puede cargar archivos reales en la sección "
            "**Cargar datos** o generar un conjunto de prueba con datos ficticios.")
    if st.button("Generar datos de prueba y procesar", type="primary"):
        with st.spinner("Generando y procesando..."):
            pipeline.ejecutar(demo=True)
        st.rerun()
    st.stop()

D = cargar(marca_datos())
ventas, ficha, alertas, met = D["ventas"], D["ficha"], D["alertas"], D["met"]
corte = pd.Timestamp(met["corte"])

# ---------------------------------------------------------------- menú
st.sidebar.markdown(f"### {MARCA['empresa']}")
st.sidebar.caption(f"Datos con corte al **{corte:%d/%m/%Y}** · lote `{met['etl']['lote_id']}`")
if ventas.get("dato_ficticio", pd.Series([False])).any():
    st.sidebar.warning("Modo prueba: todos los datos son ficticios.")
if "fuente" in ventas.columns and ventas.fuente.notna().any():
    st.sidebar.caption(f"Fuente: {ventas.fuente.dropna().iloc[0]}")
pagina = st.sidebar.radio("Sección", ["Resumen", "Clientes y segmentos", "Ficha del cliente",
                                      "Alertas del mes", "Trazabilidad", "Confiabilidad",
                                      "Cargar datos"])
comerciales = sorted(ficha.comercial.dropna().unique())
filtro_com = st.sidebar.multiselect("Comercial", comerciales, placeholder="Todos")
if filtro_com:
    ficha = ficha[ficha.comercial.isin(filtro_com)]
    ventas = ventas[ventas.comercial.isin(filtro_com)]
    alertas = alertas[alertas.comercial.isin(filtro_com)]

hace12 = corte - pd.DateOffset(months=12)
v12 = ventas[ventas.fecha > hace12]
v12_ant = ventas[(ventas.fecha > hace12 - pd.DateOffset(months=12)) & (ventas.fecha <= hace12)]


# ================================================================ RESUMEN
if pagina == "Resumen":
    encabezado("Resumen de la operación",
               "Cómo van las ventas, los márgenes y la cartera de clientes en los últimos 12 meses.")
    st.caption("Últimos 12 meses frente a los 12 anteriores. Cifras en pesos; las ventas en "
               "dólares se convierten con la TRM del día de cada factura.")
    k = st.columns(5)
    var = v12.valor_cop.sum() / v12_ant.valor_cop.sum() - 1 if len(v12_ant) else None
    k[0].metric("Ventas 12 meses", cop(v12.valor_cop.sum()),
                f"{var:+.1%}" if var is not None else None)
    hay_costos = v12.margen_cop.notna().any()
    k[1].metric("Margen bruto",
                f"{v12.margen_cop.sum() / v12.loc[v12.margen_cop.notna(), 'valor_cop'].sum():.1%}"
                if hay_costos else "—",
                help="(Ventas − costo de la orden de compra ligada) / ventas" if hay_costos
                else "Los datos cargados no traen costos de compra; el margen no se puede calcular.")
    activos = ficha.segmento.isin(["Frecuente", "Ocasional", "Nuevo"]).sum()
    k[2].metric("Clientes activos", int(activos), help=f"Compraron en los últimos {cfg.DIAS_ACTIVO} días o son nuevos")
    k[3].metric("Clientes en riesgo o fríos", int(ficha.segmento.isin(["En riesgo", "Frío"]).sum()))
    k[4].metric("Alertas de prioridad alta", int((alertas.prioridad == "Alta").sum()))

    # Ventas mensuales + pronóstico
    serie = ventas.groupby("mes").valor_cop.sum().reset_index()
    pron = D["pron"]
    fig = go.Figure()
    fig.add_bar(x=serie.mes, y=serie.valor_cop, name="Ventas reales", marker_color=MARCA["color_acento"], opacity=0.55,
                hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra></extra>")
    if not filtro_com:
        fig.add_scatter(x=pron.mes, y=pron.pronostico_cop, mode="lines+markers", name="Pronóstico",
                        line=dict(color=VERDE, width=3),
                        error_y=dict(type="data", symmetric=False,
                                     array=pron.maximo_cop - pron.pronostico_cop,
                                     arrayminus=pron.pronostico_cop - pron.minimo_cop),
                        hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra>pronóstico</extra>")
    fig.update_layout(title="Ventas por mes y pronóstico de los próximos tres meses",
                      height=380, margin=dict(t=50, b=10), yaxis_title="COP", legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")
    if not filtro_com:
        st.caption(f"Error medio del pronóstico en los últimos 6 meses: "
                   f"{met['pronostico']['mape_pronostico']:.0%} (repetir el mes anterior: "
                   f"{met['pronostico']['mape_mes_anterior']:.0%}). El último mes puede estar incompleto.")

    c1, c2 = st.columns(2)
    cat = (v12.groupby("categoria").agg(valor_cop=("valor_cop", "sum"),
                                        margen_cop=("margen_cop", lambda x: x.sum(min_count=1)))
           .sort_values("valor_cop").reset_index())
    cat["margen_pct"] = cat.margen_cop / cat.valor_cop
    c1.plotly_chart(px.bar(cat, x="valor_cop", y="categoria", orientation="h",
                           text=cat.margen_pct.map(lambda m: "" if pd.isna(m) else f"{m:.0%} margen"),
                           title="Ventas 12 meses por categoría", labels={"valor_cop": "COP", "categoria": ""},
                           color=cat.valor_cop, color_continuous_scale=[MARCA["color_secundario"], MARCA["color_acento"], VERDE]
                           ).update_layout(height=380, coloraxis_showscale=False),
                    width="stretch")

    # Exposición a la TRM: dato clave para la Gerencia Financiera
    usd = v12[v12.moneda == "USD"]
    trm = pd.read_csv(P / "trm_diaria.csv", parse_dates=["fecha"])
    trm = trm[trm.fecha > hace12 - pd.DateOffset(months=12)]
    c2.plotly_chart(px.line(trm, x="fecha", y="valor", title="TRM diaria (COP por USD)",
                            labels={"valor": "COP", "fecha": ""},
                            color_discrete_sequence=["#2D7DD2"]).update_traces(fill="tozeroy", fillcolor="rgba(45,125,210,.10)").update_layout(height=380),
                    width="stretch")
    usd_vendidos = usd.valor_original.sum()
    usd_costo = (usd.costo_cop / usd.trm).sum()
    usd_txt = f"{usd_vendidos:,.0f}".replace(",", ".")
    if usd.empty:
        st.markdown("**Exposición cambiaria.** En los datos cargados todas las ventas de los últimos 12 meses "
                    "están facturadas en pesos, así que la TRM no las afecta directamente. Sí puede afectar "
                    "el costo de los productos que Green compra en dólares (dato que no viene en esta "
                    "exportación).")
    else:
        st.markdown(
            f"**Exposición cambiaria.** El {usd.valor_cop.sum() / v12.valor_cop.sum():.0%} de las ventas "
            f"de los últimos 12 meses se facturó en dólares (US${usd_txt}). "
            f"Cada **$100 de variación en la TRM** mueve esas ventas en **{cop(usd_vendidos * 100)}** "
            f"al año. Como el costo también está en dólares, el efecto en margen es de "
            f"**{cop((usd_vendidos - usd_costo) * 100)}**, siempre que compra y venta se hagan con "
            f"TRM parecida.")


# ================================================================ SEGMENTOS
elif pagina == "Clientes y segmentos":
    encabezado("Clientes y segmentos",
               "Quién compra seguido, quién se está enfriando y dónde está la base instalada.")
    st.caption(f"Frecuente: compró en al menos {cfg.MIN_COMPRAS_FRECUENTE} meses del último año y sigue activo · "
               f"En riesgo: entre {cfg.DIAS_ACTIVO} y {cfg.DIAS_RIESGO} días sin comprar · "
               f"Frío: más de {cfg.DIAS_RIESGO} días · Nuevo: primera compra hace menos de "
               f"{cfg.DIAS_CLIENTE_NUEVO} días · Base instalada: tiene licencias, equipos o "
               f"almacenamiento que se renuevan.")
    seg = (ficha.groupby("segmento").agg(clientes=("cliente_id", "count"),
                                         ventas_12m=("ventas_12m_cop", "sum"),
                                         base_instalada=("base_instalada", "sum"))
           .reindex(ORDEN_SEG).dropna(how="all").reset_index())
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(seg, x="segmento", y="clientes", color="segmento", text="clientes",
                           color_discrete_map=COLOR_SEG, title="Número de clientes por segmento")
                    .update_layout(showlegend=False, height=340, xaxis_title=""), width="stretch")
    c2.plotly_chart(px.bar(seg, x="segmento", y="ventas_12m", color="segmento",
                           color_discrete_map=COLOR_SEG, title="Ventas de los últimos 12 meses por segmento",
                           labels={"ventas_12m": "COP"})
                    .update_layout(showlegend=False, height=340, xaxis_title=""), width="stretch")

    act = ficha.dropna(subset=["recencia_dias"])
    fig = px.scatter(act, x="recencia_dias", y="ventas_historicas_cop", color="segmento",
                     size=act.meses_con_compra_12m.clip(lower=0.5), color_discrete_map=COLOR_SEG,
                     category_orders={"segmento": ORDEN_SEG}, log_y=True,
                     hover_name="nombre", hover_data={"cliente_id": True, "comercial": True,
                                                     "prob_compra_90d": ":.0%"},
                     labels={"recencia_dias": "Días desde la última compra",
                             "ventas_historicas_cop": "Ventas históricas (COP, escala log)"},
                     title="Mapa de clientes: qué tan reciente compraron y cuánto han comprado")
    for x in (cfg.DIAS_ACTIVO, cfg.DIAS_RIESGO):
        fig.add_vline(x=x, line_dash="dot", line_color="gray")
    st.plotly_chart(fig.update_layout(height=460), width="stretch")
    st.caption("Cada punto es un cliente; el tamaño indica en cuántos meses del último año compró. "
               "Los puntos grandes a la derecha de las líneas son clientes valiosos que se están perdiendo.")

    ficha = ficha.assign(prob_pct=ficha.prob_compra_90d * 100)
    cols = ["cliente_id", "nombre", "segmento", "comercial", "ventas_12m_cop", "recencia_dias",
            "ciclo_recompra_dias", "prob_pct", "base_instalada", "rfm", "ultima_factura"]
    st.dataframe(ficha[cols].sort_values("ventas_12m_cop", ascending=False), hide_index=True,
                 width="stretch",
                 column_config={"ventas_12m_cop": st.column_config.NumberColumn("Ventas 12m", format="$%d"),
                                "prob_pct": st.column_config.ProgressColumn(
                                    "Prob. compra 90 días", format="%.0f%%", min_value=0, max_value=100),
                                "recencia_dias": "Días sin comprar",
                                "ciclo_recompra_dias": "Ciclo (días)"})
    st.download_button("Descargar en Excel", a_excel(ficha[cols]), "segmentos.xlsx")


# ================================================================ FICHA 360
elif pagina == "Ficha del cliente":
    encabezado("Ficha del cliente", "Todo lo que se le ha vendido a un cliente, en una sola vista.")
    opciones = ficha.sort_values("ventas_historicas_cop", ascending=False)
    eleccion = st.selectbox("Cliente", opciones.cliente_id,
                            format_func=lambda c: f"{c} · {opciones.set_index('cliente_id').loc[c, 'nombre']}")
    c = ficha.set_index("cliente_id").loc[eleccion]
    vc = ventas[ventas.cliente_id == eleccion].sort_values("fecha", ascending=False)

    a, b = st.columns([2, 1])
    a.subheader(c.nombre)
    a.markdown(f"NIT {c.get('nit', '—')} · {c.sector} · {c.ciudad} · {c.get('tamano', '')}  \n"
               f"Comercial: **{c.comercial}**  \n"
               f"Contacto: **{c.get('contacto_nombre', '—')}**, {c.get('contacto_cargo', '')} · "
               f"{c.get('contacto_email', '')} · {c.get('contacto_telefono', '')}")
    b.markdown(f"<div style='padding:12px;border-radius:8px;background:{COLOR_SEG.get(c.segmento, '#999')};"
               f"color:white;text-align:center;font-size:20px'>{c.segmento}</div>", unsafe_allow_html=True)
    if bool(c.get("base_instalada")):
        b.caption("Pertenece a la base instalada")

    if vc.empty:
        st.info("Este cliente no tiene compras registradas.")
        st.stop()
    k = st.columns(5)
    k[0].metric("Ventas históricas", cop(c.ventas_historicas_cop))
    k[1].metric("Ventas 12 meses", cop(c.ventas_12m_cop))
    k[2].metric("Días sin comprar", int(c.recencia_dias),
                help=f"Última compra {c.ultima_compra:%d/%m/%Y}, factura {c.ultima_factura}")
    k[3].metric("Compra cada", f"{c.ciclo_recompra_dias:.0f} días" if pd.notna(c.ciclo_recompra_dias) else "—")
    k[4].metric("Prob. compra 90 días", f"{c.prob_compra_90d:.0%}" if pd.notna(c.prob_compra_90d) else "—")

    al_c = alertas[alertas.cliente_id == eleccion]
    for r in al_c.itertuples():
        st.warning(f"**{r.tipo}** ({r.alerta_id}) · {r.detalle}. Acción sugerida: {r.accion}. "
                   f"Soporte: {r.evidencia}.")

    hist = vc.groupby(["mes", "categoria"]).valor_cop.sum().reset_index()
    st.plotly_chart(px.bar(hist, x="mes", y="valor_cop", color="categoria",
                           title="Historial de compras por mes", labels={"valor_cop": "COP", "mes": ""})
                    .update_layout(height=340, legend=dict(orientation="h")), width="stretch")

    c1, c2 = st.columns(2)
    prod = (vc.groupby(["producto", "categoria"])
            .agg(veces=("factura", "nunique"), unidades=("cantidad", "sum"),
                 total_cop=("valor_cop", "sum"), ultima=("fecha", "max"))
            .sort_values("total_cop", ascending=False).reset_index())
    c1.markdown("**Qué se le ha vendido**")
    c1.dataframe(prod, hide_index=True, width="stretch",
                 column_config={"total_cop": st.column_config.NumberColumn("Total", format="$%d")})
    ren = D["ren"][D["ren"].cliente_id == eleccion].sort_values("vence")
    c2.markdown("**Base instalada y renovaciones**")
    if ren.empty:
        c2.caption("No tiene productos con renovación.")
    else:
        ren = ren.assign(estado=ren.dias_para_vencer.map(
            lambda d: "Vencida" if d < 0 else ("Próxima" if d <= cfg.DIAS_AVISO_RENOVACION else "Vigente")))
        c2.dataframe(ren[["producto", "vence", "estado", "factura_origen", "valor_ultimo_cop"]],
                     hide_index=True, width="stretch",
                     column_config={"vence": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                    "valor_ultimo_cop": st.column_config.NumberColumn("Último valor", format="$%d")})

    st.markdown("**Facturas** (cada línea lleva su archivo y fila de origen)")
    st.dataframe(vc[["fecha", "factura", "linea", "producto", "cantidad", "moneda", "valor_original",
                     "trm", "valor_cop", "margen_cop", "orden_compra", "archivo_origen", "fila_origen"]],
                 hide_index=True, width="stretch",
                 column_config={"fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                "valor_cop": st.column_config.NumberColumn(format="$%d"),
                                "margen_cop": st.column_config.NumberColumn(format="$%d")})


# ================================================================ ALERTAS
elif pagina == "Alertas del mes":
    encabezado("Alertas del mes", "Lista de trabajo para el equipo comercial. Cada alerta trae la acción "
               "sugerida, el contacto y la factura que la sustenta.")
    tipos = st.multiselect("Tipo de alerta", sorted(alertas.tipo.unique()), placeholder="Todos")
    al = alertas[alertas.tipo.isin(tipos)] if tipos else alertas
    k = st.columns(4)
    for i, t in enumerate(["Renovación vencida", "Cliente valioso en riesgo", "Renovación próxima",
                           "Reactivación"]):
        sub = al[al.tipo == t]
        k[i].metric(t, len(sub), cop(sub.valor_en_juego_cop.sum()) + " en juego", delta_color="off")
    porcom = al.groupby(["comercial", "tipo"]).size().reset_index(name="alertas")
    st.plotly_chart(px.bar(porcom, x="alertas", y="comercial", color="tipo", orientation="h",
                           color_discrete_map=COLOR_ALERTA, title="Alertas por comercial").update_layout(height=280, yaxis_title=""),
                    width="stretch")
    cols = ["alerta_id", "prioridad", "tipo", "nombre", "comercial", "detalle", "accion",
            "valor_en_juego_cop", "fecha_limite", "contacto_nombre", "contacto_email",
            "contacto_telefono", "evidencia"]
    cols = [c for c in cols if c in al.columns]
    st.dataframe(al[cols], hide_index=True, width="stretch",
                 column_config={"valor_en_juego_cop": st.column_config.NumberColumn("Valor en juego", format="$%d"),
                                "fecha_limite": st.column_config.DateColumn("Fecha límite", format="DD/MM/YYYY")})
    st.download_button("Descargar alertas en Excel", a_excel(al[cols]),
                       f"alertas_{corte:%Y-%m}.xlsx", type="primary")


# ================================================================ TRAZABILIDAD
elif pagina == "Trazabilidad":
    encabezado("Trazabilidad", "Del indicador a la fila exacta del archivo de origen.")
    st.caption("Desde cualquier alerta o factura se puede llegar a la fila exacta del archivo "
               "que la originó, la orden de compra que fija su costo y la TRM que se le aplicó.")
    modo = st.radio("Buscar por", ["Alerta", "Factura"], horizontal=True)
    if modo == "Alerta" and alertas.empty:
        st.info("No hay alertas con el filtro actual.")
        st.stop()
    if modo == "Alerta":
        aid = st.selectbox("Alerta", alertas.alerta_id,
                           format_func=lambda a: f"{a} · {alertas.set_index('alerta_id').loc[a, 'tipo']} · "
                                                 f"{alertas.set_index('alerta_id').loc[a, 'nombre']}")
        r = alertas.set_index("alerta_id").loc[aid]
        st.markdown(f"**{r.tipo}** para **{r.nombre}** ({r.cliente_id}).  \nRegla que la disparó: "
                    f"{r.detalle}.  \nSoporte: {r.evidencia}.")
        factura = r.evidencia.split("ctura ")[1].split(" ")[0]
    else:
        factura = st.text_input("Número de factura", ventas.factura.iloc[-1])
    lin = D["ventas"][D["ventas"].factura == factura]
    if lin.empty:
        st.error("No se encontró esa factura.")
        st.stop()
    st.subheader(f"Factura {factura}")
    for l in lin.itertuples():
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**Línea {l.linea}: {l.producto}**  \n{l.cantidad} × {l.precio_unitario:,.2f} {l.moneda}  \n"
                        f"Valor en pesos: **{cop(l.valor_cop)}**")
            c1.caption(f"Origen: `{l.archivo_origen}` fila {l.fila_origen} · registro `{l.registro_id}` · "
                       f"huella `{l.hash_registro}` · lote `{l.lote_id}`")
            if l.moneda == "USD":
                c2.markdown(f"**TRM aplicada:** {l.trm:,.2f}  \nPublicada el {pd.Timestamp(l.trm_fecha_publicada):%d/%m/%Y} "
                            f"(registro `{l.trm_registro_id}`)")
            else:
                c2.markdown("**TRM:** no aplica, factura en pesos")
            if pd.isna(l.costo_cop):
                c3.markdown(f"**Costo:** sin dato  \n{l.metodo_costo}")
            else:
                c3.markdown(f"**Costo:** {cop(l.costo_cop)} ({l.metodo_costo})  \nOrden de compra `{l.orden_compra}` "
                            f"a {l.proveedor}  \n**Margen:** {cop(l.margen_cop)}")
    compras_d = D["compras"]
    if "factura_relacionada" in compras_d.columns and not compras_d.empty:
        oc = compras_d[compras_d.factura_relacionada == factura]
        st.markdown("**Órdenes de compra ligadas**")
        st.dataframe(oc[["orden", "fecha", "proveedor", "producto_id", "cantidad", "costo_unitario", "moneda",
                         "trm", "valor_cop", "archivo_origen", "fila_origen", "hash_registro"]],
                     hide_index=True, width="stretch")
    else:
        st.caption("Los datos cargados no traen órdenes de compra ligadas a las facturas.")

    st.divider()
    st.subheader("Bitácora de cargas")
    st.dataframe(D["bitacora"].sort_values("fecha_carga", ascending=False), hide_index=True,
                 width="stretch")
    st.subheader("Registros rechazados en el último lote")
    if D["rechazos"].empty:
        st.success("Ningún registro fue rechazado.")
    else:
        st.dataframe(D["rechazos"], hide_index=True, width="stretch")


# ================================================================ CONFIABILIDAD
elif pagina == "Confiabilidad":
    encabezado("¿Qué tanto se puede confiar en las predicciones?",
               "Pruebas hacia atrás: el modelo se entrena con el pasado y se califica con lo que pasó después.")
    r = met["riesgo"]
    st.markdown(
        "La probabilidad de compra se probó **hacia atrás**: se tomaron cuatro fechas del pasado, se "
        "entrenó solo con lo que se sabía en cada una y se verificó quién compró en los 90 días siguientes. "
        "Se compara con la regla que usaría cualquier persona: *quien lleva más días sin comprar es "
        "quien tiene más riesgo*.")
    pr = pd.DataFrame(r["pruebas"])
    larga = pr.melt(id_vars="corte", value_vars=["auc_regla", "auc_modelo", "auc_mezcla"],
                    var_name="método", value_name="auc").replace(
        {"auc_regla": "Regla de días sin comprar", "auc_modelo": "Modelo", "auc_mezcla": "Mezcla (la que se usa)"})
    st.plotly_chart(px.bar(larga, x="corte", y="auc", color="método", barmode="group",
                           title="Capacidad de ordenar clientes por riesgo (AUC; 0,5 = azar, 1 = perfecto)",
                           color_discrete_sequence=["#A0AEC0", MARCA["color_acento"], VERDE])
                    .update_yaxes(range=[0.5, 1]).update_layout(height=380, xaxis_title="Fecha de prueba"),
                    width="stretch")
    k = st.columns(3)
    k[0].metric("AUC promedio de la mezcla", f"{r['auc_mezcla_promedio']:.2f}",
                f"{r['auc_mezcla_promedio'] - r['auc_regla_promedio']:+.2f} frente a la regla")
    k[1].metric("Acierto en los 30 más riesgosos", f"{r['acierto_top30_mezcla_promedio']:.0%}",
                help="De los 30 clientes con menor probabilidad, cuántos efectivamente no compraron")
    k[2].metric("Cortes en que la mezcla gana", f"{r['cortes_donde_mezcla_supera_regla']} de {len(pr)}")
    st.info("Con datos de prueba estas cifras solo demuestran que el método funciona. Con los datos "
            "reales hay que repetir esta validación antes de usar las probabilidades para decidir.")


# ================================================================ CARGAR
elif pagina == "Cargar datos":
    encabezado("Cargar datos del mes", "Suba las exportaciones del mes y personalice la marca del tablero.")
    st.warning("Si esta página está publicada en internet, **no suba datos reales**: la empresa no "
               "permite divulgarlos. Use datos reales solo en un equipo o servidor interno.")

    st.subheader("Opción A · Exportación de facturación (un solo archivo)")
    st.markdown("Un CSV o Excel con una fila por línea de factura y estas columnas: **Fecha Factura, "
                "No. Factura, NIT, Razón Social, Sector, Ciudad, Vendedor, Línea de negocio, Descripción, "
                "Valor Total**. Acepta separador `;` o `,` y valores con punto de miles. Los meses de "
                "renovación de cada producto se ajustan en `data/catalogo_facturacion.csv`.")
    plano = st.file_uploader("Exportación de facturación", type=["csv", "xlsx"], key="plano")
    if plano and st.button("Importar y procesar", type="primary", key="btn_plano"):
        with st.spinner("Importando y procesando (puede tardar unos 20 segundos)..."):
            try:
                pipeline.ejecutar(facturacion=plano.getvalue() if plano.name.lower().endswith(".csv")
                                  else io.BytesIO(plano.getvalue()), nombre_archivo=plano.name)
                st.cache_data.clear()
                st.success("Listo. Los datos se actualizaron.")
                st.rerun()
            except Exception as e:  # mostrar el problema en palabras simples
                st.error(f"No se pudo procesar: {e}")

    st.subheader("Opción B · Archivos separados por plataforma")
    st.markdown("Suba las exportaciones de cada plataforma en CSV o Excel. Columnas mínimas "
                "(compras es opcional):")
    st.table(pd.DataFrame({"archivo": list(cfg.ESQUEMA),
                           "columnas mínimas": [", ".join(c) for c in cfg.ESQUEMA.values()]}))
    archivos = st.file_uploader("Archivos", type=["csv", "xlsx"], accept_multiple_files=True)
    if archivos and st.button("Guardar y procesar", type="primary"):
        cfg.DATOS_CRUDOS.mkdir(parents=True, exist_ok=True)
        for f in archivos:
            (cfg.DATOS_CRUDOS / f.name).write_bytes(f.getvalue())
        with st.spinner("Procesando..."):
            try:
                pipeline.ejecutar()
                st.success("Listo. Los datos se actualizaron.")
                st.cache_data.clear()
            except Exception as e:  # mostrar el problema en palabras simples
                st.error(f"No se pudo procesar: {e}")

    st.divider()
    st.subheader("Datos de prueba (ficticios)")
    ejemplo = cfg.RAIZ / "data" / "ejemplos" / "ventas_prueba_green_2.csv"
    c1, c2 = st.columns(2)
    if ejemplo.exists() and c1.button("Usar «ventas_prueba_green_2» (401 clientes, 2022–2026)"):
        with st.spinner("Importando y procesando..."):
            pipeline.ejecutar(facturacion=ejemplo)
        st.cache_data.clear()
        st.rerun()
    if c2.button("Usar datos del generador (220 clientes, con costos y contactos)"):
        with st.spinner("Generando..."):
            pipeline.ejecutar(demo=True)
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("Personalizar marca")
    st.caption("El logo y los colores se aplican a todo el tablero. En la versión publicada en internet "
               "se pierden si la app se reinicia; para dejarlos fijos, suba el logo a la carpeta "
               "assets/ del repositorio con el nombre logo_empresa.png.")
    c1, c2 = st.columns([1, 1])
    with c1:
        logo = st.file_uploader("Logo de la empresa (PNG, JPG o SVG; ideal con fondo transparente)",
                                type=["png", "jpg", "jpeg", "svg", "webp"], key="logo")
        empresa = st.text_input("Nombre que aparece en el tablero", MARCA["empresa"])
    with c2:
        cc = st.columns(3)
        principal = cc[0].color_picker("Color principal", MARCA["color_principal"])
        acento = cc[1].color_picker("Color de acento", MARCA["color_acento"])
        secundario = cc[2].color_picker("Color secundario", MARCA["color_secundario"])
        st.image(str(estilo.ruta_logo()), caption="Logo actual", width=220)
    b1, b2 = st.columns([1, 1])
    if b1.button("Guardar marca", type="primary"):
        if logo is not None:
            estilo.guardar_logo(logo.name, logo.getvalue())
        estilo.guardar_marca(empresa=empresa, color_principal=principal, color_acento=acento,
                             color_secundario=secundario)
        st.rerun()
    if b2.button("Volver al diseño original"):
        estilo.quitar_logo()
        if estilo.ARCHIVO_MARCA.exists():
            estilo.ARCHIVO_MARCA.unlink()
        st.rerun()
