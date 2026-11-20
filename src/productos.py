"""Nombres genéricos de producto («Producto A», «Producto B»…).

Se usan mientras no haya un catálogo confiable de lo que vende Green, para no
presentar como reales nombres de producto que fueron supuestos.
"""
from __future__ import annotations

import string

import pandas as pd


def letras(n: int) -> list[str]:
    """A, B, …, Z, AA, AB, …"""
    out = []
    for i in range(n):
        s, k = "", i
        while True:
            s = string.ascii_uppercase[k % 26] + s
            k = k // 26 - 1
            if k < 0:
                break
        out.append(s)
    return out


def generizar(productos: pd.DataFrame, col_nombre: str = "nombre",
              col_categoria: str = "categoria") -> pd.DataFrame:
    """Reemplaza el nombre por «Producto X», ordenando por línea de negocio y nombre
    para que los productos de una misma línea queden con letras seguidas."""
    p = productos.copy()
    orden = p.sort_values([col_categoria, col_nombre]).index
    p.loc[orden, col_nombre] = [f"Producto {l}" for l in letras(len(orden))]
    return p
