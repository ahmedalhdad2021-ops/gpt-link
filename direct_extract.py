# -*- coding: utf-8 -*-
"""Direct Session/accessToken to ChatGPT checkout link extraction."""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Any

from opll_core import (
    currency_for_country,
    extract_access_token_from_session_text,
    generate_link,
    normalize_opll_country,
    normalize_proxy_url,
)
from token_util import is_chatgpt_access_token, parse_accounts

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def bool_option(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}


def split_nonempty_lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").replace("\r", "\n").split("\n") if line.strip()]


def normalize_pasted_proxy_text(value: str) -> str:
    text = str(value or "").replace("\r", "\n")
    chunks: list[str] = []
    host_re = re.compile(r"(?:https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}:\d+")
    for token in re.split(r"\s+", text):
        token = token.strip()
        if not token:
            continue
        starts = [match.start() for match in host_re.finditer(token)]
        if len(starts) <= 1:
            chunks.append(token)
            continue
        starts.append(len(token))
        for index, start in enumerate(starts[:-1]):
            part = token[start : starts[index + 1]].strip()
            if part:
                chunks.append(part)
    return "\n".join(chunks)


def normalize_dynamic_proxy_lines(value: str) -> list[str]:
    proxies: list[str] = []
    for line in split_nonempty_lines(normalize_pasted_proxy_text(value)):
        proxy = normalize_proxy_url(line)
        if proxy:
            proxies.append(proxy)
    return proxies


