# -*- coding: utf-8 -*-
"""Token / Session 解析：输入文本 → accessToken + 展示元数据。"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from typing import Any

from opll_core import extract_access_token_from_session_text

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)

# session.account.planType / JWT chatgpt_plan_type
PLAN_LABELS = {
    "free": "Free 免费",
    "plus": "Plus",
    "team": "Team 团队",
    "pro": "Pro",
    "enterprise": "Enterprise",
    "edu": "Edu",
    "go": "Go",
}


def _b64url_json(part: str) -> dict[str, Any]:
    raw = part + "=" * (-len(part) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _jwt_payload(token: str) -> dict[str, Any]:
    text = str(token or "").strip()
    if text.count(".") < 2:
        return {}
    return _b64url_json(text.split(".")[1])


def _format_expires(value: Any) -> str:
    """统一成可读本地/UTC 时间字符串。"""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        ts = float(value)
        # ms vs s
        if ts > 1e12:
            ts /= 1000.0
        try:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return str(value)
    text = str(value).strip()
    if not text:
        return ""
    # ISO: 2026-10-22T15:37:39.347Z
    try:
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return text


def _plan_label(plan: str) -> str:
    key = str(plan or "").strip().lower()
    if not key:
        return ""
    return PLAN_LABELS.get(key, plan)


def is_chatgpt_access_token(token: str) -> bool:
    """只放行 ChatGPT / OpenAI API 账号 accessToken，排除 Cookie 网关 JWT。"""
    payload = _jwt_payload(token)
    if not payload:
        return False
    issuer = str(payload.get("iss") or "").strip().lower()
    if issuer == "edge-gateway":
        return False
    auth = payload.get("https://api.openai.com/auth")
    auth = auth if isinstance(auth, dict) else {}
    account_id = str(
        auth.get("chatgpt_account_id")
        or auth.get("account_id")
        or payload.get("chatgpt_account_id")
        or payload.get("account_id")
        or ""
    ).strip()
    user_id = str(
        auth.get("chatgpt_user_id")
        or auth.get("user_id")
        or payload.get("chatgpt_user_id")
        or payload.get("user_id")
        or ""
    ).strip()
    return bool((account_id or user_id) and payload.get("exp"))


def email_from_token(token: str) -> str:
    """从 JWT / 嵌套 JSON 尽量抠出邮箱。"""
    text = str(token or "").strip()
    if not text:
        return ""

    # JWT payload（含 OpenAI 自定义 claim）
    if text.count(".") >= 2 and not text.lstrip().startswith("{"):
        payload = _jwt_payload(text)
        for key in ("email", "preferred_username", "upn", "unique_name"):
            val = str(payload.get(key) or "").strip()
            if "@" in val:
                return val
        profile = payload.get("https://api.openai.com/profile")
        if isinstance(profile, dict):
            val = str(profile.get("email") or "").strip()
            if "@" in val:
                return val

    # session JSON
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        stack: list[Any] = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key in ("email", "user", "name"):
                    val = item.get(key)
                    if isinstance(val, str) and "@" in val:
                        return val.strip()
                    if isinstance(val, dict):
                        stack.append(val)
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)

    m = EMAIL_RE.search(text)
    return m.group(0) if m else ""


def _session_dict(raw_chunk: str) -> dict[str, Any] | None:
    text = str(raw_chunk or "").strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def enrich_account(token: str, email: str = "", raw_chunk: str = "") -> dict[str, str]:
    """
    从 session JSON / JWT 提取展示字段。
    返回含 token 的完整账号 dict（API 层再裁剪敏感字段）。
    """
    tok = str(token or "").strip()
    raw = str(raw_chunk or tok).strip()
    em = str(email or "").strip()
    name = ""
    plan = ""
    structure = ""
    expires = ""

    data = _session_dict(raw)
    if isinstance(data, dict):
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        account = data.get("account") if isinstance(data.get("account"), dict) else {}
        em = em or str(user.get("email") or "").strip()
        name = str(user.get("name") or "").strip()
        plan = str(account.get("planType") or account.get("plan") or "").strip()
        structure = str(account.get("structure") or "").strip()
        expires = _format_expires(data.get("expires"))

    payload = _jwt_payload(tok)
    if payload:
        profile = payload.get("https://api.openai.com/profile")
        auth = payload.get("https://api.openai.com/auth")
        if isinstance(profile, dict):
            em = em or str(profile.get("email") or "").strip()
            name = name or str(profile.get("name") or "").strip()
        if isinstance(auth, dict):
            plan = plan or str(auth.get("chatgpt_plan_type") or "").strip()
        for key in ("email", "preferred_username"):
            val = str(payload.get(key) or "").strip()
            if "@" in val:
                em = em or val
        if not expires and payload.get("exp") is not None:
            expires = _format_expires(payload.get("exp"))

    if not em:
        em = email_from_token(raw) or email_from_token(tok)

    return {
        "token": tok,
        "email": em,
        "name": name,
        "plan": plan,
        "plan_label": _plan_label(plan),
        "structure": structure,
        "expires": expires,
        "raw": raw,
    }


def _split_json_objects(text: str) -> list[str]:
    """按花括号深度切分多段粘贴的 session JSON。"""
    chunks: list[str] = []
    buf: list[str] = []
    depth = 0
    in_json = False
    for ch in text:
        if ch == "{":
            depth += 1
            in_json = True
        if in_json:
            buf.append(ch)
        if ch == "}":
            depth = max(0, depth - 1)
            if in_json and depth == 0:
                chunks.append("".join(buf).strip())
                buf = []
                in_json = False
    return chunks


def parse_accounts(raw: str) -> list[dict[str, str]]:
    """
    解析多账号输入。
    支持：
    - 多段 session JSON（含首尾粘连）
    - 每行一个 accessToken / session
    - 邮箱----token / 邮箱|token
    返回 [{token, email, name, plan, plan_label, structure, expires, raw}]
    """
    text = str(raw or "").strip()
    if not text:
        return []

    accounts: list[dict[str, str]] = []
    seen: set[str] = set()

    def push(token: str, email: str = "", raw_chunk: str = "") -> None:
        tok = str(token or "").strip()
        if not tok or tok in seen or not is_chatgpt_access_token(tok):
            return
        seen.add(tok)
        accounts.append(enrich_account(tok, email=email, raw_chunk=raw_chunk or tok))

    chunks = _split_json_objects(text)
    if not chunks:
        chunks = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]

    for chunk in chunks:
        email = ""
        body = chunk
        for sep in ("----", "|", "\t", ","):
            if sep in chunk and "@" in chunk.split(sep, 1)[0]:
                left, right = chunk.split(sep, 1)
                if "@" in left and len(right) > 20:
                    email = left.strip()
                    body = right.strip()
                    break
        tok = extract_access_token_from_session_text(body)
        if tok:
            push(tok, email or email_from_token(body), body)
        elif body.startswith("eyJ") and body.count(".") >= 2:
            push(body, email, body)

    return accounts


def account_public_view(account: dict[str, str]) -> dict[str, str]:
    """API 对外字段：不回传完整 token。"""
    tok = str(account.get("token") or "")
    preview = (tok[:24] + "…") if len(tok) > 24 else tok
    return {
        "email": str(account.get("email") or ""),
        "name": str(account.get("name") or ""),
        "plan": str(account.get("plan") or ""),
        "plan_label": str(account.get("plan_label") or _plan_label(str(account.get("plan") or ""))),
        "structure": str(account.get("structure") or ""),
        "expires": str(account.get("expires") or ""),
        "token_preview": preview,
    }