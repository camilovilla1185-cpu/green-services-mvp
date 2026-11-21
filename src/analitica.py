"""Vista 360 del cliente, segmentación y alertas.

Responde a tres preguntas del reto:
  1. ¿Qué se le ha vendido a cada cliente y cómo va la relación?  -> ficha_clientes
  2. ¿Quién es frecuente, quién se enfrió y quién es base instalada? -> segmento
  3. ¿A quién hay que llamar este mes y por qué?                    -> alertas
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config as cfg


def ficha_clientes(ventas: pd.DataFrame, clientes: pd.DataFrame,
                   corte: pd.Timestamp) -> pd.DataFrame:
    v = ventas[ventas.fecha <= corte]
    hace_12m = corte - pd.DateOffset(months=12)
    v12 = v[v.fecha > hace_12m]

    g = v.sort_values("fecha").groupby("cliente_id")
    f = pd.DataFrame({
        "ultima_factura": g.factura.last(),
        "primera_compra": g.fecha.min(),
        "ultima_compra": g.fecha.max(),
        "facturas_historicas": g.factura.nunique(),
        "ventas_historicas_cop": g.valor_cop.sum(),
        "margen_historico_cop": g.margen_cop.sum(min_count=1),
        "categorias": g.categoria.agg(lambda s: ", ".join(sorted(s.unique()))),
        "producto_principal": v.groupby(["cliente_id", "producto"]).valor_cop.sum()
                               .reset_index().sort_values("valor_cop")
                               .groupby("cliente_id").producto.last(),
    })
    g12 = v12.groupby("cliente_id")
    f["ventas_12m_cop"] = g12.valor_cop.sum()
    f["margen_12m_cop"] = g12.margen_cop.sum(min_count=1)
    f["meses_con_compra_12m"] = g12.mes.nunique()
    f[["ventas_12m_cop", "meses_con_compra_12m"]] = (
        f[["ventas_12m_cop", "meses_con_compra_12m"]].fillna(0))

    f["recencia_dias"] = (corte - f.ultima_compra).dt.days
    f["antiguedad_dias"] = (corte - f.primera_compra).dt.days
    f["ticket_promedio_cop"] = f.ventas_historicas_cop / f.facturas_historicas

    # Ciclo típico de recompra: mediana de días entre fechas de compra distintas
    ciclo = (v[["cliente_id", "fecha"]].drop_duplicates().sort_values("fecha")
             .groupby("cliente_id").fecha.apply(lambda s: s.diff().dt.days.median()))
    f["ciclo_recompra_dias"] = ciclo
    f["proxima_compra_estimada"] = f.ultima_compra + pd.to_timedelta(
        f.ciclo_recompra_dias.fillna(cfg.DIAS_ACTIVO), unit="D")

    # Base instalada: tiene productos que generan renovación o soporte
    # (por categoría configurada o porque el producto tiene ciclo de renovación)
    inst = v[v.categoria.isin(cfg.CATEGORIAS_INSTALABLES) | (v.meses_renovacion.fillna(0) > 0)]
    f["base_instalada"] = f.index.isin(inst.cliente_id.unique())
    f["valor_instalado_cop"] = inst.groupby("cliente_id").valor_cop.sum()
    f["valor_instalado_cop"] = f["valor_instalado_cop"].fillna(0)

    f["segmento"] = f.apply(_segmento, axis=1)

    # Puntaje RFM (1 a 5) para priorizar dentro de cada segmento
    f["r"] = _quintil(-f.recencia_dias)
    f["f"] = _quintil(f.meses_con_compra_12m)
    f["m"] = _quintil(f.ventas_12m_cop)
    f["rfm"] = f.r.astype(str) + f.f.astype(str) + f.m.astype(str)

    f = clientes.set_index("cliente_id").join(f, how="left")
    f["segmento"] = f["segmento"].fillna("Sin compras")
    return f.reset_index()


def _quintil(s: pd.Series) -> pd.Series:
    return (pd.qcut(s.rank(method="first"), 5, labels=[1, 2, 3, 4, 5])).astype(int)


def _segmento(c) -> str:
    # Frío primero: un cliente reciente que ya dejó de comprar no debe verse como «Nuevo»
    if c.recencia_dias >= cfg.DIAS_RIESGO:
        return "Frío"
    if c.antiguedad_dias <= cfg.DIAS_CLIENTE_NUEVO:
        return "Nuevo"
    if c.recencia_dias > cfg.DIAS_ACTIVO:
        # Un cliente que por costumbre compra cada 5 meses no está "en riesgo" al cuarto mes
        if pd.notna(c.ciclo_recompra_dias) and c.recencia_dias <= 1.25 * c.ciclo_recompra_dias:
            return "Ocasional"
        return "En riesgo"
    if cfg.MIN_TRANSACCIONES_FRECUENTE:  # regla definida por la fuente (paquete oficial)
        if c.facturas_historicas >= cfg.MIN_TRANSACCIONES_FRECUENTE:
            return "Frecuente"
    elif c.meses_con_compra_12m >= cfg.MIN_COMPRAS_FRECUENTE:
        return "Frecuente"
    return "Ocasional"


def renovaciones_desde_base(base: pd.DataFrame, ventas: pd.DataFrame, productos: pd.DataFrame,
                            corte: pd.Timestamp) -> pd.DataFrame:
    """Cuando la fuente trae la base instalada (instalaciones con fecha de fin), se usan esas
    fechas reales en vez de estimar el vencimiento desde la última venta. Por cliente y
    producto se toma la instalación más reciente (si ya se renovó, no hay alerta)."""
    b = base.copy()
    b["fecha_inicio"] = pd.to_datetime(b.fecha_inicio, errors="coerce")
    b["fecha_fin"] = pd.to_datetime(b.fecha_fin, errors="coerce")
    b = b[b.fecha_inicio <= corte].sort_values("fecha_fin")
    ult = b.groupby(["cliente_id", "producto_id"]).last().reset_index()
    p = productos.rename(columns={"nombre": "producto"})[["producto_id", "producto", "categoria",
                                                           "meses_renovacion"]]
    ult = ult.merge(p, on="producto_id", how="left")
    # Valor en juego: lo último que el cliente pagó por ese producto
    vv = (ventas[ventas.fecha <= corte].sort_values("fecha")
          .groupby(["cliente_id", "producto_id"]).valor_cop.last().rename("valor_ultimo_cop"))
    ult = ult.merge(vv.reset_index(), on=["cliente_id", "producto_id"], how="left")
    ult["valor_ultimo_cop"] = ult.valor_ultimo_cop.fillna(0)
    ult = ult.rename(columns={"fecha_inicio": "ultima_compra", "fecha_fin": "vence"})
    ult["factura_origen"] = "instalación " + ult.instalacion_id.astype(str)
    ult["dias_para_vencer"] = (ult.vence - corte).dt.days
    return ult[["cliente_id", "producto_id", "producto", "categoria", "meses_renovacion",
                "ultima_compra", "valor_ultimo_cop", "factura_origen", "vence", "dias_para_vencer",
                "instalacion_id", "unidades"]]


def renovaciones(ventas: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """Por cada producto instalado: cuándo vence y si ya se renovó."""
    v = ventas[(ventas.fecha <= corte) & (ventas.meses_renovacion > 0)]
    ult = (v.sort_values("fecha")
           .groupby(["cliente_id", "producto_id", "producto", "categoria", "meses_renovacion"])
           .agg(ultima_compra=("fecha", "max"), valor_ultimo_cop=("valor_cop", "last"),
                factura_origen=("factura", "last"))
           .reset_index())
    ult["vence"] = [d + pd.DateOffset(months=int(m))
                    for d, m in zip(ult.ultima_compra, ult.meses_renovacion)]
    ult["dias_para_vencer"] = (ult.vence - corte).dt.days
    return ult


def alertas(ficha: pd.DataFrame, ren: pd.DataFrame,
            corte: pd.Timestamp) -> pd.DataFrame:
    """Lista accionable para el equipo comercial, ordenada por prioridad."""
    a = []
    datos = ficha.set_index("cliente_id")

    # 1. Renovaciones que vencen pronto o que vencieron hace poco sin renovarse
    prox = ren[(ren.dias_para_vencer <= cfg.DIAS_AVISO_RENOVACION) & (ren.dias_para_vencer >= -90)]
    for r in prox.itertuples():
        c = datos.loc[r.cliente_id]
        vencida = r.dias_para_vencer < 0
        a.append({
            "cliente_id": r.cliente_id, "nombre": c.nombre, "comercial": c.comercial,
            "tipo": "Renovación vencida" if vencida else "Renovación próxima",
            "detalle": f"{r.producto}: {'venció' if vencida else 'vence'} el {r.vence:%d/%m/%Y}",
            "valor_en_juego_cop": r.valor_ultimo_cop,
            "accion": "Llamar hoy y enviar cotización de renovación" if vencida
            else "Enviar cotización de renovación antes del vencimiento",
            "fecha_limite": r.vence,
            "evidencia": (f"Base instalada: {str(r.factura_origen).split(' ', 1)[1]} "
                          f"(vigente desde {r.ultima_compra:%d/%m/%Y})"
                          if str(r.factura_origen).startswith("instalación ")
                          else f"Factura {r.factura_origen} del {r.ultima_compra:%d/%m/%Y}"),
        })

    # 2. Clientes valiosos que se están enfriando (usa la predicción si existe)
    tiene_riesgo = "prob_compra_90d" in ficha.columns
    valiosos = ficha[(ficha.segmento.isin(["En riesgo", "Frecuente", "Ocasional"]))
                     & (ficha.m >= 4)]
    for c in valiosos.itertuples():
        prob = c.prob_compra_90d if tiene_riesgo else np.nan
        ciclo = cfg.DIAS_ACTIVO if pd.isna(c.ciclo_recompra_dias) else c.ciclo_recompra_dias
        atrasado = c.recencia_dias > 1.5 * ciclo
        if (tiene_riesgo and prob < 0.5) or (not tiene_riesgo and atrasado) or c.segmento == "En riesgo":
            detalle = f"{int(c.recencia_dias)} días sin comprar (suele comprar cada {int(ciclo)})"
            if tiene_riesgo:
                detalle += f"; probabilidad de compra en {cfg.HORIZONTE_DIAS} días: {prob:.0%}"
            a.append({
                "cliente_id": c.cliente_id, "nombre": c.nombre, "comercial": c.comercial,
                "tipo": "Cliente valioso en riesgo",
                "detalle": detalle,
                "valor_en_juego_cop": c.ventas_12m_cop,
                "accion": "Visita o llamada de seguimiento; revisar satisfacción y necesidades",
                "fecha_limite": corte + pd.Timedelta(days=15),
                "evidencia": f"Última factura {c.ultima_factura} del {c.ultima_compra:%d/%m/%Y}",
            })

    # 3. Clientes fríos con buen historial: candidatos a reactivación
    frios = ficha[(ficha.segmento == "Frío") & (ficha.ventas_historicas_cop >=
                                                ficha.ventas_historicas_cop.quantile(0.6))]
    for c in frios.itertuples():
        a.append({
            "cliente_id": c.cliente_id, "nombre": c.nombre, "comercial": c.comercial,
            "tipo": "Reactivación",
            "detalle": f"Última compra {c.ultima_compra:%d/%m/%Y}; compró {c.producto_principal}",
            "valor_en_juego_cop": c.ventas_historicas_cop / max(c.antiguedad_dias / 365, 1),
            "accion": "Campaña de reactivación con oferta sobre su producto principal",
            "fecha_limite": corte + pd.Timedelta(days=30),
            "evidencia": f"Última factura {c.ultima_factura} del {c.ultima_compra:%d/%m/%Y}",
        })

    al = pd.DataFrame(a)
    if al.empty:
        return al
    peso = {"Renovación vencida": 4, "Cliente valioso en riesgo": 3,
            "Renovación próxima": 2, "Reactivación": 1}
    al["prioridad"] = al.tipo.map(peso)
    al = (al.sort_values(["prioridad", "valor_en_juego_cop"], ascending=False)
          .drop_duplicates(["cliente_id", "tipo", "detalle"]).reset_index(drop=True))
    al["prioridad"] = al.prioridad.map({4: "Alta", 3: "Alta", 2: "Media", 1: "Baja"})
    # Datos de contacto para que el comercial actúe sin buscar en otra plataforma
    contacto = [c for c in ["contacto_nombre", "contacto_cargo", "contacto_email",
                            "contacto_telefono"] if c in ficha.columns]
    al = al.merge(ficha[["cliente_id"] + contacto], on="cliente_id", how="left")
    al.insert(0, "alerta_id", [f"AL-{corte:%Y%m}-{i:04d}" for i in range(1, len(al) + 1)])
    al["fecha_corte"] = corte
    return al
