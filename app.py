# -*- coding: utf-8 -*-
"""GPT提链 - standalone local web app."""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from direct_extract import collect_accounts, direct_extract_common_options, run_direct_zero_extract

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
SETTINGS = DATA / "ui_settings.json"
DATA.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")

SETTING_KEYS = {
    "direct_proxy1",
    "direct_proxy2",
    "direct_max_attempts",
}


def load_settings() -> dict[str, str]:
    defaults = {key: "" for key in SETTING_KEYS}
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    if not isinstance(data, dict):
        return defaults
    return {key: str(data.get(key) or "") for key in SETTING_KEYS}


def save_settings(data: dict) -> dict[str, str]:
    current = load_settings()
    for key in SETTING_KEYS:
        if key in data:
            current[key] = str(data.get(key) or "")
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html", conditional=False, max_age=0)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "name": "GPT提链"})


@app.get("/api/register/ui-settings")
def ui_settings_get():
    return jsonify({"ok": True, "settings": load_settings()})


@app.post("/api/register/ui-settings")
def ui_settings_save():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"ok": True, "settings": save_settings(data)})


@app.post("/api/register/short-link")
def short_link():
    try:
        data = request.get_json(force=True, silent=True) or {}
        token_text = str(data.get("access_token") or data.get("session") or data.get("token") or "").strip()
        payload = run_direct_zero_extract(
            token_text,
            direct_extract_common_options(data),
            str(data.get("payment_email") or "").strip(),
        )
        return jsonify({"ok": True, **payload})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/register/short-link-batch")
def short_link_batch():
    try:
        data = request.get_json(force=True, silent=True) or {}
        token_text = str(data.get("access_token") or data.get("session") or data.get("token") or "").strip()
        accounts = collect_accounts(token_text, int(data.get("max_accounts") or 50))
        if not accounts:
            raise ValueError("请粘贴 Session JSON 或 accessToken")

        options = direct_extract_common_options(data)
        results: list[dict] = []
        success_count = 0
        for index, account in enumerate(accounts, start=1):
            email = str(account.get("email") or "").strip()
            try:
                payload = run_direct_zero_extract(
                    str(account.get("raw") or account.get("token") or ""),
                    options,
                    email,
                )
                payload.update({"ok": True, "index": index})
                results.append(payload)
                success_count += 1
            except Exception as exc:
                results.append({"ok": False, "index": index, "account_email": email, "error": str(exc)})

        body = {
            "ok": success_count > 0,
            "total": len(accounts),
            "success": success_count,
            "failed": len(accounts) - success_count,
            "results": results,
            "error": "" if success_count > 0 else "全部提链失败",
        }
        return jsonify(body), 200 if success_count > 0 else 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("GPT_LINK_PORT") or os.environ.get("PP_PORT") or 8801)
    print(f"GPT提链: http://127.0.0.1:{port}", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