def extract_email_from_session_text(text: str) -> str:
    raw = str(text or "")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = None

    def walk(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("email", "mail", "username"):
                item = value.get(key)
                if isinstance(item, str) and EMAIL_RE.match(item.strip()):
                    return item.strip()
            for item in value.values():
                found = walk(item)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = walk(item)
                if found:
                    return found
        return ""

    found = walk(payload) if payload is not None else ""
    if found:
        return found

    token = extract_access_token_from_session_text(raw) or raw.strip()
    parts = token.split(".")
    if len(parts) >= 2:
        try:
            padded = parts[1] + ("=" * (-len(parts[1]) % 4))
            claims = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace"))
            found = walk(claims)
            if found:
                return found
        except Exception:
            pass
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", raw)
    return match.group(0) if match else ""


def link_result_view(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    short_url = str(result.get("internal_url") or result.get("chatgpt_short_url") or "").strip()
    external_url = str(
        result.get("pay_openai_url")
        or result.get("external_url")
        or result.get("long_url")
        or result.get("pay_url")
        or ""
    ).strip()
    amount = result.get("stripe_amount")
    if amount is None or str(amount) == "":
        amount = result.get("amount") or ""
    return {
        "short_url": short_url,
        "external_url": external_url,
        "final_url": short_url or external_url or str(result.get("stripe_hosted_url") or ""),
        "stripe_hosted_url": str(result.get("stripe_hosted_url") or ""),
        "amount": str(amount),
        "currency": result.get("currency") or "",
        "billing_country": result.get("billing_country") or "",
        "cs_id": result.get("cs_id") or "",
        "mode": result.get("mode") or "",
        "target_amount": str(result.get("target_amount") or ""),
        "amount_check": str(result.get("amount_check") or ""),
        "stripe_amount_source": str(result.get("stripe_amount_source") or ""),
        "raw": {
            k: v
            for k, v in result.items()
            if k
            in {
                "processor_entity",
                "payment_method_country",
                "proxy_exit_country",
                "used_country",
                "pay_openai_url",
                "internal_url",
                "chatgpt_short_url",
                "external_url",
                "long_url",
                "stripe_hosted_url",
                "target_amount",
                "amount_check",
                "stripe_amount_source",
            }
        },
    }


def direct_extract_common_options(data: dict[str, Any]) -> dict[str, Any]:
    country = normalize_opll_country(str(data.get("country") or "PH"))
    target_amount = str(data.get("target_amount") if data.get("target_amount") is not None else "0").strip()
    return {
        "country": country,
        "mode": str(data.get("mode") or "hosted").strip().lower() or "hosted",
        "plan_name": str(data.get("plan_name") or "chatgptplusplan").strip() or "chatgptplusplan",
        "currency": str(data.get("currency") or currency_for_country(country)).strip().upper(),
        "proxy1_pool": normalize_dynamic_proxy_lines(str(data.get("proxy1") or data.get("create_proxy") or "")),
        "proxy2_pool": normalize_dynamic_proxy_lines(str(data.get("proxy2") or data.get("followup_proxy") or "")),
        "approve_proxy_pool": normalize_dynamic_proxy_lines(str(data.get("approve_proxy") or "")),
        "max_attempts": max(1, min(int(data.get("max_attempts") or data.get("direct_max_attempts") or 20), 200)),
        "target_amount": target_amount or "0",
        "use_promo": bool_option(data.get("use_promo"), True),
        "promo_code": str(data.get("promo_code") or ""),
        "checkout_ui_mode": str(data.get("checkout_ui_mode") or "hosted"),
        "payment_locale": str(data.get("payment_locale") or "en"),
    }


def run_direct_zero_extract(token_text: str, options: dict[str, Any], payment_email: str = "") -> dict[str, Any]:
    access_token = extract_access_token_from_session_text(token_text) or str(token_text or "").strip()
    if not access_token:
        raise ValueError("请粘贴 Session JSON 或 accessToken")
    if not is_chatgpt_access_token(access_token):
        raise ValueError("输入内容不是有效的 ChatGPT accessToken / Session JSON")

    proxy1_pool = list(options.get("proxy1_pool") or [])
    proxy2_pool = list(options.get("proxy2_pool") or [])
    approve_proxy_pool = list(options.get("approve_proxy_pool") or [])
    max_attempts = int(options.get("max_attempts") or 20)
    target_amount = str(options.get("target_amount") or "0")
    payment_email = str(payment_email or "").strip() or extract_email_from_session_text(token_text)

    view: dict[str, Any] = {}
    errors: list[str] = []
    attempt_used = 0
    for attempt in range(1, max_attempts + 1):
        attempt_used = attempt
        proxy1 = proxy1_pool[(attempt - 1) % len(proxy1_pool)] if proxy1_pool else ""
        proxy2 = proxy2_pool[(attempt - 1) % len(proxy2_pool)] if proxy2_pool else proxy1
        approve_proxy = approve_proxy_pool[(attempt - 1) % len(approve_proxy_pool)] if approve_proxy_pool else proxy2
        try:
            result = generate_link(
                access_token=access_token,
                country=str(options.get("country") or "PH"),
                mode=str(options.get("mode") or "hosted"),
                currency=str(options.get("currency") or "PHP"),
                create_proxy=proxy1,
                followup_proxy=proxy2,
                approve_proxy=approve_proxy,
                target_amount=target_amount,
                auto_match_proxy_country=False,
                plan_name=str(options.get("plan_name") or "chatgptplusplan"),
                use_promo=bool(options.get("use_promo", True)),
                promo_code=str(options.get("promo_code") or ""),
                checkout_ui_mode=str(options.get("checkout_ui_mode") or "hosted"),
                payment_locale=str(options.get("payment_locale") or "en"),
                payment_email=payment_email,
            )
            view = link_result_view(result)
            if not view.get("final_url"):
                raise RuntimeError("提链成功返回中没有可用链接")
            if target_amount == "0" and not (view.get("amount") == "0" and view.get("amount_check") == "passed"):
                actual = view.get("amount") or "-"
                source = view.get("stripe_amount_source") or "-"
                raise RuntimeError(f"不是 0 链: 实际 {actual}, 来源 {source}")
            break
        except Exception as exc:
            errors.append(f"{attempt}/{max_attempts}: {str(exc)[:220]}")
            if attempt >= max_attempts:
                raise RuntimeError("直接提链 0 短链失败: " + " | ".join(errors[-5:]))
            time.sleep(0.4)

    return {
        "short_url": str(view.get("short_url") or "").strip(),
        "external_url": str(view.get("external_url") or "").strip(),
        "stripe_hosted_url": view.get("stripe_hosted_url") or "",
        "amount": view.get("amount") or "",
        "currency": view.get("currency") or str(options.get("currency") or "PHP"),
        "billing_country": view.get("billing_country") or str(options.get("country") or "PH"),
        "cs_id": view.get("cs_id") or "",
        "mode": view.get("mode") or str(options.get("mode") or "hosted"),
        "target_amount": view.get("target_amount") or target_amount,
        "amount_check": view.get("amount_check") or "",
        "stripe_amount_source": view.get("stripe_amount_source") or "",
        "attempt": attempt_used,
        "account_email": payment_email or "",
        "raw": view.get("raw") or {},
    }


def collect_accounts(token_text: str, max_accounts: int = 50) -> list[dict[str, str]]:
    accounts = parse_accounts(token_text)
    if not accounts:
        token = extract_access_token_from_session_text(token_text) or token_text
        if token:
            accounts = [{"token": token, "email": extract_email_from_session_text(token_text), "raw": token_text}]
    return accounts[: max(1, min(max_accounts, 200))]
