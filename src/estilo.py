"""Identidad visual del tablero: colores de marca, logo, CSS y plantilla de gráficas.

La marca se personaliza sin programar desde «Cargar datos → Personalizar marca»:
  - assets/logo_empresa.(png|jpg|svg)  logo subido por el usuario
  - assets/marca.json                  nombre y colores elegidos
Si no hay logo propio se usa assets/logo_base.svg (genérico).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from src.config import RAIZ

ASSETS = RAIZ / "assets"
ARCHIVO_MARCA = ASSETS / "marca.json"
LOGO_BASE = ASSETS / "logo_base.svg"

MARCA_DEFECTO = {
    "empresa": "Green Services and Solutions",
    "color_principal": "#1F6F50",
    "color_acento": "#13A89E",
    "color_secundario": "#8CC63F",
}

# Colores fijos para que cada segmento se reconozca en todo el tablero
COLOR_SEG = {"Frecuente": "#1F9D55", "Ocasional": "#13A89E", "Nuevo": "#2D7DD2",
             "En riesgo": "#F2A541", "Frío": "#E4572E", "Sin compras": "#A0AEC0"}
COLOR_ALERTA = {"Renovación vencida": "#E4572E", "Cliente valioso en riesgo": "#F2A541",
                "Renovación próxima": "#2D7DD2", "Reactivación": "#7E5BEF"}


# ----------------------------------------------------------------- marca
def leer_marca() -> dict:
    marca = dict(MARCA_DEFECTO)
    if ARCHIVO_MARCA.exists():
        try:
            marca.update(json.loads(ARCHIVO_MARCA.read_text(encoding="utf-8")))
        except Exception:
            pass
    return marca


def guardar_marca(**cambios) -> None:
    ASSETS.mkdir(exist_ok=True)
    marca = leer_marca()
    marca.update({k: v for k, v in cambios.items() if v})
    ARCHIVO_MARCA.write_text(json.dumps(marca, ensure_ascii=False, indent=2), encoding="utf-8")


def ruta_logo() -> Path:
    for ext in ("png", "jpg", "jpeg", "svg", "webp"):
        p = ASSETS / f"logo_empresa.{ext}"
        if p.exists():
            return p
    return LOGO_BASE


def guardar_logo(nombre: str, contenido: bytes) -> None:
    ASSETS.mkdir(exist_ok=True)
    for viejo in ASSETS.glob("logo_empresa.*"):
        viejo.unlink()
    ext = Path(nombre).suffix.lower().lstrip(".") or "png"
    (ASSETS / f"logo_empresa.{ext}").write_bytes(contenido)


def quitar_logo() -> None:
    for viejo in ASSETS.glob("logo_empresa.*"):
        viejo.unlink()


def _logo_data_uri() -> str:
    p = ruta_logo()
    mime = {"svg": "image/svg+xml", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp"}.get(p.suffix.lower().lstrip("."), "image/png")
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


# ----------------------------------------------------------------- estilo
def _plantilla_graficas(m: dict) -> None:
    colores = [m["color_principal"], m["color_acento"], "#2D7DD2", "#F2A541",
               m["color_secundario"], "#7E5BEF", "#E4572E", "#5A6B63"]
    plantilla = go.layout.Template(pio.templates["plotly_white"])
    plantilla.layout.update(
        colorway=colores,
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=13, color="#1C2421"),
        title=dict(font=dict(size=16, color="#1C2421"), x=0, xanchor="left"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=50, b=10),
        hoverlabel=dict(bgcolor="white", font_size=13, bordercolor=m["color_principal"]),
        legend=dict(bgcolor="rgba(0,0,0,0)", title_font=dict(size=12, color="#5A6B63")),
        xaxis=dict(gridcolor="#EEF2EF", zeroline=False, linecolor="#DDE4DF"),
        yaxis=dict(gridcolor="#EEF2EF", zeroline=False, linecolor="#DDE4DF"),
    )
    plantilla.data.bar = [go.Bar(marker=dict(line=dict(width=0), cornerradius=6))]
    pio.templates["green"] = plantilla
    pio.templates.default = "green"


def aplicar_estilo() -> dict:
    """Inyecta el CSS, registra la plantilla de gráficas y muestra el logo. Devuelve la marca."""
    m = leer_marca()
    _plantilla_graficas(m)
    p, a, s = m["color_principal"], m["color_acento"], m["color_secundario"]
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea {{
  font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
}}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* ---------- barra lateral ---------- */
section[data-testid="stSidebar"] > div {{
  background: linear-gradient(180deg, {p} 0%, color-mix(in srgb, {p} 45%, #0B1410) 100%);
}}
section[data-testid="stSidebar"] * {{ color: #EAF4EE !important; }}
section[data-testid="stSidebar"] [data-testid="stAlert"] {{
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18); border-radius: 12px;
}}
section[data-testid="stSidebar"] [data-testid="stAlert"] * {{ color: #FFF4D6 !important; }}
section[data-testid="stSidebar"] [data-testid="stAlertContainer"] {{ background: transparent; }}
section[data-testid="stSidebar"] [data-baseweb="select"] span,
section[data-testid="stSidebar"] [data-baseweb="select"] input,
section[data-testid="stSidebar"] [data-baseweb="tag"] * {{ color: #FFFFFF !important; }}
section[data-testid="stSidebar"] [data-baseweb="select"] svg {{ fill: #EAF4EE; }}
section[data-testid="stSidebar"] code {{ background: rgba(255,255,255,.12); color: #fff !important; }}
section[data-testid="stSidebar"] [role="radiogroup"] label {{
  padding: 8px 12px; border-radius: 10px; margin-bottom: 2px; transition: background .15s;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: rgba(255,255,255,.10); }}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
  background: rgba(255,255,255,.18); font-weight: 600;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] > div {{
  background: rgba(255,255,255,.10); border-color: rgba(255,255,255,.25);
}}
[data-testid="stSidebarHeader"] img, [data-testid="stLogo"] {{
  background: white; border-radius: 12px; padding: 6px 10px; box-sizing: content-box;
  height: auto !important; width: auto !important; max-height: 56px; max-width: 190px;
  object-fit: contain;
}}

/* ---------- encabezado de sección ---------- */
.gs-hero {{
  position: relative; overflow: hidden;
  background: linear-gradient(120deg, {p} 0%, {a} 62%, {s} 120%);
  border-radius: 20px; padding: 26px 30px; margin: 0 0 18px 0; color: white;
  box-shadow: 0 10px 30px -12px {p}99;
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
}}
.gs-hero::after {{
  content: ""; position: absolute; right: -60px; top: -60px; width: 240px; height: 240px;
  border-radius: 50%; background: rgba(255,255,255,.08);
}}
.gs-hero .gs-eyebrow {{ font-size: .78rem; letter-spacing: .14em; text-transform: uppercase;
  opacity: .85; font-weight: 600; }}
.gs-hero h1 {{ color: white !important; font-size: 2rem; font-weight: 800; margin: 4px 0 6px 0;
  padding: 0; line-height: 1.15; }}
.gs-hero p {{ margin: 0; opacity: .92; font-size: .98rem; max-width: 780px; }}
.gs-hero .gs-logo {{ background: white; border-radius: 16px; padding: 10px 16px; z-index: 1;
  box-shadow: 0 6px 18px rgba(0,0,0,.15); flex-shrink: 0; }}
.gs-hero .gs-logo img {{ height: auto; width: auto; max-height: 58px; max-width: 230px;
  object-fit: contain; display: block; }}

/* ---------- tarjetas de indicadores ---------- */
[data-testid="stMetric"] {{
  background: white; border-radius: 16px; padding: 16px 18px;
  border: 1px solid #E6ECE8; border-top: 5px solid {p};
  box-shadow: 0 4px 16px -8px rgba(28,36,33,.18);
  transition: transform .15s, box-shadow .15s;
}}
[data-testid="stMetric"]:hover {{ transform: translateY(-2px); box-shadow: 0 10px 24px -10px rgba(28,36,33,.28); }}
[data-testid="stColumn"]:nth-of-type(2) [data-testid="stMetric"] {{ border-top-color: {a}; }}
[data-testid="stColumn"]:nth-of-type(3) [data-testid="stMetric"] {{ border-top-color: #2D7DD2; }}
[data-testid="stColumn"]:nth-of-type(4) [data-testid="stMetric"] {{ border-top-color: #F2A541; }}
[data-testid="stColumn"]:nth-of-type(5) [data-testid="stMetric"] {{ border-top-color: #7E5BEF; }}
[data-testid="stMetricLabel"] p {{ font-size: .88rem; font-weight: 600; color: #5A6B63; }}
[data-testid="stMetricValue"] {{ font-size: 1.75rem; font-weight: 800; color: #1C2421; }}

/* ---------- gráficas, tablas y otros ---------- */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{
  background: white; border-radius: 16px; padding: 8px; border: 1px solid #E6ECE8;
  box-shadow: 0 4px 16px -10px rgba(28,36,33,.18);
}}
h2, h3 {{ color: #1C2421; font-weight: 700; }}
.stButton > button, .stDownloadButton > button {{ border-radius: 10px; font-weight: 600; }}
.stButton > button[kind="primary"], .stDownloadButton > button {{
  background: linear-gradient(120deg, {p}, {a}); border: none; color: white;
}}
[data-testid="stExpander"] {{ border-radius: 14px; border: 1px solid #E6ECE8; background: white; }}
[data-testid="stAlert"] {{ border-radius: 12px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ border-radius: 10px 10px 0 0; padding: 8px 16px; }}
</style>""", unsafe_allow_html=True)
    try:
        st.logo(str(ruta_logo()), size="large")
    except Exception:
        st.sidebar.image(str(ruta_logo()))
    return m


def encabezado(titulo: str, subtitulo: str = "", etiqueta: str | None = None) -> None:
    """Banner de sección con degradado de marca y el logo a la derecha."""
    m = leer_marca()
    etiqueta = etiqueta or m["empresa"]
    sub = f"<p>{subtitulo}</p>" if subtitulo else ""
    st.markdown(
        f'<div class="gs-hero"><div><div class="gs-eyebrow">{etiqueta}</div>'
        f'<h1>{titulo}</h1>{sub}</div>'
        f'<div class="gs-logo"><img src="{_logo_data_uri()}" alt="logo"/></div></div>',
        unsafe_allow_html=True)
