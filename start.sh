#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
  else
    python -m venv .venv
  fi
  .venv/bin/python -m pip install -r requirements.txt
fi

# Keep local traffic away from system proxy.
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

export GPT_LINK_PORT="${GPT_LINK_PORT:-8801}"

if command -v open >/dev/null 2>&1; then
  open "http://127.0.0.1:${GPT_LINK_PORT}" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:${GPT_LINK_PORT}" >/dev/null 2>&1 || true
fi

.venv/bin/python app.py
