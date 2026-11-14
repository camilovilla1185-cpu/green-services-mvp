#!/usr/bin/env bash
# Instala lo necesario la primera vez y abre el tablero en el navegador.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi
[ -f data/processed/metricas.json ] || python -m src.pipeline --demo
streamlit run app.py --server.headless false
