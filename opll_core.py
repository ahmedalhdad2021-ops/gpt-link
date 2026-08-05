# -*- coding: utf-8 -*-
"""PP 提链核心逻辑（从桌面巴西提链 OPLL 流程抽取）"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
import json
import random
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

import requests

try:
    from curl_cffi.requests import Session as CurlCffiSession  # type: ignore
except Exception:
    CurlCffiSession = None  # type: ignore

try:
    from curl_cffi import CurlOpt as _CurlOpt  # type: ignore
except Exception:
    _CurlOpt = None  # type: ignore


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)

_ACTIVE_CHECKOUT_OPTS: dict = {}
DEFAULT_STRIPE_PK = "pk_live_51HOrSwC6h1nxGoI3lTAgRjYVrz4dU3fVOabyCcKR3pbEJguCVAlqCxdxCUvoRh1XWwRacViovU3kLKvpkjh7IqkW00iXQsjo3n"
STRIPE_VERSION_FULL = "2025-03-31.basil; checkout_server_update_beta=v1; checkout_manual_approval_preview=v1"
DEFAULT_STRIPE_RUNTIME_VERSION = "6f8494a281"
PAY_LONG_LINK_TIMEOUT = 30

COUNTRY_CURRENCY = {
    "AT": "EUR", "AU": "AUD", "BE": "EUR", "BR": "BRL", "CA": "CAD", "CH": "CHF", "CZ": "CZK",
    "DE": "EUR", "DK": "DKK", "ES": "EUR", "FI": "EUR", "FR": "EUR", "GB": "GBP", "HK": "HKD",
    "ID": "IDR", "IE": "EUR", "IN": "INR", "IT": "EUR", "JP": "JPY", "KR": "KRW", "MX": "MXN",
    "MY": "MYR", "NL": "EUR", "NO": "NOK", "NZ": "NZD", "PH": "PHP", "PL": "PLN", "PT": "EUR",
    "SE": "SEK", "SG": "SGD", "TH": "THB", "TW": "TWD", "US": "USD", "VN": "VND",
}
OPENAI_SUPPORTED_COUNTRY_CODES = {
    "AX", "AL", "DZ", "AS", "AD", "AO", "AI", "AQ", "AG", "AR",
    "AM", "AW", "AU", "AT", "AZ", "BS", "BH", "BD", "BB", "BE",
    "BZ", "BJ", "BM", "BT", "BO", "BQ", "BA", "BW", "BV", "BR",
    "IO", "BN", "BG", "BF", "BI", "CV", "KH", "CM", "CA", "KY",
    "CF", "TD", "CL", "CX", "CC", "CO", "KM", "CG", "CK", "CR",
    "CI", "HR", "CW", "CY", "CZ", "DK", "DJ", "DM", "DO", "EC",
    "SV", "GQ", "ER", "EE", "SZ", "FK", "FO", "FJ", "FI", "FR",
    "GF", "PF", "TF", "GA", "GM", "GE", "DE", "GH", "GI", "GR",
    "GL", "GD", "GP", "GU", "GT", "GG", "GN", "GW", "GY", "HT",
    "HM", "VA", "HN", "HU", "IS", "IN", "ID", "IQ", "IE", "IM",
    "IL", "IT", "JM", "JP", "JE", "JO", "KZ", "KE", "KI", "KW",
    "KG", "LA", "LV", "LB", "LS", "LR", "LI", "LT", "LU", "MG",
    "MW", "MY", "MV", "ML", "MT", "MH", "MQ", "MR", "MU", "YT",
    "MX", "FM", "MD", "MC", "MN", "ME", "MS", "MA", "MZ", "MM",
    "NA", "NR", "NP", "NL", "NC", "NZ", "NI", "NE", "NG", "NU",
    "NF", "MK", "MP", "NO", "OM", "PK", "PW", "PS", "PA", "PG",
    "PE", "PH", "PN", "PL", "PT", "PR", "QA", "RE", "RO", "RW",
    "BL", "SH", "KN", "LC", "MF", "PM", "VC", "WS", "SM", "ST",
    "SN", "RS", "SC", "SL", "SG", "SX", "SK", "SI", "SB", "SO",
    "ZA", "GS", "KR", "SS", "ES", "LK", "SR", "SJ", "SE", "CH",
    "TW", "TZ", "TH", "TL", "TG", "TK", "TO", "TT", "TN", "TR",
    "TM", "TC", "TV", "UG", "UA", "AE", "GB", "UM", "US", "UY",
    "UZ", "VU", "VN", "WF", "EH", "ZM",
}
EUR_COUNTRIES = {
    "AD", "AT", "BE", "CY", "EE", "FI", "FR", "DE", "GR", "HR",
    "IE", "IT", "LV", "LT", "LU", "MT", "MC", "ME", "NL", "PT",
    "SM", "SK", "SI", "ES",
}
COUNTRY_CURRENCY.update({country: "EUR" for country in EUR_COUNTRIES if country not in COUNTRY_CURRENCY})
COUNTRY_CURRENCY.update({
    "AE": "AED", "AR": "ARS", "BH": "BHD", "BM": "BMD", "BO": "BOB", "BQ": "USD",
    "CL": "CLP", "CO": "COP", "GU": "USD", "IL": "ILS", "PR": "USD", "TR": "TRY",
    "UA": "UAH", "UM": "USD", "ZA": "ZAR",
})
COUNTRY_PHONE_PREFIX = {
    "AU": "+61", "CA": "+1", "DE": "+49", "GB": "+44", "IE": "+353", "JP": "+81",
    "NZ": "+64", "SG": "+65", "TH": "+66", "US": "+1",
    "AD": "+376", "AE": "+971", "AL": "+355", "AR": "+54", "AT": "+43", "BE": "+32",
    "BG": "+359", "BH": "+973", "BM": "+1", "BO": "+591", "BR": "+55", "CH": "+41",
    "CL": "+56", "CO": "+57", "CR": "+506", "CY": "+357", "CZ": "+420", "DK": "+45",
    "EE": "+372", "ES": "+34", "FI": "+358", "FR": "+33", "GI": "+350", "GR": "+30",
    "HK": "+852", "HU": "+36", "ID": "+62", "IL": "+972", "IN": "+91", "IS": "+354",
    "IT": "+39", "KR": "+82", "KZ": "+7", "LI": "+423", "LT": "+370", "LU": "+352",
    "LV": "+371", "MC": "+377", "MD": "+373", "ME": "+382", "MK": "+389", "MT": "+356",
    "MX": "+52", "MY": "+60", "NL": "+31", "NO": "+47", "PH": "+63", "PL": "+48",
    "PT": "+351", "QA": "+974", "RO": "+40", "RS": "+381", "SA": "+966", "SE": "+46",
    "SI": "+386", "SK": "+421", "SM": "+378", "TR": "+90", "TW": "+886", "UA": "+380",
    "UY": "+598", "VN": "+84", "ZA": "+27",
}
US_BILLING_NAMES = [("James", "Smith"), ("John", "Brown"), ("Michael", "Johnson"), ("Robert", "Miller"), ("David", "Davis"), ("William", "Wilson")]
US_BILLING_STREETS = [
    ("3110 Sunset Boulevard", "Los Angeles", "CA", "90026"),
    ("1200 Market Street", "San Francisco", "CA", "94102"),
    ("500 Main Street", "Austin", "TX", "78701"),
    ("88 Broadway", "New York", "NY", "10007"),
    ("1200 Peachtree St", "Atlanta", "GA", "30309"),
]
DE_BILLING_NAMES = [("Lukas", "Schneider"), ("Felix", "Muller"), ("Jonas", "Weber"), ("Leon", "Fischer"), ("Marie", "Wagner"), ("Laura", "Becker"), ("Maximilian", "Hoffmann"), ("Paul", "Schulz"), ("Emma", "Koch"), ("Hannah", "Bauer"), ("Sophie", "Richter"), ("Noah", "Klein")]
DE_BILLING_STREETS = [
    ("Friedrichstrasse 123", "Berlin", "BE", "10117"),
    ("Leopoldstrasse 50", "Munich", "BY", "80802"),
    ("Zeil 85", "Frankfurt am Main", "HE", "60313"),
    ("Konigsallee 60", "Dusseldorf", "NW", "40212"),
    ("Moenckebergstrasse 7", "Hamburg", "HH", "20095"),
    ("Hohenzollernring 72", "Cologne", "NW", "50672"),
    ("Kaiserstrasse 44", "Stuttgart", "BW", "70173"),
    ("Kaufingerstrasse 15", "Munich", "BY", "80331"),
    ("Georgstrasse 24", "Hanover", "NI", "30159"),
    ("Prager Strasse 9", "Dresden", "SN", "01069"),
    ("Schadowstrasse 36", "Dusseldorf", "NW", "40212"),
    ("Breite Strasse 18", "Bonn", "NW", "53111"),
]
GB_BILLING_NAMES = [("Oliver", "Smith"), ("George", "Taylor"), ("Harry", "Brown"), ("Noah", "Wilson"), ("Jack", "Davies"), ("Arthur", "Evans"), ("Olivia", "Johnson"), ("Amelia", "Roberts"), ("Isla", "Walker"), ("Ava", "Thompson"), ("Mia", "White"), ("Grace", "Hughes")]
GB_BILLING_STREETS = [
    ("221B Baker Street", "London", "England", "NW1 6XE"),
    ("10 Downing Street", "London", "England", "SW1A 2AA"),
    ("45 Deansgate", "Manchester", "England", "M3 2AY"),
    ("18 Park Row", "Leeds", "England", "LS1 5JA"),
    ("77 Queen Street", "Cardiff", "Wales", "CF10 2GR"),
    ("9 Princes Street", "Edinburgh", "Scotland", "EH2 2ER"),
    ("33 Broad Street", "Birmingham", "England", "B1 2HF"),
    ("14 Castle Street", "Liverpool", "England", "L2 0NE"),
    ("52 College Green", "Bristol", "England", "BS1 5SH"),
    ("6 Royal Avenue", "Belfast", "Northern Ireland", "BT1 1DA"),
]
AU_BILLING_NAMES = [("Jack", "Wilson"), ("Oliver", "Taylor"), ("Noah", "Brown"), ("Charlotte", "Smith"), ("Amelia", "Jones"), ("Isla", "Williams")]
AU_BILLING_STREETS = [
    ("120 Collins Street", "Melbourne", "Victoria", "3000"),
    ("88 George Street", "Sydney", "New South Wales", "2000"),
    ("45 Queen Street", "Brisbane", "Queensland", "4000"),
    ("22 King William Street", "Adelaide", "South Australia", "5000"),
    ("60 St Georges Terrace", "Perth", "Western Australia", "6000"),
    ("18 Elizabeth Street", "Hobart", "Tasmania", "7000"),
]
EXTRA_BILLING_NAMES = [("Alex", "Tan"), ("Daniel", "Lee"), ("Emma", "Wong"), ("Mia", "Chen"), ("Noah", "Martin"), ("Olivia", "Nguyen")]
EXTRA_BILLING_STREETS = {
    "TH": [("999 Rama I Road", "Bangkok", "Bangkok", "10330"), ("88 Sukhumvit Road", "Bangkok", "Bangkok", "10110"), ("45 Nimman Road", "Chiang Mai", "Chiang Mai", "50200")],
    "JP": [("1-1 Marunouchi", "Chiyoda-ku", "Tokyo", "100-0005"), ("2-2-1 Yaesu", "Chuo-ku", "Tokyo", "104-0028"), ("3-1 Umeda", "Osaka", "Osaka", "530-0001")],
    "SG": [("10 Anson Road", "Singapore", "Singapore", "079903"), ("1 Raffles Place", "Singapore", "Singapore", "048616"), ("80 Robinson Road", "Singapore", "Singapore", "068898")],
    "NZ": [("22 Queen Street", "Auckland", "Auckland", "1010"), ("50 Lambton Quay", "Wellington", "Wellington", "6011"), ("120 Hereford Street", "Christchurch", "Canterbury", "8011")],
    "CA": [("100 King Street West", "Toronto", "ON", "M5X 1A9"), ("555 West Hastings Street", "Vancouver", "BC", "V6B 4N6"), ("1250 Rene-Levesque Blvd", "Montreal", "QC", "H3B 4W8")],
    "IE": [("1 Grand Canal Square", "Dublin", "Dublin", "D02 P820"), ("10 South Mall", "Cork", "Cork", "T12 RD43"), ("5 Eyre Square", "Galway", "Galway", "H91 FPK2")],
    # VN 账单：MoMo 提链 / taxes 同步必须能生成真实越南地址
    "VN": [
        ("12 Nguyen Hue", "Ho Chi Minh City", "Ho Chi Minh", "700000"),
        ("25 Le Loi", "Ho Chi Minh City", "Ho Chi Minh", "710000"),
        ("48 Hang Bai", "Hanoi", "Hanoi", "100000"),
        ("7 Tran Phu", "Da Nang", "Da Nang", "550000"),
    ],
}
BILLING_PROFILE_CITY_BY_COUNTRY = {
    "AT": ["Vienna", "Graz", "Linz"], "BE": ["Brussels", "Antwerp", "Ghent"], "BR": ["Sao Paulo", "Rio de Janeiro", "Brasilia"],
    "CH": ["Zurich", "Geneva", "Basel"], "DK": ["Copenhagen", "Aarhus", "Odense"], "ES": ["Madrid", "Barcelona", "Valencia"],
    "FI": ["Helsinki", "Espoo", "Tampere"], "FR": ["Paris", "Lyon", "Marseille"], "ID": ["Jakarta", "Surabaya", "Bandung"],
    "IT": ["Rome", "Milan", "Turin"], "KR": ["Seoul", "Busan", "Incheon"], "MX": ["Mexico City", "Guadalajara", "Monterrey"],
    "NL": ["Amsterdam", "Rotterdam", "Utrecht"], "NO": ["Oslo", "Bergen", "Trondheim"], "PL": ["Warsaw", "Krakow", "Gdansk"],
    "PT": ["Lisbon", "Porto", "Coimbra"], "SE": ["Stockholm", "Gothenburg", "Malmo"], "TW": ["Taipei", "Taichung", "Kaohsiung"],
    "VN": ["Ho Chi Minh City", "Hanoi", "Da Nang", "Hai Phong", "Can Tho"],
}
POSTAL_PATTERN_BY_COUNTRY = {
    "AD": "AD###", "AR": "C####", "AU": "####", "AT": "####", "BE": "####", "BR": "#####-###",
    "CA": "A#A #A#", "CH": "####", "CL": "#######", "CZ": "### ##", "DE": "#####", "DK": "####",
    "ES": "#####", "FI": "#####", "FR": "#####", "GB": "AA# #AA", "IE": "A## A###", "ID": "#####",
    "IN": "######", "IT": "#####", "JP": "###-####", "KR": "#####", "MX": "#####", "NL": "#### AA",
    "NO": "####", "NZ": "####", "PL": "##-###", "PT": "####-###", "SE": "### ##", "SG": "######",
    "TH": "#####", "US": "#####", "VN": "######",
}
BILLING_STREET_POOL = ["Market Street", "Central Avenue", "Station Road", "Main Street", "High Street", "King Street"]
BILLING_PROFILE_BY_COUNTRY = {
    country: {
        "currency": COUNTRY_CURRENCY.get(country, "USD"),
        "phone_prefix": COUNTRY_PHONE_PREFIX.get(country, "+1"),
        "city_pool": BILLING_PROFILE_CITY_BY_COUNTRY.get(country, ["Capital City", "Central District", "Market Town"]),
        "postal_pattern": POSTAL_PATTERN_BY_COUNTRY.get(country, "#####"),
        "street_pool": BILLING_STREET_POOL,
    }
    for country in OPENAI_SUPPORTED_COUNTRY_CODES
}
LOCALE_MAP = {
    "de": ("de-DE", "de"), "en": ("en-US", "en"), "en-US": ("en-US", "en"), "es": ("es-ES", "es"),
    "fr": ("fr-FR", "fr"), "id": ("id-ID", "id"), "it": ("it-IT", "it"), "ja": ("ja-JP", "ja"),
    "ko": ("ko-KR", "ko"), "nl": ("nl-NL", "nl"), "pt-BR": ("pt-BR", "pt-BR"),
    "vi": ("vi-VN", "vi"), "vi-VN": ("vi-VN", "vi"),
    "zh-CN": ("zh-CN", "zh-CN"), "zh-TW": ("zh-TW", "zh-TW"),
}

# 支付页语言：与参考站选项对齐
PAYMENT_LOCALES = [
    {"id": "en", "label": "English"},
    {"id": "zh-CN", "label": "简体中文"},
    {"id": "zh-TW", "label": "繁体中文"},
    {"id": "ja", "label": "日本語"},
    {"id": "ko", "label": "한국어"},
    {"id": "nl", "label": "Nederlands"},
    {"id": "de", "label": "Deutsch"},
    {"id": "fr", "label": "Français"},
    {"id": "es", "label": "Español"},
    {"id": "id", "label": "Bahasa Indonesia"},
    {"id": "pt-BR", "label": "Português (BR)"},
]

class AmountMismatchError(RuntimeError):
    def __init__(self, target_amount: str, actual_amount: str, stripe_amount_source: str):
        self.target_amount = target_amount
        self.actual_amount = actual_amount
        self.stripe_amount_source = stripe_amount_source
        super().__init__(f"金额不匹配: 目标 {target_amount}, 实际 {actual_amount}")

class ProxyExitCheckError(RuntimeError):
    def __init__(self, message: str, status: str = "代理检测失败"):
        self.status = status
        super().__init__(message)


LINK_PROXY_LOG_STEPS = (
    ("create", "第一步"),
    ("followup", "后续"),
    ("approve", "Approve"),
)
LINK_PROXY_LOG_PADDING = {
    "第一步": "    ",
    "后续": "      ",
    "Approve": "   ",
}

class OpllStripeRequiresApproval(Exception):
    pass

class OpllChatgptApproveBlocked(Exception):
    pass


OPLL_APPROVE_BURST_RESULTS = {"blocked", "exception"}


REGION_PRESETS = [
    # PayPal 长链：默认美区，地区自选，不写死德国
    {"id": "us_paypal", "label": "PayPal 美国 US/USD", "country": "US", "currency": "USD", "mode": "paypal", "plan": "plus", "use_promo": True, "require_zero": False, "note": "默认：PayPal 长链，账单默认 US；代理自定义，不强制改写出口"},
    {"id": "de_paypal", "label": "PayPal 德国 DE/EUR", "country": "DE", "currency": "EUR", "mode": "paypal", "plan": "plus", "use_promo": True, "require_zero": False, "note": "可选德区账单；代理自定义，建议出口与账单一致"},
    {"id": "gb_paypal", "label": "PayPal 英国 GB/GBP", "country": "GB", "currency": "GBP", "mode": "paypal", "plan": "plus", "use_promo": True, "require_zero": False, "note": "可选英区 PayPal"},
    {"id": "jp_paypal", "label": "PayPal 日本 JP/JPY", "country": "JP", "currency": "JPY", "mode": "paypal", "plan": "plus", "use_promo": True, "require_zero": False, "note": "可选日区 PayPal"},
    {"id": "ie_paypal", "label": "PayPal 爱尔兰 IE/EUR", "country": "IE", "currency": "EUR", "mode": "paypal", "plan": "plus", "use_promo": True, "require_zero": False, "note": "欧元区备选"},
    {"id": "nl_paypal", "label": "PayPal 荷兰 NL/EUR", "country": "NL", "currency": "EUR", "mode": "paypal", "plan": "plus", "use_promo": True, "require_zero": False, "note": "欧元区备选"},
    {"id": "fr_paypal", "label": "PayPal 法国 FR/EUR", "country": "FR", "currency": "EUR", "mode": "paypal", "plan": "plus", "use_promo": True, "require_zero": False, "note": "欧元备选"},
    {"id": "us_hosted", "label": "Hosted 美国 US/USD", "country": "US", "currency": "USD", "mode": "hosted", "plan": "plus", "use_promo": True, "require_zero": False, "note": "美区 Hosted 稳链"},
    {"id": "gb_hosted", "label": "Hosted 英国 GB/GBP", "country": "GB", "currency": "GBP", "mode": "hosted", "plan": "plus", "use_promo": True, "require_zero": False, "note": "英镑区 Hosted"},
    {"id": "jp_hosted", "label": "Hosted 日本 JP/JPY", "country": "JP", "currency": "JPY", "mode": "hosted", "plan": "plus", "use_promo": True, "require_zero": False, "note": "日元区"},
    {"id": "sg_hosted", "label": "Hosted 新加坡 SG/SGD", "country": "SG", "currency": "SGD", "mode": "hosted", "plan": "plus", "use_promo": True, "require_zero": False, "note": "新币区"},
    {"id": "br_pix", "label": "PIX 巴西 BR/BRL", "country": "BR", "currency": "BRL", "mode": "pix", "plan": "plus", "use_promo": True, "require_zero": True, "note": "巴西 PIX：代理池 BR 出链 + Promo 刷新 0 元；提取复制码/二维码"},
    {"id": "id_gopay", "label": "GoPay 印尼 ID/IDR", "country": "ID", "currency": "IDR", "mode": "gopay", "plan": "plus", "use_promo": True, "require_zero": False, "note": "GoPay 专用"},
    {"id": "vn_momo", "label": "MoMo 越南 VN/VND", "country": "VN", "currency": "VND", "mode": "momo", "plan": "plus", "use_promo": True, "require_zero": True, "note": "越南 MoMo：VN 账单 + payment.momo.vn 支付链接 + 二维码"},
    {"id": "us_team_hosted", "label": "Team Hosted 美国", "country": "US", "currency": "USD", "mode": "hosted", "plan": "team", "use_promo": False, "require_zero": False, "note": "Team 套餐 Hosted"},
]


def _quote_proxy_auth(user: str, password: str = "") -> str:
    """对代理账号密码做一次 URL 编码；已编码的输入先 unquote，避免二次编码。"""
    u = quote(unquote(str(user or "")), safe="")
    if password is None or password == "":
        return u
    return f"{u}:{quote(unquote(str(password)), safe='')}"


def _normalize_proxy_scheme(scheme: str, default_scheme: str = "http") -> str:
    scheme = (scheme or default_scheme).strip().lower() or default_scheme
    if scheme in {"socks5h", "socks"}:
        return "socks5"
    if scheme == "https":
        # 代理网关几乎都是 HTTP CONNECT；https://user@host 会误走 TLS-to-proxy
        return "http"
    return scheme


def parse_proxy_line(value: str, default_scheme: str = "http") -> str:
    """把参考站常见的多格式代理行归一成 URL。

    支持：
    - http://user:pass@host:port / socks5://user:pass@host:port
    - host:port
    - host:port:user:pass（密码可含 @）
    - user:pass@host:port
    - host:port@user:pass
    """
    text = str(value or "").strip()
    if not text:
        return ""

    scheme = default_scheme
    rest = text
    if "://" in text:
        scheme, rest = text.split("://", 1)
        scheme = _normalize_proxy_scheme(scheme, default_scheme)
        rest = rest.strip()
        # 已是标准 URL：只做 scheme 规范化 + 账号密码一次编码（幂等）
        try:
            parsed = urlsplit(f"{scheme}://{rest}")
            host = parsed.hostname or ""
            # urlsplit 会把 hostname 小写；保留用户原始 host 大小写（DNS 不敏感，但部分代理签名敏感）
            if parsed.port is not None and "@" in rest:
                host_part = rest.rsplit("@", 1)[-1]
                host_raw = host_part.split(":", 1)[0].strip()
                if host_raw:
                    host = host_raw
            elif parsed.port is not None and ":" in rest and "@" not in rest:
                host_raw = rest.split(":", 1)[0].strip()
                if host_raw:
                    host = host_raw
            port = parsed.port
            user = unquote(parsed.username or "")
            password = unquote(parsed.password or "")
            if host and port:
                auth = _quote_proxy_auth(user, password) if (user or password) else ""
                netloc = f"{auth}@{host}:{port}" if auth else f"{host}:{port}"
                path = parsed.path or ""
                query = f"?{parsed.query}" if parsed.query else ""
                return f"{scheme}://{netloc}{path}{query}"
            if host and not port and not user:
                return f"{scheme}://{host}{parsed.path or ''}"
        except Exception:
            pass
    else:
        scheme = _normalize_proxy_scheme(default_scheme, default_scheme)

    # host:port:user:pass —— 优先于 @ 分支，密码里可以带 @
    m = re.match(r"^([^:@\s/]+):(\d+):([^:\s/]+):(.*)$", rest)
    if m:
        host, port, user, password = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{scheme}://{_quote_proxy_auth(user, password)}@{host}:{port}"

    if "@" in rest:
        left, right = rest.rsplit("@", 1)
        left = left.strip()
        right = right.strip()
        left_parts = left.split(":")
        right_parts = right.split(":")
        # host:port@user:pass
        if (
            len(left_parts) >= 2
            and left_parts[1].isdigit()
            and len(right_parts) >= 2
            and not right_parts[0].isdigit()
        ):
            host, port = left_parts[0], left_parts[1]
            user, password = right_parts[0], ":".join(right_parts[1:])
            return f"{scheme}://{_quote_proxy_auth(user, password)}@{host}:{port}"
        # user:pass@host:port
        port_token = right_parts[1].split("/")[0] if len(right_parts) >= 2 else ""
        if len(right_parts) >= 2 and port_token.isdigit():
            user = left_parts[0]
            password = ":".join(left_parts[1:]) if len(left_parts) > 1 else ""
            host = right_parts[0]
            port = port_token
            auth = _quote_proxy_auth(user, password) if (user or password) else ""
            return f"{scheme}://{auth}@{host}:{port}" if auth else f"{scheme}://{host}:{port}"
        return f"{scheme}://{left}@{right}"

    parts = rest.split(":")
    # host:port
    if len(parts) == 2 and parts[1].isdigit():
        return f"{scheme}://{parts[0]}:{parts[1]}"
    return f"{scheme}://{rest}"


def normalize_proxy_url(value: str, default_scheme: str = "http") -> str:
    """兼容旧调用：单行代理规范化。

    多行文本只取第一行（create/follow 场景）。approve 多 sid 池请用
    ``normalize_proxy_pool_text``，避免整池被压成一条无效 URL。
    """
    lines = split_proxy_pool(value)
    if not lines:
        return parse_proxy_line(value, default_scheme=default_scheme)
    return parse_proxy_line(lines[0], default_scheme=default_scheme)


def normalize_proxy_pool_text(value: str, default_scheme: str = "http") -> str:
    """多行代理池：逐行规范化，保留换行（给 approve 换线用）。"""
    norms: list[str] = []
    for line in split_proxy_pool(value):
        item = parse_proxy_line(line, default_scheme=default_scheme)
        if item:
            norms.append(item)
    if norms:
        return "\n".join(norms)
    # 非换行分隔的单条
    return parse_proxy_line(value, default_scheme=default_scheme)


def random_proxy_sid(length: int = 10) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(alphabet) for _ in range(length))


def randomize_proxy_sid(proxy_url: str) -> str:
    """住宅代理常见 sid/session 字段：每次请求换会话出口。"""
    text = str(proxy_url or "").strip()
    if not text:
        return ""
    sid = random_proxy_sid()
    try:
        parsed = urlsplit(text)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if any(key.lower() == "sid" for key, _value in query_pairs):
            query = urlencode([(key, sid if key.lower() == "sid" else value) for key, value in query_pairs])
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
        netloc = parsed.netloc
        if "@" in netloc:
            userinfo, host = netloc.rsplit("@", 1)
            new_userinfo = re.sub(
                r"(?i)(sid[-_=])([^-:@;&/?]+)",
                lambda m: f"{m.group(1)}{sid}",
                userinfo,
                count=1,
            )
            if new_userinfo != userinfo:
                return urlunsplit((parsed.scheme, f"{new_userinfo}@{host}", parsed.path, parsed.query, parsed.fragment))
        new_text = re.sub(r"(?i)(sid[-_=])([^-:@;&/?]+)", lambda m: f"{m.group(1)}{sid}", text, count=1)
        return new_text
    except Exception:
        return text


def is_proxy_retryable_error(error: Exception | str) -> bool:
    text = str(error or "").lower()
    needles = (
        "connection closed abruptly",
        "connection aborted",
        "connection reset",
        "connection was reset",
        "recv failure",
        "remote end closed",
        "远程主机强迫关闭",
        "curl: (56)",
        "curl: (35)",
        "curl: (7)",
        "curl: (28)",
        "tls connect",
        "wrong_version_number",
        "ssl routines",
        "timed out",
        "timeout",
        "failed to connect",
        "failed to perform",
        "proxyerror",
        "tunnel connection failed",
        "max retries exceeded",
        "cannot connect to proxy",
        "proxy authentication",
        "http 407",
        "http 403",
        "http 408",
        "response 408",
        "connect tunnel",
        "tunnel failed",
        "forbidden ip",
        "代理请求失败",
        "跟随 stripe 跳转时代理失败",
        "跟随 stripe 跳转未到达 paypal",
        "仍停在 stripe 中间跳转页",
        # approve blocked 可换 sid/线路再试
        "chatgpt approve",
        "approve retryable result",
        "approve 连续失败",
        "'blocked'",
        "\"blocked\"",
    )
    return any(item in text for item in needles)



def split_proxy_pool(text: str) -> list[str]:
    lines = []
    for line in str(text or "").replace("\r", "\n").split("\n"):
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        lines.append(item)
    return lines


def pick_proxy_from_pool(text: str, default_scheme: str = "http") -> tuple[str, int, int]:
    lines = split_proxy_pool(text)
    if not lines:
        return "", 0, 0
    import random as _random
    idx = _random.randrange(len(lines))
    return parse_proxy_line(lines[idx], default_scheme=default_scheme), idx + 1, len(lines)


def extract_access_token_from_session_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if raw.startswith("Bearer "):
        return raw.split(None, 1)[1].strip()
    # JWT-looking
    if raw.count(".") >= 2 and len(raw) > 80 and " " not in raw and not raw.startswith("{"):
        return raw
    try:
        data = json.loads(raw)
    except Exception:
        data = None
    if isinstance(data, dict):
        for key in ("accessToken", "access_token", "token"):
            val = str(data.get(key) or "").strip()
            if val:
                return val
        # nested
        stack = list(data.values())
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key in ("accessToken", "access_token", "token"):
                    val = str(item.get(key) or "").strip()
                    if val:
                        return val
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    m = re.search(r'"(?:accessToken|access_token|token)"\s*:\s*"([^"]+)"', raw)
    if m:
        return m.group(1).strip()
    # last resort: first JWT-like token in text
    m = re.search(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", raw)
    return m.group(0) if m else ""


def decode_jwt_payload(token: str) -> dict:
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return {}
    try:
        payload = parts[1].replace("-", "+").replace("_", "/")
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.b64decode(payload).decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_nested_record(payload: dict, key: str) -> dict:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def currency_for_country(country: str) -> str:
    return COUNTRY_CURRENCY.get(normalize_opll_country(country), "USD")


def normalize_opll_country(country: str) -> str:
    code = str(country or "").strip().upper()
    if len(code) != 2:
        return "US"
    return code


def locale_parts(locale: str = "en") -> tuple[str, str]:
    key = str(locale or "en").strip() or "en"
    if key in LOCALE_MAP:
        return LOCALE_MAP[key]
    low = key.lower()
    if low in LOCALE_MAP:
        return LOCALE_MAP[low]
    return LOCALE_MAP.get("en", ("en-US", "en"))


def opll_extract_processor_entity(data) -> str:
    if not isinstance(data, dict):
        return ""
    direct = data.get("processor_entity") or data.get("processorEntity")
    if direct:
        return str(direct).strip()
    for key in ("checkout_session", "session", "checkout", "data"):
        nested = data.get(key)
        if isinstance(nested, dict):
            found = opll_extract_processor_entity(nested)
            if found:
                return found
    return ""


def _checkout_opts_kwargs() -> dict:
    opts = globals().get("_ACTIVE_CHECKOUT_OPTS") or {}
    if not isinstance(opts, dict):
        return {}
    plan_name = str(opts.get("plan_name") or "chatgptplusplan").strip() or "chatgptplusplan"
    low = plan_name.lower()
    if low in {"team", "chatgpt_team", "chatgptteam"}:
        plan_name = "chatgptteamplan"
    elif low in {"plus", "chatgptplus", "chatgpt_plus", "chatgptplusplan"}:
        plan_name = "chatgptplusplan"
    ui_mode = str(opts.get("checkout_ui_mode") or "").strip()
    return {
        "plan_name": plan_name,
        "use_promo": bool(opts.get("use_promo", True)),
        "promo_campaign_id": str(opts.get("promo_campaign_id") or "plus-1-month-free"),
        "promo_code": str(opts.get("promo_code") or "").strip(),
        "team_seats": int(opts.get("team_seats") or 5),
        "workspace_name": str(opts.get("workspace_name") or ""),
        "checkout_ui_mode": ui_mode,
        "entry_point": str(opts.get("entry_point") or "all_plans_pricing_modal"),
    }


def opll_create_checkout_with_opts(access_token: str, country: str, currency: str, proxy_url: str = "", **overrides) -> dict:
    kwargs = _checkout_opts_kwargs()
    kwargs.update({k: v for k, v in overrides.items() if v is not None and v != ""})
    if not kwargs.get("checkout_ui_mode"):
        # 对齐 oaipay 模式2：PayPal/Hosted 默认 hosted；PIX/iDEAL 才用 custom
        kwargs["checkout_ui_mode"] = "hosted"
    return opll_create_checkout(
        access_token=access_token,
        country=country,
        currency=currency,
        proxy_url=proxy_url,
        plan_name=kwargs.get("plan_name", "chatgptplusplan"),
        checkout_ui_mode=kwargs.get("checkout_ui_mode", "hosted"),
        use_promo=bool(kwargs.get("use_promo", True)),
        promo_campaign_id=str(kwargs.get("promo_campaign_id") or "plus-1-month-free"),
        promo_code=str(kwargs.get("promo_code") or ""),
        team_seats=int(kwargs.get("team_seats") or 5),
        workspace_name=str(kwargs.get("workspace_name") or ""),
        entry_point=str(kwargs.get("entry_point") or "all_plans_pricing_modal"),
    )


def _is_iso2_country(value: str) -> bool:
    text = str(value or "").strip().upper()
    return len(text) == 2 and text.isalpha()


def _looks_like_ip(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    # ipv4 simple
    parts = text.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return True
    return ":" in text and any(ch.isdigit() for ch in text)


def extract_region_hint_from_proxy(proxy_url: str = "") -> str:
    text = str(proxy_url or "")
    # region-BR / region=BR / -BR- / country-BR
    m = re.search(r"(?i)(?:region|country|cc)[-_=]([a-z]{2})\b", text)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?i)(?:^|[^\w])([a-z]{2})-(?:sid|session|city|st)\b", text)
    if m and m.group(1).upper() in OPENAI_SUPPORTED_COUNTRY_CODES:
        return m.group(1).upper()
    return ""


def _parse_geo_payload(data: dict) -> tuple[str, str]:
    if not isinstance(data, dict):
        return "", ""
    country = ""
    for key in ("countryCode", "country_code", "country", "cc", "loc"):
        val = str(data.get(key) or "").strip()
        if not val:
            continue
        if key == "loc" and "," in val:
            # ipinfo sometimes loc=lat,lon
            continue
        if len(val) == 2 and val.isalpha():
            country = val.upper()
            break
        # full country name mapping not needed; try countryCode first
    if not country:
        val = str(data.get("country") or "").strip()
        if len(val) == 2 and val.isalpha():
            country = val.upper()
    ip = ""
    for key in ("query", "ip", "ipAddress", "origin"):
        val = str(data.get(key) or "").strip()
        if _looks_like_ip(val):
            ip = val
            break
    return country, ip


def _parse_cf_trace(text: str) -> tuple[str, str]:
    country, ip = "", ""
    for line in str(text or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k == "loc" and len(v) == 2:
            country = v.upper()
        elif k == "ip" and _looks_like_ip(v):
            ip = v
    return country, ip

def opll_extract_stripe_publishable_key(data) -> str:
    if isinstance(data, str):
        match = re.search(r"pk_live_[A-Za-z0-9]+", data)
        return match.group(0) if match else ""
    if isinstance(data, dict):
        for key in ("stripe_publishable_key", "publishable_key", "publishableKey", "stripePublishableKey", "key"):
            found = opll_extract_stripe_publishable_key(data.get(key))
            if found:
                return found
        for item in data.values():
            found = opll_extract_stripe_publishable_key(item)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = opll_extract_stripe_publishable_key(item)
            if found:
                return found
    return ""

def opll_processor_entity_for_country(country: str, processor_entity: str = "") -> str:
    entity = str(processor_entity or "").strip()
    if entity:
        return entity
    return "openai_llc" if str(country or "").upper() == "US" else "openai_ie"

def opll_chatgpt_success_return_url(cs_id: str, country: str, processor_entity: str = "") -> str:
    entity = opll_processor_entity_for_country(country, processor_entity)
    return f"https://chatgpt.com/checkout/verify?stripe_session_id={cs_id}&processor_entity={entity}&plan_type=plus"

def opll_to_openai_pay_url(stripe_hosted_url: str) -> str:
    url = str(stripe_hosted_url or "").strip()
    if not url:
        return ""
    if url.startswith("https://checkout.stripe.com"):
        return "https://pay.openai.com" + url[len("https://checkout.stripe.com"):]
    parsed = urlsplit(url)
    if parsed.netloc.lower() == "checkout.stripe.com":
        return urlunsplit((parsed.scheme or "https", "pay.openai.com", parsed.path, parsed.query, parsed.fragment))
    return url

def opll_stripe_checkout_long_url(cs_id: str, country: str, processor_entity: str = "") -> str:
    return (
        f"https://checkout.stripe.com/c/pay/{cs_id}"
        f"?returned_from_redirect=true&ui_mode=custom&return_url="
        f"{quote(opll_chatgpt_success_return_url(cs_id, country, processor_entity), safe='')}"
    )

def opll_stripe_confirm_return_url(cs_id: str, checkout: dict, stripe_hosted_url: str) -> str:
    hosted_url = opll_to_openai_pay_url(stripe_hosted_url) or opll_stripe_checkout_long_url(
        cs_id,
        checkout["billing_country"],
        checkout.get("processor_entity", ""),
    )
    if "pay.openai.com/" in hosted_url or "checkout.stripe.com/" in hosted_url:
        parsed = urlsplit(hosted_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault(
            "success_return_url",
            opll_chatgpt_success_return_url(
                cs_id,
                checkout["billing_country"],
                checkout.get("processor_entity", ""),
            ),
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return hosted_url

# 本机常见前置（Clash 混合口等）。SOCKS 必须优先于 HTTP：
# Clash mixed 7890 上 HTTP PRE_PROXY 常只出 Clash 节点 IP（假成功），
# socks5h PRE_PROXY 才能真正 CONNECT 到 arxLabs 住宅出口。
_DEFAULT_LOCAL_PRE_PROXIES = (
    "socks5h://127.0.0.1:7890",
    "socks5://127.0.0.1:7890",
    "socks5h://127.0.0.1:7891",
    "socks5h://127.0.0.1:10808",
    "http://127.0.0.1:7890",
    "http://127.0.0.1:7891",
    "http://127.0.0.1:10809",
    "http://127.0.0.1:10808",
)
# proxy host:port -> pre_proxy URL；"" 表示直连可用；None 表示尚未探测
_PRE_PROXY_ROUTE_CACHE: dict[str, str] = {}
_LOCAL_PRE_PROXY_ENABLED: ContextVar[bool] = ContextVar("opll_local_pre_proxy_enabled", default=True)


@contextmanager
def opll_local_pre_proxy(enabled: bool = True):
    """Temporarily control automatic local PRE_PROXY routing for the current flow."""
    token = _LOCAL_PRE_PROXY_ENABLED.set(bool(enabled))
    try:
        yield
    finally:
        _LOCAL_PRE_PROXY_ENABLED.reset(token)


def opll_local_pre_proxy_enabled() -> bool:
    try:
        return bool(_LOCAL_PRE_PROXY_ENABLED.get())
    except Exception:
        return True


def _normalize_pre_proxy(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        return f"http://{text}"
    return text


def list_pre_proxy_candidates(explicit: str | None = None) -> list[str]:
    """前置代理候选：显式 > 环境变量 > 本机已监听端口（SOCKS 优先）。"""
    import os
    import socket

    out: list[str] = []

    def add(raw: str) -> None:
        url = _normalize_pre_proxy(raw)
        if url and url not in out:
            out.append(url)

    if explicit:
        add(explicit)
    env_one = str(os.getenv("OPLL_PRE_PROXY") or os.getenv("PAYPAL_PRE_PROXY") or "").strip()
    if env_one:
        add(env_one)
    env_pool = str(os.getenv("OPLL_PRE_PROXY_POOL") or os.getenv("PAYPAL_PRE_PROXY_POOL") or "").strip()
    for item in env_pool.replace(",", "\n").splitlines():
        item = item.strip()
        if item and not item.startswith("#"):
            add(item)

    for cand in _DEFAULT_LOCAL_PRE_PROXIES:
        try:
            parsed = urlsplit(cand)
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or 0)
            if not port:
                continue
            sock = socket.create_connection((host, port), timeout=0.35)
            sock.close()
            add(cand)
        except Exception:
            continue
    # 同端口：socks* 排到 http 前面，避免假成功
    def sort_key(url: str) -> tuple[int, str]:
        low = url.lower()
        if low.startswith("socks"):
            return (0, url)
        if low.startswith("http"):
            return (1, url)
        return (2, url)

    return sorted(out, key=sort_key)


def _proxy_route_cache_key(proxy_url: str) -> str:
    raw = normalize_proxy_url(proxy_url)
    if not raw:
        return ""
    try:
        p = urlsplit(raw)
        return f"{(p.hostname or '').lower()}:{p.port or 0}"
    except Exception:
        return raw


def _curl_session_with_pre(pre_proxy: str = ""):
    """创建带可选 PRE_PROXY 的 curl session；失败返回 None。"""
    if CurlCffiSession is None:
        return None
    pre = _normalize_pre_proxy(pre_proxy)
    curl_options = {}
    if pre and _CurlOpt is not None:
        curl_options[_CurlOpt.PRE_PROXY] = pre
    for impersonate in ("chrome131", "chrome"):
        try:
            session = CurlCffiSession(impersonate=impersonate, curl_options=curl_options or None)
            if hasattr(session, "trust_env"):
                session.trust_env = False
            return session
        except Exception:
            continue
    try:
        session = CurlCffiSession(curl_options=curl_options or None)
        if hasattr(session, "trust_env"):
            session.trust_env = False
        return session
    except Exception:
        return None


def _probe_public_exit_ip(proxy_url: str = "", pre_proxy: str = "", timeout: float = 8.0) -> str:
    """探测出口 IP；用于识别「前置假成功」（链路上仍是 Clash 节点）。"""
    session = _curl_session_with_pre(pre_proxy)
    if session is None:
        return ""
    use = str(proxy_url or "").strip()
    if use.startswith("socks5h://"):
        use = "socks5://" + use[len("socks5h://") :]
    if use:
        session.proxies = {"http": use, "https": use}
    endpoints = (
        "http://ip-api.com/json/?fields=status,query,countryCode",
        "https://api.ipify.org?format=json",
        "http://icanhazip.com",
    )
    for url in endpoints:
        try:
            resp = session.get(url, timeout=timeout)
            if int(getattr(resp, "status_code", 0) or 0) >= 400:
                continue
            text = (getattr(resp, "text", None) or "").strip()
            if not text:
                continue
            if text.startswith("{"):
                try:
                    data = resp.json() or {}
                except Exception:
                    data = {}
                ip = str(data.get("query") or data.get("ip") or "").strip()
                if _looks_like_ip(ip):
                    return ip
            else:
                ip = text.split()[0]
                if _looks_like_ip(ip):
                    return ip
        except Exception:
            continue
    return ""


def resolve_pre_proxy_for(proxy_url: str = "", *, force: bool = False) -> str:
    """为住宅代理选前置：直连通则空串；否则试本机 7890 等。

    关键：Clash mixed 口上 HTTP PRE_PROXY 可能只出 Clash 节点（与纯 7890 同 IP），
    必须再验出口 IP，优先 SOCKS 前置以真正落到 arxLabs 住宅。
    """
    raw = normalize_proxy_url(proxy_url)
    if not raw:
        return ""
    if not force and not opll_local_pre_proxy_enabled():
        return ""
    key = _proxy_route_cache_key(raw)
    if not force and key in _PRE_PROXY_ROUTE_CACHE:
        return _PRE_PROXY_ROUTE_CACHE[key]

    import os

    forced = str(os.getenv("OPLL_PRE_PROXY") or os.getenv("PAYPAL_PRE_PROXY") or "").strip()
    if forced:
        pre = _normalize_pre_proxy(forced)
        _PRE_PROXY_ROUTE_CACHE[key] = pre
        return pre

    if CurlCffiSession is None or _CurlOpt is None:
        _PRE_PROXY_ROUTE_CACHE[key] = ""
        return ""

    candidates = proxy_url_candidates(raw) or [raw]
    pre_list: list[str | None] = [None]
    for item in list_pre_proxy_candidates():
        pre_list.append(item)

    # 纯前置出口缓存：用于识别假链式（chain IP == 纯 Clash IP）
    pure_pre_ip: dict[str, str] = {}
    region_hint = extract_region_hint_from_proxy(raw)

    def accept_route(pre: str | None, cand: str) -> bool:
        use = cand
        if use.startswith("socks5h://"):
            use = "socks5://" + use[len("socks5h://") :]
        session = _curl_session_with_pre(pre or "")
        if session is None:
            return False
        session.proxies = {"http": use, "https": use}
        try:
            resp = session.get("https://api.ipify.org?format=json", timeout=10)
        except Exception:
            try:
                resp = session.get(
                    "http://ip-api.com/json/?fields=status,query,countryCode",
                    timeout=10,
                )
            except Exception:
                return False
        body = (getattr(resp, "text", None) or "")[:220].lower()
        code = int(getattr(resp, "status_code", 0) or 0)
        if code in {403, 407} and (
            "forbidden ip" in body or "not supported" in body or "proxy-authenticate" in body
        ):
            return False
        if code >= 400 and code not in {401, 403, 404, 429}:
            # 4xx 业务码可视为隧道通；连接层失败已在 except
            if code >= 500:
                return False
        # 无前置：直连住宅成功即可
        if not pre:
            return code < 500
        # 有前置：必须证明出口不是「纯前置」自己的 IP
        chain_ip = ""
        try:
            data = resp.json() if resp.content else {}
            if isinstance(data, dict):
                chain_ip = str(data.get("ip") or data.get("query") or "").strip()
        except Exception:
            chain_ip = ""
        if not chain_ip or not _looks_like_ip(chain_ip):
            chain_ip = _probe_public_exit_ip(use, pre, timeout=8)
        if not chain_ip:
            # 隧道通但拿不到 IP：SOCKS 前置仍可接受；HTTP 前置风险高，继续试
            return str(pre).lower().startswith("socks")
        if pre not in pure_pre_ip:
            pure_pre_ip[pre] = _probe_public_exit_ip("", pre, timeout=6)
        pure_ip = pure_pre_ip.get(pre) or ""
        if pure_ip and chain_ip == pure_ip:
            # 假链式：流量没进住宅代理
            return False
        # 可选：账号 region 与出口一致时优先（不强制，上面已排除假链）
        if region_hint and len(region_hint) == 2:
            # 轻量再取 country（失败不否决）
            try:
                geo = session.get(
                    "http://ip-api.com/json/?fields=status,countryCode,query",
                    timeout=6,
                )
                g = geo.json() if geo.content else {}
                cc = str((g or {}).get("countryCode") or "").upper()
                if cc and cc != region_hint.upper() and not str(pre).lower().startswith("socks"):
                    return False
            except Exception:
                pass
        return True

    for pre in pre_list:
        for cand in candidates:
            try:
                if accept_route(pre, cand):
                    chosen = pre or ""
                    _PRE_PROXY_ROUTE_CACHE[key] = chosen
                    return chosen
            except Exception:
                continue

    # 全失败：优先返回已监听的 SOCKS 前置，避免 HTTP 假成功
    local = list_pre_proxy_candidates()
    chosen = ""
    for item in local:
        if item.lower().startswith("socks"):
            chosen = item
            break
    if not chosen and local:
        chosen = local[0]
    _PRE_PROXY_ROUTE_CACHE[key] = chosen
    return chosen


def opll_new_http_session(engine: str = "auto", pre_proxy: str = "") -> requests.Session:
    """engine: auto|curl|plain。auto 优先 curl_cffi（浏览器指纹），失败路径可强制 plain。

    pre_proxy：本地前置（Clash 7890），仅 curl_cffi 支持（CURLOPT_PRE_PROXY）。
    """
    prefer = str(engine or "auto").strip().lower()
    pre = _normalize_pre_proxy(pre_proxy)
    # 有前置时必须 curl；plain requests 无法 PRE_PROXY
    if pre:
        prefer = "curl"
    session = None
    if prefer in {"auto", "curl"} and CurlCffiSession is not None:
        curl_options = {}
        if pre and _CurlOpt is not None:
            curl_options[_CurlOpt.PRE_PROXY] = pre
        # chrome131 对部分住宅代理更稳；chrome136 作次选
        for impersonate in ("chrome131", "chrome136", "chrome124", "chrome"):
            try:
                session = CurlCffiSession(  # type: ignore[assignment]
                    impersonate=impersonate,
                    curl_options=curl_options or None,
                )
                break
            except Exception:
                session = None
        if session is None and prefer == "curl":
            try:
                session = CurlCffiSession(curl_options=curl_options or None)  # type: ignore[assignment]
            except Exception:
                session = None
    if session is None:
        session = requests.Session()
    if hasattr(session, "trust_env"):
        session.trust_env = False
    # 供日志/调试读取
    try:
        session._opll_pre_proxy = pre  # type: ignore[attr-defined]
    except Exception:
        pass
    return session


def _apply_proxy_to_session(session, proxy_url: str = "", pre_proxy: str = "") -> None:
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return
    use = proxy_url
    # curl_cffi 对 socks5h 支持一般
    if use.startswith("socks5h://") and CurlCffiSession is not None and session.__class__.__name__.lower().find("curl") >= 0:
        use = "socks5://" + use[len("socks5h://") :]
    session.proxies.update({"http": use, "https": use})
    # 若 session 创建时未带 pre_proxy，无法在 plain requests 上补；仅记录
    pre = _normalize_pre_proxy(pre_proxy)
    if pre:
        try:
            session._opll_pre_proxy = pre  # type: ignore[attr-defined]
        except Exception:
            pass


def request_with_proxy_fallback(
    method: str,
    url: str,
    *,
    proxy_url: str = "",
    headers: dict | None = None,
    timeout: float | int = PAY_LONG_LINK_TIMEOUT,
    json_body=None,
    data=None,
    params=None,
    base_headers: dict | None = None,
    pre_proxy: str | None = None,
) -> requests.Response:
    """经代理发请求：浏览器指纹优先，普通 requests 作为降级；拒 IP 时自动试本机前置。"""
    method = str(method or "GET").strip().upper()
    candidates = proxy_url_candidates(proxy_url) if proxy_url else [""]
    if not candidates:
        candidates = [""]

    # 前置：显式 > 自动解析（arxLabs forbidden ip 场景）
    allow_local_pre_proxy = opll_local_pre_proxy_enabled()
    if pre_proxy is None:
        resolved_pre = resolve_pre_proxy_for(proxy_url) if (proxy_url and allow_local_pre_proxy) else ""
    else:
        resolved_pre = _normalize_pre_proxy(pre_proxy or "")

    pre_list: list[str] = [""]
    if resolved_pre:
        # 解析结果优先；若解析说要用前置，仍先短试直连会浪费，直接前置
        pre_list = [resolved_pre]
    elif proxy_url and allow_local_pre_proxy:
        # 尚未缓存/未知：先直连，再本机前置
        pre_list = [""] + list_pre_proxy_candidates()

    last_exc: Exception | None = None
    last_response = None
    errors: list[str] = []

    for pre in pre_list:
        # 有前置只能 curl；无前置 curl→plain
        if pre:
            engines = ("curl",) if CurlCffiSession is not None else ("plain",)
        elif proxy_url and CurlCffiSession is not None:
            engines = ("curl", "plain")
        elif CurlCffiSession is not None:
            engines = ("curl", "plain")
        else:
            engines = ("plain",)

        for engine in engines:
            for cand in candidates:
                use_cand = cand
                if engine == "curl" and use_cand.startswith("socks5h://"):
                    use_cand = "socks5://" + use_cand[len("socks5h://") :]
                session = opll_new_http_session(engine=engine, pre_proxy=pre)
                if base_headers:
                    session.headers.update(base_headers)
                _apply_proxy_to_session(session, use_cand, pre_proxy=pre)
                try:
                    resp = session.request(
                        method,
                        url,
                        headers=headers or {},
                        timeout=timeout,
                        json=json_body,
                        data=data,
                        params=params,
                    )
                    body_low = (resp.text or "")[:240].lower()
                    # 供应商拒客户端 IP：换前置，不要当业务 403 返回
                    if proxy_url and (
                        "forbidden ip" in body_low
                        or ("not supported" in body_low and "ip=" in body_low)
                    ):
                        last_response = resp
                        errors.append(f"{engine}|pre={pre or 'direct'}|{use_cand}: forbidden-ip body")
                        continue
                    if proxy_url and resp.status_code in {403, 407, 408, 429, 502, 503, 504}:
                        last_response = resp
                        errors.append(f"{engine}|pre={pre or 'direct'}|{use_cand}: HTTP {resp.status_code}")
                        continue
                    # 成功：缓存路由
                    if proxy_url:
                        key = _proxy_route_cache_key(proxy_url)
                        if key:
                            _PRE_PROXY_ROUTE_CACHE[key] = pre or ""
                    return resp
                except Exception as exc:
                    last_exc = exc
                    label = f"{engine}|pre={pre or 'direct'}|{use_cand or 'direct'}"
                    errors.append(f"{label}: {type(exc).__name__}: {str(exc)[:180]}")
                    continue

    if last_response is not None:
        return last_response
    detail = " | ".join(errors[-8:]) if errors else str(last_exc or "unknown")
    route_hint = "本机前置7890" if allow_local_pre_proxy else "未使用本机前置"
    raise RuntimeError(
        f"代理请求失败（已尝试 curl/requests、多协议、{route_hint}）: {detail}"
    ) from last_exc


def opll_build_chatgpt_session(access_token: str, proxy_url: str = "", locale: str = "", engine: str = "auto") -> requests.Session:
    token = extract_access_token_from_session_text(access_token) or str(access_token or "").strip()
    if not token:
        raise RuntimeError("当前账号没有 Access Token，请先注册并获取 Session 信息")
    # 同一 token 固定 device_id，避免每次提链像换设备（开源 pix-core 同款）
    device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, token))
    locale_norm = str(locale or "").strip()
    if not locale_norm:
        # 巴西/越南：按代理 region 靠拢语言指纹
        region = extract_region_hint_from_proxy(proxy_url)
        if region == "BR":
            locale_norm = "pt-BR"
        elif region == "VN":
            locale_norm = "vi-VN"
        elif region == "ID":
            locale_norm = "id-ID"
        else:
            locale_norm = "en-US"
    low = locale_norm.lower()
    if low.startswith("pt"):
        lang_primary = "pt-BR,pt;q=0.9,en;q=0.8"
        oai_language = "pt-BR"
    elif low.startswith("vi"):
        lang_primary = "vi-VN,vi;q=0.9,en;q=0.8"
        oai_language = "vi-VN"
    elif low.startswith("id"):
        lang_primary = "id-ID,id;q=0.9,en;q=0.8"
        oai_language = "id-ID"
    else:
        lang_primary = "en-US,en;q=0.9"
        oai_language = "en-US"
    pre = resolve_pre_proxy_for(proxy_url) if (proxy_url and opll_local_pre_proxy_enabled()) else ""
    # 有前置必须 curl
    use_engine = "curl" if pre else engine
    session = opll_new_http_session(engine=use_engine, pre_proxy=pre)
    session.headers.update({
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": lang_primary,
        "Authorization": f"Bearer {token}",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "Content-Type": "application/json",
        "oai-device-id": device_id,
        "oai-language": oai_language,
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "Cookie": f"oai-did={device_id}",
    })
    if proxy_url:
        _apply_proxy_to_session(session, proxy_url, pre_proxy=pre)
    return session

def opll_is_non_retryable_link_error(exc: Exception | str) -> bool:
    text = str(exc or "").lower()
    non_retryable_markers = (
        "billing country must match request country",
        "confirm_error_reason=payment_method_types_mismatch",
        "token_invalidated",
        "authentication token has been invalidated",
        # 账号/会话本身不可用，换代理也无意义
        "当前账号没有 access token",
        "authentication token",
        # 商户会话未开 MoMo：换 sid 无意义
        "当前 checkout 不支持 momo",
        "商户侧未启用 momo",
        "不支持的账单资料地区",
    )
    return any(marker in text for marker in non_retryable_markers)


def opll_create_checkout(
    access_token: str,
    country: str,
    currency: str,
    proxy_url: str = "",
    plan_name: str = "chatgptplusplan",
    checkout_ui_mode: str = "hosted",
    use_promo: bool = True,
    promo_campaign_id: str = "plus-1-month-free",
    promo_code: str = "",
    team_seats: int = 5,
    workspace_name: str = "",
    entry_point: str = "all_plans_pricing_modal",
    locale: str = "",
) -> dict:
    country = normalize_opll_country(country)
    currency = str(currency or currency_for_country(country)).upper()
    plan_name = str(plan_name or "chatgptplusplan").strip()
    checkout_ui_mode = str(checkout_ui_mode or "hosted").strip() or "hosted"
    if not locale and country == "BR":
        locale = "pt-BR"
    elif not locale and country == "VN":
        locale = "vi-VN"
    elif not locale and country == "ID":
        locale = "id-ID"
    token = extract_access_token_from_session_text(access_token) or str(access_token or "").strip()
    if not token:
        raise RuntimeError("当前账号没有 Access Token，请先注册并获取 Session 信息")
    device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, token))
    is_br = country == "BR" or str(locale).lower().startswith("pt")
    is_vn = country == "VN" or str(locale).lower().startswith("vi")
    is_id = country == "ID" or str(locale).lower().startswith("id")
    if is_br:
        accept_language = "pt-BR,pt;q=0.9,en;q=0.8"
        oai_language = "pt-BR"
    elif is_vn:
        accept_language = "vi-VN,vi;q=0.9,en;q=0.8"
        oai_language = "vi-VN"
    elif is_id:
        accept_language = "id-ID,id;q=0.9,en;q=0.8"
        oai_language = "id-ID"
    else:
        accept_language = "en-US,en;q=0.9"
        oai_language = "en-US"
    body = {
        "entry_point": entry_point or "all_plans_pricing_modal",
        "plan_name": plan_name,
        "billing_details": {"country": country, "currency": currency},
        "checkout_ui_mode": checkout_ui_mode,
    }
    if use_promo and promo_campaign_id:
        body["promo_campaign"] = {
            "promo_campaign_id": promo_campaign_id,
            "is_coupon_from_query_param": bool(promo_code),
        }
    if promo_code:
        body["promo_code"] = str(promo_code).strip()
    if plan_name in {"chatgptteamplan", "team", "chatgpt_team"}:
        body["plan_name"] = "chatgptteamplan"
        body["team_plan_data"] = {
            "workspace_name": str(workspace_name or f"workspace-{uuid.uuid4().hex[:8]}"),
            "price_interval": "month",
            "seat_quantity": max(2, int(team_seats or 5)),
        }
    referer = "https://chatgpt.com/"
    if use_promo and promo_campaign_id:
        referer = f"https://chatgpt.com/?promo_campaign={promo_campaign_id}#pricing"
    # 经代理时：curl_cffi 失败自动降级 plain requests，并轮换 http/socks 候选
    response = request_with_proxy_fallback(
        "POST",
        "https://chatgpt.com/backend-api/payments/checkout",
        proxy_url=proxy_url,
        json_body=body,
        headers={
            "Referer": referer,
            "x-openai-target-path": "/backend-api/payments/checkout",
            "x-openai-target-route": "/backend-api/payments/checkout",
        },
        timeout=PAY_LONG_LINK_TIMEOUT,
        base_headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": accept_language,
            "Authorization": f"Bearer {token}",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
            "Content-Type": "application/json",
            "oai-device-id": device_id,
            "oai-language": oai_language,
            "Cookie": f"oai-did={device_id}",
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(f"checkout create failed: HTTP {response.status_code} {response.text[:500]}")
    data = response.json() or {}
    cs_id = str(data.get("checkout_session_id") or data.get("session_id") or data.get("id") or "").strip()
    is_stripe_checkout = cs_id.startswith("cs_")
    is_openai_checkout = cs_id.startswith("oaics_")
    if not cs_id or not (is_stripe_checkout or (is_openai_checkout and checkout_ui_mode == "hosted")):
        raise RuntimeError(f"checkout response missing cs_id: {str(data)[:500]}")
    return {
        "cs_id": cs_id,
        "processor_entity": opll_extract_processor_entity(data),
        "stripe_publishable_key": opll_extract_stripe_publishable_key(data),
        "billing_country": country,
        "currency": currency,
        "plan_name": body["plan_name"],
        "checkout_ui_mode": checkout_ui_mode,
    }

def opll_stripe_key_for_checkout(checkout: dict | None = None) -> str:
    return str((checkout or {}).get("stripe_publishable_key") or "").strip() or DEFAULT_STRIPE_PK

def opll_stripe_init(cs_id: str, country: str, currency: str, proxy_url: str = "", payment_locale: str = "en", stripe: requests.Session | None = None, ctx: dict | None = None, checkout: dict | None = None) -> dict:
    browser_locale, elements_locale = locale_parts(payment_locale)
    stripe_pk = opll_stripe_key_for_checkout(checkout)
    # 无外部 session 时走统一构建（含本机前置 7890）
    stripe_session = stripe or opll_build_stripe_session(proxy_url, engine="plain")
    # 时区按 locale/账单国靠拢，避免本地钱包被按 CN 判定
    tz = "Asia/Shanghai"
    loc = str(payment_locale or "").lower()
    cc = str(country or (checkout or {}).get("billing_country") or "").upper()
    if loc.startswith("vi") or cc == "VN":
        tz = "Asia/Ho_Chi_Minh"
    elif loc.startswith("pt") or cc == "BR":
        tz = "America/Sao_Paulo"
    elif loc.startswith("id") or cc == "ID":
        tz = "Asia/Jakarta"
    response = stripe_session.post(
        f"https://api.stripe.com/v1/payment_pages/{cs_id}/init",
        data={
            "browser_locale": browser_locale,
            "browser_timezone": tz,
            "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
            "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
            "elements_session_client[elements_init_source]": "custom_checkout",
            "elements_session_client[referrer_host]": "chatgpt.com",
            "elements_session_client[stripe_js_id]": str((ctx or {}).get("stripe_js_id") or uuid.uuid4()),
            "elements_session_client[locale]": elements_locale,
            "elements_session_client[is_aggregation_expected]": "false",
            "elements_options_client[saved_payment_method][enable_save]": "never",
            "elements_options_client[saved_payment_method][enable_redisplay]": "never",
            "key": stripe_pk,
            "_stripe_version": STRIPE_VERSION_FULL,
        },
        timeout=PAY_LONG_LINK_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"stripe init failed: HTTP {response.status_code} {response.text[:500]}")
    return response.json() or {}

def opll_build_stripe_session(proxy_url: str = "", engine: str = "auto") -> requests.Session:
    pre = resolve_pre_proxy_for(proxy_url) if proxy_url else ""
    # 有前置必须 curl（PRE_PROXY）；无前置时尊重 engine（Stripe 常 plain）
    use_engine = "curl" if pre else engine
    session = opll_new_http_session(engine=use_engine, pre_proxy=pre)
    accept_lang = "pt-BR,pt;q=0.9,en;q=0.8" if extract_region_hint_from_proxy(proxy_url) == "BR" else "en-US,en;q=0.9"
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": accept_lang})
    if proxy_url:
        _apply_proxy_to_session(session, proxy_url, pre_proxy=pre)
    return session

def opll_stripe_context(init_payload: dict, payment_locale: str = "en", ctx: dict | None = None) -> dict:
    _browser_locale, elements_locale = locale_parts(payment_locale)
    base = ctx or {}
    return {
        "stripe_js_id": str(base.get("stripe_js_id") or uuid.uuid4()),
        "elements_session_id": str(base.get("elements_session_id") or f"elements_session_{uuid.uuid4().hex[:11]}"),
        "elements_session_config_id": str(init_payload.get("config_id") or base.get("elements_session_config_id") or uuid.uuid4()),
        "config_id": str(init_payload.get("config_id") or ""),
        "init_checksum": str(init_payload.get("init_checksum") or ""),
        "checkout_amount": str(opll_expected_amount(init_payload)),
        "currency": str(init_payload.get("currency") or "").lower(),
        "locale": elements_locale,
        "runtime_version": str(base.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION),
    }

def opll_expected_amount(init_payload: dict) -> str:
    return opll_stripe_amount_info(init_payload)[0]

def opll_stripe_amount_info(init_payload) -> tuple[str, str]:
    if not isinstance(init_payload, dict):
        return "0", "missing_payload"
    total_summary = init_payload.get("total_summary") if isinstance(init_payload, dict) else None
    if isinstance(total_summary, dict) and total_summary.get("due") is not None:
        return str(total_summary.get("due")), "total_summary.due"
    invoice = init_payload.get("invoice") if isinstance(init_payload, dict) else None
    if isinstance(invoice, dict) and invoice.get("amount_due") is not None:
        return str(invoice.get("amount_due")), "invoice.amount_due"
    line_items = init_payload.get("line_items") if isinstance(init_payload, dict) else None
    if isinstance(line_items, list):
        total = 0
        found = False
        for item in line_items:
            if isinstance(item, dict) and item.get("amount") is not None:
                try:
                    total += int(item.get("amount") or 0)
                    found = True
                except Exception:
                    pass
        if found:
            return str(total), "line_items.amount"
    return "0", "fallback_zero"


class AmountMismatchError(RuntimeError):
    def __init__(self, target_amount: str, actual_amount: str, stripe_amount_source: str):
        self.target_amount = target_amount
        self.actual_amount = actual_amount
        self.stripe_amount_source = stripe_amount_source
        super().__init__(f"金额不匹配: 目标 {target_amount}, 实际 {actual_amount}")


class ProxyExitCheckError(RuntimeError):
    def __init__(self, message: str, status: str = "代理检测失败"):
        self.status = status
        super().__init__(message)


LINK_PROXY_LOG_STEPS = (
    ("create", "第一步"),
    ("followup", "后续"),
    ("approve", "Approve"),
)
LINK_PROXY_LOG_PADDING = {
    "第一步": "    ",
    "后续": "      ",
    "Approve": "   ",
}

def _format_aligned_proxy_log(label: str, proxy_label: str) -> str:
    label = str(label or "").strip()
    proxy_text = str(proxy_label or "").strip() or "直连"
    return f"代理[{label}]{LINK_PROXY_LOG_PADDING.get(label, ' ')}\t: {proxy_text}"

def _format_aligned_exit_log(label: str, proxy_exit: str) -> str:
    label = str(label or "").strip()
    exit_text = str(proxy_exit or "").strip() or "未记录"
    return f"出口[{label}]{LINK_PROXY_LOG_PADDING.get(label, ' ')}\t: {exit_text}"

def _log_link_proxy_group(log_func, create_proxy, followup_proxy, approve_proxy, action_text: str = "") -> None:
    prefix = f"{str(action_text).strip()}，" if str(action_text or "").strip() else ""
    for label, proxy in (
        ("第一步", create_proxy),
        ("后续", followup_proxy),
        ("Approve", approve_proxy),
    ):
        proxy_label = getattr(proxy, "label", str(proxy or ""))
        log_func(f"{prefix}{_format_aligned_proxy_log(label, proxy_label)}")

def _proxy_exit_failed_text(proxy_exit: str) -> bool:
    return str(proxy_exit or "").strip().startswith("检测失败")

def _detect_link_proxy_exits_concurrently(detect_proxy_exit, log_func, create_proxy_url: str, followup_proxy_url: str, approve_proxy_url: str, require_japan: bool, proxy_exit_is_japan, cached_exits: dict[str, str] | None = None) -> dict[str, str]:
    proxy_urls = {
        "create": create_proxy_url,
        "followup": followup_proxy_url,
        "approve": approve_proxy_url,
    }
    cached_exits = cached_exits or {}
    exits: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="proxy-exit-check") as executor:
        futures = {
            key: executor.submit(detect_proxy_exit, proxy_urls.get(key, ""))
            for key, _label in LINK_PROXY_LOG_STEPS
            if key not in cached_exits
        }
        for key, _label in LINK_PROXY_LOG_STEPS:
            if key in cached_exits:
                exits[key] = cached_exits[key]
            else:
                try:
                    exits[key] = futures[key].result()
                except Exception as exc:
                    exits[key] = f"检测失败: {exc}"

    for key, label in LINK_PROXY_LOG_STEPS:
        log_func(_format_aligned_exit_log(label, exits.get(key, "")))

    for key, label in LINK_PROXY_LOG_STEPS:
        proxy_exit = exits.get(key, "")
        if _proxy_exit_failed_text(proxy_exit):
            raise ProxyExitCheckError(f"{label}代理出口检测失败，已放弃当前代理组: {proxy_exit}", "代理检测失败")

    if require_japan and not proxy_exit_is_japan(exits.get("create", "")):
        raise ProxyExitCheckError(f"第一步代理出口不是日本，已放弃当前代理组: {exits.get('create', '')}", "代理非日本")
    return exits

def opll_apply_amount_check(result: dict, target_amount: str = "") -> dict:
    target = str(target_amount).strip()
    actual = str(result.get("stripe_amount") or "").strip()
    source = str(result.get("stripe_amount_source") or "").strip()
    result["target_amount"] = target
    if not target:
        result["amount_check"] = "skipped"
        return result
    if actual != target:
        result["amount_check"] = "failed"
        raise AmountMismatchError(target, actual, source)
    result["amount_check"] = "passed"
    return result

def opll_random_postal_code(pattern: str) -> str:
    result = []
    for char in str(pattern or "#####"):
        if char == "#":
            result.append(str(random.randint(0, 9)))
        elif char == "A":
            result.append(chr(random.randint(ord("A"), ord("Z"))))
        else:
            result.append(char)
    return "".join(result)

def opll_billing_for_country(country: str, payment_email: str = "") -> dict:
    country = normalize_opll_country(country)
    if country == "DE":
        first, last = random.choice(DE_BILLING_NAMES)
        line1, city, state, postal = random.choice(DE_BILLING_STREETS)
    elif country == "GB":
        first, last = random.choice(GB_BILLING_NAMES)
        line1, city, state, postal = random.choice(GB_BILLING_STREETS)
    elif country == "AU":
        first, last = random.choice(AU_BILLING_NAMES)
        line1, city, state, postal = random.choice(AU_BILLING_STREETS)
    elif country == "US":
        first, last = random.choice(US_BILLING_NAMES)
        line1, city, state, postal = random.choice(US_BILLING_STREETS)
    elif country in EXTRA_BILLING_STREETS:
        first, last = random.choice(EXTRA_BILLING_NAMES)
        line1, city, state, postal = random.choice(EXTRA_BILLING_STREETS[country])
    elif country in OPENAI_SUPPORTED_COUNTRY_CODES:
        profile = BILLING_PROFILE_BY_COUNTRY[country]
        first, last = random.choice(EXTRA_BILLING_NAMES)
        line1 = f"{random.randint(10, 999)} {random.choice(profile['street_pool'])}"
        city = random.choice(profile["city_pool"])
        state = country
        postal = opll_random_postal_code(str(profile.get("postal_pattern") or "#####"))
    else:
        raise RuntimeError(f"不支持的账单资料地区: {country}")
    suffix = random.randint(1000, 9999)
    phone_prefix = str(BILLING_PROFILE_BY_COUNTRY.get(country, {}).get("phone_prefix") or COUNTRY_PHONE_PREFIX.get(country, "+1"))
    billing = {
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}{suffix}@example.com",
        "phone": f"{phone_prefix}{random.randint(100000000, 999999999)}",
        "country": country,
        "line1": line1,
        "city": city,
        "state": state,
        "postal_code": postal,
    }
    email = str(payment_email or "").strip()
    if "@" in email:
        billing["email"] = email
    return billing

def opll_random_jp_billing() -> dict:
    suffix = random.randint(1000, 9999)
    first = random.choice(["Haruto", "Yuto", "Sota", "Ren", "Yui", "Hina", "Aoi", "Sakura"])
    last = random.choice(["Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto"])
    street, city, state, postal = random.choice([
        ("1-1 Marunouchi", "Chiyoda-ku", "Tokyo", "100-0005"),
        ("2-8-1 Nishi-Shinjuku", "Shinjuku-ku", "Tokyo", "160-0023"),
        ("1-1 Umeda", "Kita-ku Osaka", "Osaka", "530-0001"),
        ("3-1 Minatomirai", "Nishi-ku Yokohama", "Kanagawa", "220-0012"),
    ])
    return {"name": f"{first} {last}", "email": f"{first.lower()}.{last.lower()}{suffix}@example.com", "country": "JP", "line1": street, "city": city, "state": state, "postal_code": postal}

def opll_stripe_create_paypal_method(stripe: requests.Session, cs_id: str, ctx: dict, billing: dict, stripe_pk: str = "", payment_method_type: str = "paypal") -> str:
    runtime_version = str(ctx.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION)
    payment_method_type = str(payment_method_type or "paypal").strip().lower()
    body = {
        "billing_details[name]": billing.get("name") or "John Doe",
        "billing_details[email]": billing.get("email") or "buyer@example.com",
        "billing_details[phone]": billing.get("phone") or "",
        "billing_details[address][country]": billing.get("country") or "US",
        "billing_details[address][line1]": billing.get("line1") or "3110 Sunset Boulevard",
        "billing_details[address][city]": billing.get("city") or "Los Angeles",
        "billing_details[address][postal_code]": billing.get("postal_code") or "90026",
        # 本地钱包（PIX/MoMo/GoPay）不要塞 CA 这种美国州
        "billing_details[address][state]": (
            billing.get("state")
            or (
                ""
                if str(payment_method_type).lower()
                in {"pix", "momo", "momo_wallet", "momo_vn", "momowallet", "gopay"}
                else "CA"
            )
        ),
        **({"billing_details[tax_id]": billing.get("tax_id")} if billing.get("tax_id") else {}),
        "type": payment_method_type,
        "payment_user_agent": f"stripe.js/{runtime_version}; stripe-js-v3/{runtime_version}; payment-element; deferred-intent",
        "referrer": "https://chatgpt.com",
        "time_on_page": str(random.randint(25000, 55000)),
        "client_attribution_metadata[checkout_session_id]": cs_id,
        "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
        "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
        "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
        "client_attribution_metadata[elements_session_config_id]": ctx["elements_session_config_id"],
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "2021",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "automatic",
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
        "key": stripe_pk or DEFAULT_STRIPE_PK,
        "_stripe_version": STRIPE_VERSION_FULL,
    }
    response = stripe.post("https://api.stripe.com/v1/payment_methods", data=body, timeout=PAY_LONG_LINK_TIMEOUT)
    if response.status_code >= 400:
        raise RuntimeError(f"stripe payment_methods failed: HTTP {response.status_code} {response.text[:500]}")
    pm_id = str((response.json() or {}).get("id") or "")
    if not pm_id.startswith("pm_"):
        raise RuntimeError(f"stripe payment_methods bad response: {response.text[:300]}")
    return pm_id

def opll_short_error(detail: str, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(detail or "")).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."

def opll_stripe_error_summary(prefix: str, response) -> str:
    try:
        payload = response.json() or {}
    except Exception:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        error = {}
    extra_fields = error.get("extra_fields") if isinstance(error.get("extra_fields"), dict) else {}
    parts = []
    for label, value in (
        ("code", error.get("code")),
        ("decline_code", error.get("decline_code")),
        ("type", error.get("type")),
        ("message", error.get("message")),
        ("payment_method_type", extra_fields.get("payment_method_type")),
        ("confirm_error_reason", extra_fields.get("confirm_error_reason")),
        ("confirm_error_code", extra_fields.get("confirm_error_code")),
        ("confirm_error_message", extra_fields.get("confirm_error_message")),
    ):
        if value is not None and value != "":
            parts.append(f"{label}={opll_short_error(str(value), 180)}")
    if parts:
        return f"{prefix}: " + ", ".join(parts)
    return f"{prefix}: {opll_short_error(response.text, 500)}"

def opll_is_external_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)

def opll_is_paypal_url(value: str) -> bool:
    host = (urlsplit(value).netloc or "").lower()
    return host == "paypal.com" or host.endswith(".paypal.com") or host == "paypalobjects.com" or host.endswith(".paypalobjects.com")

def opll_is_paypal_ba_approve_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    if not (host == "paypal.com" or host.endswith(".paypal.com")):
        return False
    path = parsed.path.rstrip("/").lower()
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return path == "/agreements/approve" and bool(str(query.get("ba_token") or "").strip())

def opll_is_paypal_success_url(value: str) -> bool:
    """仅 BA approve / 明确带 ba_token 的 PayPal 链算成功。

    pm-redirects.stripe.com 只是中间跳转，不能当最终 long_url。
    """
    if opll_is_paypal_ba_approve_url(value):
        return True
    try:
        parsed = urlsplit(value)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if host == "paypal.com" or host.endswith(".paypal.com"):
        q = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if str(q.get("ba_token") or "").strip():
            return True
    return False


def opll_is_stripe_pm_redirect_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme.lower() == "https" and host == "pm-redirects.stripe.com"

def opll_is_ignored_resource_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    ignored_hosts = {
        "stripe-camo.global.ssl.fastly.net",
        "files.stripe.com",
        "q.stripe.com",
        "js.stripe.com",
        "m.stripe.network",
        "d1wqzb5bdbcre6.cloudfront.net",
    }
    ignored_host_suffixes = (".cloudfront.net", ".stripe.com", ".stripe.network", ".paypalobjects.com")
    ignored_suffixes = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".ico", ".css", ".js", ".woff", ".woff2")
    if host in ignored_hosts or any(host.endswith(item) for item in ignored_host_suffixes):
        # checkout.stripe.com / api.stripe.com 不是资源图，放行
        if host in {"checkout.stripe.com", "api.stripe.com", "pay.openai.com", "pm-redirects.stripe.com"}:
            return False
        if host.endswith(".paypal.com") or host == "paypal.com":
            return False
        return True
    return path.endswith(ignored_suffixes)

def opll_collect_urls(payload, urls: list[str] | None = None) -> list[str]:
    found = urls if urls is not None else []
    if isinstance(payload, str):
        for match in re.findall(r"https?://[^\s\"'<>]+", payload):
            found.append(match.rstrip("),.;]"))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if key in ("url", "return_url", "redirect_url", "redirect_to_url") and isinstance(value, str) and opll_is_external_url(value):
                found.append(value)
            else:
                opll_collect_urls(value, found)
    elif isinstance(payload, list):
        for item in payload:
            opll_collect_urls(item, found)
    return found

def opll_extract_redirect_to_url(payload) -> str:
    if not isinstance(payload, dict):
        urls = opll_collect_urls(payload)
        return next(
            (item for item in urls if opll_is_paypal_ba_approve_url(item)),
            next((item for item in urls if opll_is_paypal_url(item) and not opll_is_ignored_resource_url(item)), ""),
        )
    next_action = payload.get("next_action")
    if isinstance(next_action, dict) and next_action.get("type") == "redirect_to_url":
        redirect_to_url = next_action.get("redirect_to_url") or {}
        if isinstance(redirect_to_url, dict):
            url = str(redirect_to_url.get("url") or "").strip()
            if url:
                return url
    for key in ("setup_intent", "payment_intent"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = opll_extract_redirect_to_url(nested)
            if found:
                return found
    urls = opll_collect_urls(payload)
    return next(
        (item for item in urls if opll_is_paypal_ba_approve_url(item)),
        next((item for item in urls if opll_is_paypal_url(item) and not opll_is_ignored_resource_url(item)), ""),
    )

def opll_extract_provider_redirect_url(payload) -> str:
    if not isinstance(payload, dict):
        urls = opll_collect_urls(payload)
        return next((item for item in urls if opll_is_external_url(item) and not opll_is_ignored_resource_url(item)), "")
    next_action = payload.get("next_action")
    if isinstance(next_action, dict) and next_action.get("type") == "redirect_to_url":
        redirect_to_url = next_action.get("redirect_to_url") or {}
        if isinstance(redirect_to_url, dict):
            url = str(redirect_to_url.get("url") or "").strip()
            if url:
                return url
    for key in ("setup_intent", "payment_intent"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = opll_extract_provider_redirect_url(nested)
            if found:
                return found
    urls = opll_collect_urls(payload)
    return next((item for item in urls if opll_is_external_url(item) and not opll_is_ignored_resource_url(item)), "")

def opll_first_non_empty(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(values.get(key) or "").strip()
        if value:
            return value
    return ""

def opll_submission_attempt_failure_fields(submission) -> dict[str, str]:
    wanted = {"error", "code", "message", "reason", "failure_reason", "decline_code", "failure_code", "failure_message"}
    found: dict[str, str] = {}

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key or "").strip()
                if normalized in wanted and normalized not in found:
                    if isinstance(item, (str, int, float, bool)):
                        text = str(item).strip()
                    elif isinstance(item, dict):
                        text = str(item.get("message") or item.get("code") or item.get("reason") or item.get("type") or "").strip()
                    else:
                        text = ""
                    if text:
                        found[normalized] = text[:240]
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    if isinstance(submission, dict):
        walk(submission)
    return found

def opll_find_submission_attempt(payload) -> dict:
    if isinstance(payload, dict):
        item = payload.get("submission_attempt")
        if isinstance(item, dict):
            return item
        for value in payload.values():
            found = opll_find_submission_attempt(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = opll_find_submission_attempt(value)
            if found:
                return found
    return {}

def opll_submission_attempt_summary(submission: dict) -> str:
    if not submission:
        return "未找到 submission_attempt"
    fields = opll_submission_attempt_failure_fields(submission)
    state = str(submission.get("state") or "未知").strip()
    reason = opll_first_non_empty(fields, "reason", "failure_reason", "decline_code", "failure_code", "code")
    code = opll_first_non_empty(fields, "code", "decline_code", "failure_code")
    message = opll_first_non_empty(fields, "message", "failure_message", "error")
    parts = [f"state={state}"]
    if reason:
        parts.append(f"reason={reason}")
    if code:
        parts.append(f"code={code}")
    if message:
        parts.append(f"message={message}")
    return "，".join(parts)

def opll_stripe_payload_diagnostics(payload, ctx: dict) -> str:
    if not isinstance(payload, dict):
        return f"payload_type={type(payload).__name__}"
    keys = ",".join(sorted(payload.keys())[:12])
    urls = opll_collect_urls(payload)
    paypal_count = sum(1 for item in urls if opll_is_paypal_url(item))
    ba_count = sum(1 for item in urls if opll_is_paypal_ba_approve_url(item))
    ignored_count = sum(1 for item in urls if opll_is_ignored_resource_url(item))
    submission = opll_find_submission_attempt(payload)
    submission_state = str(submission.get("state") or "") if isinstance(submission, dict) else ""
    submission_fields = opll_submission_attempt_failure_fields(submission)
    submission_reason = opll_first_non_empty(submission_fields, "reason", "failure_reason", "decline_code", "failure_code", "code")
    submission_code = opll_first_non_empty(submission_fields, "code", "decline_code", "failure_code")
    submission_message = opll_first_non_empty(submission_fields, "message", "failure_message", "error")
    return (
        f"keys=[{keys}], urls={len(urls)}, paypal_urls={paypal_count}, ba_approve_urls={ba_count}, "
        f"ignored_resource_urls={ignored_count}, submission_attempt={bool(submission)}, submission_state={submission_state or '未知'}, "
        f"submission_reason={submission_reason or '无'}, submission_code={submission_code or '无'}, "
        f"submission_message={submission_message or '无'}, ctx_session={ctx.get('elements_session_id') or ''}"
    )


class OpllStripeRequiresApproval(Exception):
    pass


class OpllChatgptApproveBlocked(Exception):
    pass


OPLL_APPROVE_BURST_RESULTS = {"blocked", "exception"}

def opll_chatgpt_approve(chatgpt: requests.Session, cs_id: str, checkout: dict) -> None:
    entity = opll_processor_entity_for_country(checkout["billing_country"], checkout.get("processor_entity", ""))
    try:
        chatgpt.post(
            "https://chatgpt.com/backend-api/sentinel/ping",
            json={},
            headers={
                "Referer": "https://chatgpt.com/",
                "x-openai-target-path": "/backend-api/sentinel/ping",
                "x-openai-target-route": "/backend-api/sentinel/ping",
            },
            timeout=PAY_LONG_LINK_TIMEOUT,
        )
    except Exception:
        pass
    response = chatgpt.post(
        "https://chatgpt.com/backend-api/payments/checkout/approve",
        json={"checkout_session_id": cs_id, "processor_entity": entity},
        headers={"Referer": f"https://chatgpt.com/checkout/{entity}/{cs_id}", "x-openai-target-path": "/backend-api/payments/checkout/approve", "x-openai-target-route": "/backend-api/payments/checkout/approve"},
        timeout=PAY_LONG_LINK_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"chatgpt approve failed: HTTP {response.status_code} {response.text[:500]}")
    try:
        result = (response.json() or {}).get("result")
    except Exception:
        result = ""
    normalized_result = str(result or "").strip().lower()
    if normalized_result in OPLL_APPROVE_BURST_RESULTS:
        raise OpllChatgptApproveBlocked(f"chatgpt approve retryable result: {normalized_result!r}")
    if result != "approved":
        raise RuntimeError(f"chatgpt approve unexpected result: {result!r}")

def opll_chatgpt_approve_with_retry(access_token: str, cs_id: str, checkout: dict, proxy_url: str = "") -> requests.Session:
    """Approve checkout after Stripe requires_approval.

    blocked 常与出口/风控相关：换 sid、换池内线路、必要时直连再试；
    不再在第一次 blocked 就立刻放弃（0 元 BA 路径尤其依赖 approve）。
    """
    last_error = ""
    base = str(proxy_url or "").strip()
    pool_lines = split_proxy_pool(base)
    if not pool_lines and base:
        pool_lines = [base]
    # 候选：池内每条 + 随机 sid 变体；末尾补一次直连
    candidates: list[str] = []
    for line in pool_lines or [""]:
        norm = normalize_proxy_url(line) if line else ""
        if norm:
            candidates.append(norm)
            candidates.append(randomize_proxy_sid(norm))
            candidates.append(randomize_proxy_sid(norm))
    candidates.append("")  # 直连兜底
    # 去重保序
    seen: set[str] = set()
    hops: list[str] = []
    for item in candidates:
        key = item or "__direct__"
        if key in seen:
            continue
        seen.add(key)
        hops.append(item)
    # 最多 8 次，避免卡死
    hops = hops[:8]

    for attempt, hop in enumerate(hops):
        try:
            chatgpt = opll_build_chatgpt_session(access_token, hop)
            opll_chatgpt_approve(chatgpt, cs_id, checkout)
            return chatgpt
        except OpllChatgptApproveBlocked as exc:
            last_error = str(exc)
            # blocked：换下一条出口继续，不要立刻 break
            time.sleep(0.5 + attempt * 0.25)
            continue
        except Exception as exc:
            last_error = str(exc)
            if is_proxy_retryable_error(exc) or attempt + 1 < len(hops):
                time.sleep(0.6 + attempt * 0.3)
                continue
            break
    raise RuntimeError(f"ChatGPT approve 连续失败: {last_error}")

def opll_stripe_payment_page_redirect_url(stripe: requests.Session, cs_id: str, stripe_pk: str, payment_locale: str = "en", timeout_seconds: int = 45, ctx: dict | None = None) -> str:
    deadline = time.time() + max(1, timeout_seconds)
    _browser_locale, elements_locale = locale_parts(payment_locale)
    ctx = ctx or {}
    params = {
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[session_id]": str(ctx.get("elements_session_id") or f"elements_session_{uuid.uuid4().hex[:11]}"),
        "elements_session_client[stripe_js_id]": str(ctx.get("stripe_js_id") or uuid.uuid4()),
        "elements_session_client[locale]": elements_locale,
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
    }
    last_err = ""
    while time.time() < deadline:
        response = stripe.get(
            f"https://api.stripe.com/v1/payment_pages/{cs_id}",
            params=params,
            timeout=PAY_LONG_LINK_TIMEOUT,
        )
        if response.status_code == 200:
            payload = response.json() or {}
            # 优先 BA approve / 真 PayPal，忽略 cloudfront 资源图
            urls = opll_collect_urls(payload)
            for item in urls:
                if opll_is_paypal_ba_approve_url(item):
                    return item
            for item in urls:
                if opll_is_paypal_url(item) and not opll_is_ignored_resource_url(item):
                    return item
            redirect_url = opll_extract_redirect_to_url(payload)
            if redirect_url and not opll_is_ignored_resource_url(redirect_url):
                return redirect_url
            submission = opll_find_submission_attempt(payload)
            if submission.get("state") == "requires_approval":
                raise OpllStripeRequiresApproval("payment page requires ChatGPT approval")
            if submission.get("state") == "failed":
                raise RuntimeError(
                    f"stripe submission failed: {opll_submission_attempt_summary(submission)}; "
                    f"{opll_stripe_payload_diagnostics(payload, ctx)}"
                )
            last_err = opll_stripe_payload_diagnostics(payload, ctx)
        else:
            last_err = f"HTTP {response.status_code} {response.text[:120]}"
        time.sleep(1)
    raise RuntimeError(f"redirect url resolution timeout: {last_err}")

def opll_stripe_payment_page_provider_redirect_url(stripe: requests.Session, cs_id: str, stripe_pk: str, payment_locale: str = "en", timeout_seconds: int = 45, ctx: dict | None = None) -> str:
    deadline = time.time() + max(1, timeout_seconds)
    _browser_locale, elements_locale = locale_parts(payment_locale)
    ctx = ctx or {}
    params = {
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[session_id]": str(ctx.get("elements_session_id") or f"elements_session_{uuid.uuid4().hex[:11]}"),
        "elements_session_client[stripe_js_id]": str(ctx.get("stripe_js_id") or uuid.uuid4()),
        "elements_session_client[locale]": elements_locale,
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
    }
    last_err = ""
    while time.time() < deadline:
        response = stripe.get(
            f"https://api.stripe.com/v1/payment_pages/{cs_id}",
            params=params,
            timeout=PAY_LONG_LINK_TIMEOUT,
        )
        if response.status_code == 200:
            payload = response.json() or {}
            redirect_url = opll_extract_provider_redirect_url(payload)
            if redirect_url:
                return redirect_url
            submission = opll_find_submission_attempt(payload)
            if submission.get("state") == "requires_approval":
                raise OpllStripeRequiresApproval("payment page requires ChatGPT approval")
            if submission.get("state") == "failed":
                raise RuntimeError(f"stripe submission failed: {opll_stripe_payload_diagnostics(payload, ctx)}")
            last_err = opll_stripe_payload_diagnostics(payload, ctx)
        else:
            last_err = f"HTTP {response.status_code} {response.text[:120]}"
        time.sleep(1)
    raise RuntimeError(f"provider redirect url resolution timeout: {last_err}")

def opll_resolve_external_redirect(stripe: requests.Session, redirect_url: str, preferred_hosts: tuple[str, ...] = ("paypal.com",)) -> str:
    """跟随 Stripe/pm-redirects 到目标支付页（PayPal BA / MoMo 等）。

    代理隧道失败必须抛出（可重试），不能静默返回 pm-redirects 中间页，
    否则上层会误报「未提取到 BA 链」且不会换 sid 重试。
    """
    preferred_hosts = tuple(str(h or "").strip().lower() for h in (preferred_hosts or ()) if str(h or "").strip())
    want_paypal = (not preferred_hosts) or any("paypal" in h for h in preferred_hosts)
    want_momo = any("momo" in h for h in preferred_hosts)

    def _is_preferred_success(url: str) -> bool:
        u = str(url or "").strip()
        if not u:
            return False
        if want_paypal and opll_is_paypal_success_url(u):
            return True
        if want_momo and opll_is_momo_url(u):
            return True
        # preferred_hosts 为空时：仅按「外部非资源」不够，仍优先 paypal 语义
        if not preferred_hosts and opll_is_paypal_success_url(u):
            return True
        return False

    def _host_matches_preferred(url: str) -> bool:
        if not preferred_hosts:
            return False
        host = (urlsplit(url).netloc or "").lower()
        return any(host == item or host.endswith(f".{item}") for item in preferred_hosts)

    current = str(redirect_url or "").strip()
    for _ in range(10):
        if not current:
            return ""
        if _is_preferred_success(current):
            return current
        # preferred 主机已到达（MoMo 网关 / PayPal 带 ba_token）
        if _host_matches_preferred(current):
            if want_momo and opll_is_momo_url(current):
                return current
            if "ba_token=" in current or opll_is_paypal_ba_approve_url(current):
                return current
        try:
            response = stripe.get(
                current,
                allow_redirects=False,
                timeout=PAY_LONG_LINK_TIMEOUT,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://checkout.stripe.com/",
                },
            )
        except Exception as exc:
            if is_proxy_retryable_error(exc):
                raise RuntimeError(f"跟随 Stripe 跳转时代理失败: {type(exc).__name__}: {exc}") from exc
            return current
        # 代理网关偶发把 408 写在 HTTP 状态上
        if int(getattr(response, "status_code", 0) or 0) in {407, 408, 429, 502, 503, 504}:
            raise RuntimeError(
                f"跟随 Stripe 跳转时代理失败: HTTP {response.status_code} on {current[:120]}"
            )
        location = str(response.headers.get("Location") or "").strip()
        if response.status_code in (301, 302, 303, 307, 308) and location:
            current = urljoin(current, location)
            continue
        # 200 页内可能内嵌 meta refresh / JS / 纯 URL
        body = ""
        try:
            body = response.text or ""
        except Exception:
            body = ""
        found = ""
        if body:
            for item in re.findall(r"https?://[^\s\"'<>]+", body):
                item = item.rstrip("),.;]")
                if _is_preferred_success(item):
                    found = item
                    break
            if not found:
                m = re.search(r'url\s*=\s*[\'"](https?://[^\'"]+)[\'"]', body, re.I)
                if m and opll_is_external_url(m.group(1)):
                    found = m.group(1).strip()
            if not found:
                m = re.search(r'location(?:\.href)?\s*=\s*[\'"](https?://[^\'"]+)[\'"]', body, re.I)
                if m and opll_is_external_url(m.group(1)):
                    found = m.group(1).strip()
        if found:
            current = found
            if _is_preferred_success(current):
                return current
            continue
        # 仍停在 pm-redirects 中间页：不算成功
        if opll_is_stripe_pm_redirect_url(current):
            target = "MoMo" if want_momo and not want_paypal else ("PayPal" if want_paypal else "外部支付页")
            raise RuntimeError(f"跟随 Stripe 跳转未到达 {target}，仍停留在中间页: {current[:160]}")
        return current
    if _is_preferred_success(current):
        return current
    raise RuntimeError(f"跟随 Stripe 跳转次数过多，最后: {current[:160]}")

def opll_stripe_confirm(stripe: requests.Session, cs_id: str, pm_id: str, stripe_pk: str, init_payload: dict, ctx: dict, checkout: dict, stripe_hosted_url: str, payment_method_type: str = "paypal") -> dict:
    return_url = opll_stripe_confirm_return_url(cs_id, checkout, stripe_hosted_url)
    runtime_version = str(ctx.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION)
    payment_method_type = str(payment_method_type or "paypal").strip().lower()
    response = stripe.post(
        f"https://api.stripe.com/v1/payment_pages/{cs_id}/confirm",
        data={
            "guid": uuid.uuid4().hex,
            "muid": uuid.uuid4().hex,
            "sid": uuid.uuid4().hex,
            "payment_method": pm_id,
            "init_checksum": str(init_payload.get("init_checksum") or ctx.get("init_checksum") or ""),
            "version": runtime_version,
            "expected_amount": str(ctx.get("checkout_amount") or opll_expected_amount(init_payload)),
            "expected_payment_method_type": payment_method_type,
            "return_url": return_url,
            "elements_session_client[session_id]": ctx["elements_session_id"],
            "elements_session_client[locale]": str(ctx.get("locale") or "en"),
            "elements_session_client[referrer_host]": "chatgpt.com",
            "elements_session_client[is_aggregation_expected]": "false",
            "elements_session_client[elements_init_source]": "custom_checkout",
            "elements_session_client[stripe_js_id]": ctx["stripe_js_id"],
            "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
            "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
            "elements_options_client[saved_payment_method][enable_save]": "never",
            "elements_options_client[saved_payment_method][enable_redisplay]": "never",
            "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
            "client_attribution_metadata[checkout_session_id]": cs_id,
            "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
            "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
            "client_attribution_metadata[elements_session_config_id]": ctx["elements_session_config_id"],
            "client_attribution_metadata[merchant_integration_source]": "checkout",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[merchant_integration_version]": "custom",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
            "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
            "consent[terms_of_service]": "accepted",
            "key": stripe_pk,
            "_stripe_version": STRIPE_VERSION_FULL,
        },
        timeout=PAY_LONG_LINK_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(opll_stripe_error_summary("stripe confirm failed", response))
    return response.json() or {}

def opll_redirect_url_after_confirm(access_token: str, stripe: requests.Session, confirm_payload: dict, cs_id: str, stripe_pk: str, ctx: dict, checkout: dict, approve_proxy_url: str = "") -> str:
    redirect_url = opll_extract_redirect_to_url(confirm_payload)
    if redirect_url and not opll_is_ignored_resource_url(redirect_url):
        return redirect_url
    submission = opll_find_submission_attempt(confirm_payload)
    if submission.get("state") == "requires_approval":
        opll_chatgpt_approve_with_retry(access_token, cs_id, checkout, approve_proxy_url)
        try:
            return opll_stripe_payment_page_redirect_url(stripe, cs_id, stripe_pk, ctx=ctx, timeout_seconds=45)
        except OpllStripeRequiresApproval:
            # approve 已过但仍标 requires_approval：再批一次
            opll_chatgpt_approve_with_retry(access_token, cs_id, checkout, approve_proxy_url)
            return opll_stripe_payment_page_redirect_url(stripe, cs_id, stripe_pk, ctx=ctx, timeout_seconds=45)
    if submission.get("state") == "failed":
        raise RuntimeError(
            f"stripe submission failed: {opll_submission_attempt_summary(submission)}; "
            f"{opll_stripe_payload_diagnostics(confirm_payload, ctx)}"
        )
    try:
        return opll_stripe_payment_page_redirect_url(stripe, cs_id, stripe_pk, ctx=ctx, timeout_seconds=30)
    except OpllStripeRequiresApproval:
        opll_chatgpt_approve_with_retry(access_token, cs_id, checkout, approve_proxy_url)
        return opll_stripe_payment_page_redirect_url(stripe, cs_id, stripe_pk, ctx=ctx, timeout_seconds=45)

def opll_provider_redirect_url_after_confirm(access_token: str, stripe: requests.Session, confirm_payload: dict, cs_id: str, stripe_pk: str, ctx: dict, checkout: dict, approve_proxy_url: str = "") -> str:
    redirect_url = opll_extract_provider_redirect_url(confirm_payload)
    if redirect_url:
        return redirect_url
    submission = opll_find_submission_attempt(confirm_payload)
    if submission.get("state") == "requires_approval":
        opll_chatgpt_approve_with_retry(access_token, cs_id, checkout, approve_proxy_url)
        return opll_stripe_payment_page_provider_redirect_url(stripe, cs_id, stripe_pk, ctx=ctx, timeout_seconds=45)
    if submission.get("state") == "failed":
        raise RuntimeError(f"stripe submission failed: {opll_stripe_payload_diagnostics(confirm_payload, ctx)}")
    try:
        return opll_stripe_payment_page_provider_redirect_url(stripe, cs_id, stripe_pk, ctx=ctx, timeout_seconds=30)
    except OpllStripeRequiresApproval:
        opll_chatgpt_approve_with_retry(access_token, cs_id, checkout, approve_proxy_url)
        return opll_stripe_payment_page_provider_redirect_url(stripe, cs_id, stripe_pk, ctx=ctx, timeout_seconds=45)

def opll_combo_attempt_order(
    country: str,
    prefer_countries: list[str] | None = None,
    allow_fallback: bool = False,
) -> list[tuple[str, str]]:
    requested = normalize_opll_country(country)
    ordered = [(requested, requested)]
    if allow_fallback:
        for preferred in prefer_countries or []:
            normalized = normalize_opll_country(preferred)
            ordered.append((normalized, normalized))
        if requested == "DE":
            ordered.extend([("US", "US"), ("DE", "US"), ("US", "DE")])
    result = []
    seen = set()
    for item in ordered:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

def detect_proxy_transport(proxy_url: str, timeout: float = 4.0) -> str:
    """Best-effort detect: socks5 vs http. Never blocks long."""
    import socket
    proxy_url = normalize_proxy_url(proxy_url)
    if not proxy_url:
        return "unknown"
    try:
        parsed = urlsplit(proxy_url)
        host, port = parsed.hostname, parsed.port
        if not host or not port:
            return "unknown"
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        try:
            sock.settimeout(timeout)
            sock.sendall(b"\x05\x01\x02")
            data = sock.recv(64) or b""
        finally:
            sock.close()
    except Exception:
        return "unknown"
    if data[:1] == b"\x05":
        return "socks5"
    if data.upper().startswith(b"HTTP/") or b"PROXY" in data.upper() or b"FORBIDDEN" in data.upper():
        return "http"
    if data and all(32 <= b < 127 or b in (9, 10, 13) for b in data[:24]):
        return "http"
    return "unknown"

def proxy_url_candidates(proxy_url: str) -> list[str]:
    """协议候选：默认先 HTTP（住宅代理常见），再 socks5h。避免穷举拖死测试。"""
    raw = normalize_proxy_url(proxy_url)
    if not raw:
        return []
    rest = raw.split("://", 1)[1] if "://" in raw else raw
    scheme = (raw.split("://", 1)[0].lower() if "://" in raw else "http") or "http"
    out: list[str] = []
    def add(u: str) -> None:
        u = str(u or "").strip()
        if u and u not in out:
            out.append(u)
    # 用户写了什么先试什么
    add(raw)
    if scheme.startswith("socks"):
        add(f"socks5h://{rest}")
        add(f"http://{rest}")
    else:
        # arxLabs 等：无协议默认 http，几乎都是 HTTP CONNECT
        add(f"http://{rest}")
        add(f"socks5h://{rest}")
    return out


def _proxy_session(proxy: str, pre_proxy: str = ""):
    """探测用 session：有前置走 curl PRE_PROXY，否则 plain requests。"""
    pre = _normalize_pre_proxy(pre_proxy)
    if pre and CurlCffiSession is not None:
        s = opll_new_http_session(engine="curl", pre_proxy=pre)
    else:
        s = requests.Session()
        s.trust_env = False
    if proxy:
        _apply_proxy_to_session(s, proxy, pre_proxy=pre)
    s.headers.update({"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"})
    return s


def probe_proxy_exit(proxy_url: str = "", timeout: int = 8) -> dict:
    """探测代理：连通优先，geo 其次。

    ok 条件（满足任一即可）：
    1) 拿到真实 country 或 ip
    2) 代理网关可达（能拿到 HTTP 响应，含对公开 Geo 站的 403）
    自动试本机前置（7890），与提链/BA 同一策略。
    """
    raw_proxy = normalize_proxy_url(proxy_url)
    region_hint = extract_region_hint_from_proxy(raw_proxy)
    errors: list[str] = []
    country, ip, source = "", "", ""
    used_proxy = raw_proxy
    used_pre = ""
    coerced_note = ""
    reachable = False
    geo_blocked = False  # 公开 Geo/IP 站被拦（≠ 代理后台「IP 白名单」）
    geo_verified = False
    proxy_rejected = False

    # 少而精：HTTP 优先（住宅代理常拦 HTTPS CONNECT 到公开 IP 站）
    endpoints: list[tuple[str, str]] = [
        ("http://ip-api.com/json/?fields=status,message,country,countryCode,query", "json"),
        ("http://icanhazip.com", "plain_ip"),
        ("https://api.ipify.org?format=json", "json"),
        ("https://www.cloudflare.com/cdn-cgi/trace", "cf_trace"),
    ]

    candidates = proxy_url_candidates(raw_proxy) if raw_proxy else [""]
    pre_list: list[str] = [""]
    if raw_proxy:
        key = _proxy_route_cache_key(raw_proxy)
        if key in _PRE_PROXY_ROUTE_CACHE:
            cached = _PRE_PROXY_ROUTE_CACHE[key]
            pre_list = [cached] if cached else [""]
        else:
            # 未探测：先直连再本机前置；resolve 会写缓存
            forced = resolve_pre_proxy_for(raw_proxy)
            pre_list = [forced] if forced else [""] + list_pre_proxy_candidates()
    per_try = max(3.0, min(float(timeout), 8.0))

    for pre in pre_list:
        if country and ip:
            break
        for cand in candidates:
            if country and ip:
                break
            used_proxy = cand
            used_pre = pre
            try:
                session = _proxy_session(cand, pre_proxy=pre)
            except Exception as exc:
                errors.append(f"session pre={pre or 'direct'} {cand} -> {type(exc).__name__}: {exc}")
                continue
            for url, kind in endpoints:
                if country and ip:
                    break
                try:
                    resp = session.get(url, timeout=per_try)
                    body = (resp.text or "").strip()
                    low_body = body.lower()
                    # 代理服务端明确拒绝时不能视为连通，否则界面会误报测试成功。
                    if (
                        "forbidden ip" in low_body
                        or "proxy-authenticate" in low_body
                        or resp.status_code == 407
                        or ("not supported" in low_body and "ip=" in low_body)
                    ):
                        # 拒 IP：换前置，不要锁死 rejected
                        if "forbidden ip" in low_body or ("not supported" in low_body and "ip=" in low_body):
                            errors.append(f"pre={pre or 'direct'} {cand} {url} -> {body[:120]}")
                            break
                        proxy_rejected = True
                        errors.append(f"{cand} {url} -> HTTP {resp.status_code} {body[:120]}")
                        break
                    # 任意非认证拒绝的响应 = 代理网关可达。
                    reachable = True
                    # 某些公开 Geo/IP 站会被节点拦截，但这不代表代理认证失败。
                    if resp.status_code == 403 and ("forbidden" in low_body or "ip=" in low_body):
                        geo_blocked = True
                        errors.append(f"{cand} {url} -> HTTP {resp.status_code} {body[:120]}")
                        break
                    if resp.status_code >= 400:
                        errors.append(f"{cand} {url} -> HTTP {resp.status_code} {body[:120]}")
                        continue
                    got_c, got_i = "", ""
                    if kind == "cf_trace":
                        got_c, got_i = _parse_cf_trace(body)
                    elif kind == "plain_ip":
                        cand_ip = body.split()[0] if body else ""
                        if _looks_like_ip(cand_ip):
                            got_i = cand_ip
                    else:
                        try:
                            data = resp.json() if resp.content else {}
                        except Exception:
                            data = {}
                        if isinstance(data, dict):
                            if str(data.get("status") or "").lower() == "fail":
                                errors.append(f"{url} -> {data.get('message') or 'fail'}")
                                continue
                            got_c, got_i = _parse_geo_payload(data)
                    if got_c and not country:
                        country = got_c
                        source = source or url
                        geo_verified = True
                    if got_i and not ip:
                        ip = got_i
                        source = source or url
                        geo_verified = True
                except Exception as exc:
                    errors.append(f"pre={pre or 'direct'} {cand} {url} -> {type(exc).__name__}: {exc}")
                    continue
            if country or ip or reachable:
                if cand != raw_proxy or pre:
                    bits = []
                    try:
                        bits.append(urlsplit(cand).scheme or "http")
                    except Exception:
                        bits.append("http")
                    if pre:
                        bits.append(f"via {pre}")
                    coerced_note = "已用 " + " ".join(bits) + " 连通"
                # 缓存成功路由
                if raw_proxy and (country or ip or reachable) and not proxy_rejected:
                    key = _proxy_route_cache_key(raw_proxy)
                    if key:
                        _PRE_PROXY_ROUTE_CACHE[key] = pre or ""
                break
            if reachable:
                break
        if country or ip or reachable:
            break

    # geo 失败但代理可达：测试仍算通过；region 只作提示
    warning = ""
    if not country and not ip and reachable:
        if region_hint:
            warning = "公开出口检测站不可达（与后台 IP 白名单无关）；仅显示账号 region 提示"
        else:
            warning = "公开出口检测站不可达；代理网关可达，出口国家/IP 未识别"
        if geo_blocked:
            warning += "；部分代理会拦 ip-api/ipify 等检测域名，业务出链一般仍可用"
        if used_pre:
            warning += f"；已走本机前置 {used_pre}"

    ok = bool(country or ip or reachable) and not proxy_rejected
    detail_join = "; ".join(errors[:6])
    if ok:
        err_msg = ""
    else:
        low = detail_join.lower()
        if proxy_rejected:
            err_msg = "代理服务器拒绝了当前请求（认证或出口策略拒绝）。请切换代理池中的下一条。"
        elif "forbidden ip" in low or "not supported" in low:
            err_msg = (
                "供应商拒绝了客户端 IP（账号可能正常）。"
                "请保持本机 Clash/7890 开启；程序会自动走前置。"
            )
        elif "socks5" in low and "invalid" in low:
            err_msg = "SOCKS5 握手失败（端口可能是 HTTP 代理）。请用 http://user:pass@host:port。"
        elif "missing dependencies for socks" in low:
            err_msg = "缺少 SOCKS 依赖：请 pip install PySocks 后重启。"
        else:
            err_msg = (
                "代理连不上：超时/鉴权失败/节点不可用。"
                + (f"；账号 region={region_hint}" if region_hint else "")
            )

    return {
        "ok": ok,
        "country": country or "",
        "ip": ip or "",
        "source": source or "",
        "region_hint": region_hint or "",
        "proxy": used_proxy or "",
        "proxy_raw": raw_proxy or "",
        "pre_proxy": used_pre or "",
        "coerced_note": coerced_note or "",
        "reachable": reachable,
        "geo_verified": geo_verified,
        "geo_blocked": geo_blocked,
        "proxy_rejected": proxy_rejected,
        "warning": warning or "",
        "errors": errors[:8],
        "error": err_msg,
        "detail": "" if ok else (detail_join[:500] or err_msg),
    }

def coerce_proxy_url(proxy_url: str, prefer_detect: bool = True) -> str:
    """Compatibility wrapper: return first candidate (raw normalized)."""
    cands = proxy_url_candidates(proxy_url)
    if not cands:
        return ""
    if not prefer_detect:
        return cands[0]
    # Prefer detected transport when clear
    raw = cands[0]
    try:
        t = detect_proxy_transport(raw)
        rest = raw.split("://", 1)[-1]
        if t == "http":
            return f"http://{rest}"
        if t == "socks5":
            return f"socks5h://{rest}"
    except Exception:
        pass
    return raw

def classify_proxy_error(detail: str, region_hint: str = "") -> str:
    low = str(detail or "").lower()
    if "forbidden ip" in low or ("not supported" in low and "ip=" in low):
        return (
            "公开出口检测站被拦（不是后台 IP 白名单）；代理网关多半仍可用"
            + (f"；region={region_hint}" if region_hint else "")
        )
    if "invalid data" in low:
        return "SOCKS5 握手失败，可尝试 http:// 协议"
    return "代理出口探测失败" + (f"；region={region_hint}" if region_hint else "")

def detect_proxy_exit_country(proxy_url: str = "", timeout: int = 12) -> str:
    """Best-effort detect proxy/public exit country code (e.g. US).

    只返回实测 geo；region 账号标签不算真实出口。
    """
    info = probe_proxy_exit(proxy_url, timeout=timeout)
    if not info.get("geo_verified"):
        return ""
    country = str(info.get("country") or "").strip().upper()
    return country if len(country) == 2 else ""

def _paypal_wants_zero(target_amount: str = "") -> bool:
    """True when caller asks for free-trial / 0-bill PayPal BA."""
    return str(target_amount or "").strip() in {"0", "0.0", "0.00"}


def _paypal_refresh_zero_promo(
    access_token: str,
    checkout: dict,
    followup_proxy_url: str = "",
    max_attempts: int = 8,
) -> dict:
    """Apply free-trial promo on an existing non-promo checkout (keep PayPal PM types).

    Create-with-promo often collapses Stripe methods to card,link only.
    PIX already uses create(no promo) → update promotion; PayPal zero path mirrors that.
    """
    max_attempts = max(1, min(int(max_attempts or 8), 20))
    promo_errors: list[dict] = []
    last_payload: dict = {}
    for attempt in range(1, max_attempts + 1):
        promo_proxy = randomize_proxy_sid(followup_proxy_url) if followup_proxy_url else ""
        try:
            last_payload = opll_update_checkout_promotion(access_token, checkout, promo_proxy) or {}
            return {
                "ok": True,
                "attempts": attempt,
                "payload": last_payload,
                "promo_errors": promo_errors,
            }
        except Exception as exc:
            promo_errors.append({"attempt": attempt, "error": str(exc)[:400]})
            if attempt >= max_attempts:
                break
            time.sleep(0.6 + 0.15 * attempt)
    return {
        "ok": False,
        "attempts": max_attempts,
        "payload": last_payload,
        "promo_errors": promo_errors,
    }


def generate_opll_paypal_long_link(
    access_token: str,
    country: str,
    currency: str,
    create_proxy_url: str = "",
    followup_proxy_url: str = "",
    approve_proxy_url: str = "",
    target_amount: str = "",
    prefer_countries: list[str] | None = None,
    payment_locale: str = "en",
    payment_email: str = "",
    allow_country_fallback: bool = False,
    payment_countries: list[str] | None = None,
    proxy_exit_country: str = "",
) -> dict:
    """Build a PayPal approval link using the options supplied by ``generate_link``.

    ``payment_countries`` is retained as an alias for older running clients.
    住宅代理 CONNECT 408 时会换 sid 重试（对齐参考站「红字可多试几次」）。

    0 元路径（target_amount=0）：
      先无 promo 创建 checkout 保住 PayPal → promotion update 刷试用 → init/confirm 提 BA。
      直接 create-with-promo 常只剩 card,link，无法出 BA。
    """
    # 单行规范化用于 create/stripe；approve 额外保留原始多行池，blocked 时可换线路
    raw_create_pool = str(create_proxy_url or "").strip()
    raw_follow_pool = str(followup_proxy_url or "").strip() or raw_create_pool
    raw_approve_pool = str(approve_proxy_url or "").strip() or raw_follow_pool
    base_create = normalize_proxy_url(create_proxy_url)
    base_follow = normalize_proxy_url(followup_proxy_url) or base_create
    base_approve = normalize_proxy_url(approve_proxy_url) or base_follow
    payment_locale = str(payment_locale or "en").strip() or "en"
    payment_email = str(payment_email or "").strip() or token_profile_email(access_token)
    requested_country = normalize_opll_country(country)
    want_zero = _paypal_wants_zero(target_amount)
    # 不强制改写用户代理 region：prefer 仅在 allow_country_fallback（auto_match）时生效
    prefer = list(prefer_countries or payment_countries or [])
    # 出口探测只在 generate_link 做一次；这里复用，避免开局再卡一轮 probe
    exit_country = str(proxy_exit_country or "").strip().upper()
    if exit_country and len(exit_country) != 2:
        exit_country = ""
    if exit_country and allow_country_fallback and exit_country not in prefer:
        prefer.insert(0, exit_country)

    # 有代理时多试几轮换 sid；无代理只跑一轮
    attempts = 4 if base_create else 1
    failures: list[str] = []

    for attempt in range(1, attempts + 1):
        # 第 1 轮用用户原 sid；之后换 sid 换隧道（不改 region）
        create_p = randomize_proxy_sid(base_create) if (base_create and attempt > 1) else base_create
        follow_p = randomize_proxy_sid(base_follow) if (base_follow and attempt > 1) else base_follow
        approve_p = randomize_proxy_sid(base_approve) if (base_approve and attempt > 1) else base_approve
        round_proxy_fail = False

        for checkout_country, pm_country in opll_combo_attempt_order(
            requested_country, prefer, allow_fallback=allow_country_fallback
        ):
            try:
                # 0 元：强制无 promo 建单，避免 Stripe 只返回 card,link
                create_overrides = {"use_promo": False, "promo_code": ""} if want_zero else {}
                checkout = opll_create_checkout_with_opts(
                    access_token,
                    checkout_country,
                    currency_for_country(checkout_country)
                    if allow_country_fallback
                    else (currency or currency_for_country(checkout_country)),
                    create_p,
                    **create_overrides,
                )
                promo_meta: dict = {"wanted_zero": want_zero, "applied": False}
                if want_zero:
                    promo_meta = {
                        "wanted_zero": True,
                        **_paypal_refresh_zero_promo(access_token, checkout, follow_p),
                        "applied": True,
                    }

                stripe = opll_build_stripe_session(follow_p)
                init_payload = opll_stripe_init(
                    checkout["cs_id"],
                    checkout["billing_country"],
                    checkout["currency"],
                    follow_p,
                    payment_locale=payment_locale,
                    stripe=stripe,
                    checkout=checkout,
                )
                stripe_hosted_url = str(init_payload.get("stripe_hosted_url") or "").strip()
                if not stripe_hosted_url:
                    raise RuntimeError(f"stripe init response missing stripe_hosted_url, keys={sorted(init_payload.keys())}")
                methods = ensure_paypal_supported(init_payload)
                hosted_long_url = opll_to_openai_pay_url(stripe_hosted_url)
                stripe_pk = opll_stripe_key_for_checkout(checkout)
                billing = opll_billing_for_country(pm_country, payment_email=payment_email)
                # DE/EU 等会算税：先同步税区再 re-init，避免 confirm 后 upcoming_invoice_mismatch
                init_payload = opll_sync_billing_tax_and_reinit(
                    access_token,
                    checkout,
                    billing,
                    stripe,
                    proxy_url=follow_p,
                    payment_locale=payment_locale,
                    init_payload=init_payload,
                ) or init_payload
                stripe_hosted_url = str(init_payload.get("stripe_hosted_url") or stripe_hosted_url).strip()
                methods = ensure_paypal_supported(init_payload)
                ctx = opll_stripe_context(init_payload, payment_locale=payment_locale)
                if not ctx.get("currency"):
                    ctx["currency"] = str(checkout.get("currency") or "").lower()
                stripe_amount, stripe_amount_source = opll_stripe_amount_info(init_payload)
                # 0 元意图：promotion 后仍非 0，提前失败，避免白 confirm 出满价 BA
                if want_zero and str(stripe_amount) != "0":
                    promo_hint = ""
                    if promo_meta.get("ok") is False:
                        errs = promo_meta.get("promo_errors") or []
                        last = errs[-1]["error"] if errs else "promotion 未成功"
                        promo_hint = f"；promotion 失败: {last}"
                    elif promo_meta.get("ok") is True:
                        # OpenAI 常返回 success=true，但 one_click_trial_eligible=false 时金额仍是满价
                        cs_payload = ((promo_meta.get("payload") or {}).get("checkout_session") or {})
                        trial_flag = cs_payload.get("one_click_trial_eligible")
                        if trial_flag is False:
                            promo_hint = (
                                "；promotion 已调用但 one_click_trial_eligible=false，"
                                "账号无 free-trial/0 元资格（换新 free 账号，不要硬刷代理国）"
                            )
                        else:
                            promo_hint = (
                                f"；promotion 已调用但 Stripe 仍非 0"
                                f"（trial_eligible={trial_flag!r}，账号可能无 free-trial）"
                            )
                    raise AmountMismatchError("0", str(stripe_amount), stripe_amount_source + promo_hint)
                pm_id = opll_stripe_create_paypal_method(stripe, checkout["cs_id"], ctx, billing, stripe_pk)
                confirm_payload = opll_stripe_confirm(
                    stripe, checkout["cs_id"], pm_id, stripe_pk, init_payload, ctx, checkout, stripe_hosted_url
                )
                # approve 用完整代理池（多 sid），blocked 时在池内轮换；单跳 approve_p 作兜底
                approve_retry_pool = raw_approve_pool or approve_p
                stripe_redirect_url = opll_redirect_url_after_confirm(
                    access_token,
                    stripe,
                    confirm_payload,
                    checkout["cs_id"],
                    stripe_pk,
                    ctx,
                    checkout,
                    approve_retry_pool,
                )
                # 中间页（pm-redirects）必须继续跟随到 paypal BA；失败时换 sid 再跟
                try:
                    provider_url = (
                        stripe_redirect_url
                        if opll_is_paypal_ba_approve_url(stripe_redirect_url)
                        else opll_resolve_external_redirect(stripe, stripe_redirect_url)
                    )
                except Exception as follow_exc:
                    if not is_proxy_retryable_error(follow_exc):
                        raise
                    follow_retry = randomize_proxy_sid(follow_p) if follow_p else follow_p
                    stripe2 = opll_build_stripe_session(follow_retry)
                    provider_url = opll_resolve_external_redirect(stripe2, stripe_redirect_url)
                    stripe_redirect_url = provider_url or stripe_redirect_url
                if not opll_is_paypal_success_url(provider_url):
                    resource_hint = (
                        "仅发现 Stripe 资源 URL，未发现 PayPal BA approve 链；"
                        if opll_is_ignored_resource_url(provider_url)
                        else (
                            "仍停在 Stripe 中间跳转页，未拿到 BA approve；"
                            if opll_is_stripe_pm_redirect_url(provider_url)
                            else ""
                        )
                    )
                    raise RuntimeError(
                        f"{resource_hint}未提取到可用的 PayPal 跳转链接；当前结果: {provider_url or stripe_redirect_url}"
                    )
                return opll_apply_amount_check(
                    {
                        **checkout,
                        "payment_method_country": pm_country,
                        "payment_method_id": pm_id,
                        "payment_method_type": "paypal",
                        "payment_locale": payment_locale,
                        "payment_email": billing.get("email") or "",
                        "proxy_exit_country": exit_country,
                        "methods": methods,
                        "zero_promo": promo_meta,
                        "stripe_hosted_url": stripe_hosted_url,
                        "stripe_redirect_url": stripe_redirect_url,
                        "provider_redirect_url": provider_url,
                        "fallback": (checkout_country, pm_country) != (requested_country, requested_country),
                        "provider_error": "; ".join(failures),
                        "proxy_attempt": attempt,
                        "long_url": provider_url or hosted_long_url,
                        "stripe_amount": stripe_amount,
                        "stripe_amount_source": stripe_amount_source,
                    },
                    target_amount,
                )
            except AmountMismatchError:
                raise
            except Exception as exc:
                msg = opll_short_error(str(exc))
                # 0 元路径：approve 后 Stripe setup_attempt_failed 是账号/风控侧硬失败，换 sid 通常无意义
                low = msg.lower()
                if want_zero and (
                    "setup_attempt_failed" in low
                    or "checkout_approval_payment_failure" in low
                    or ("generic_decline" in low and "submission" in low)
                ):
                    failures.append(f"r{attempt}/{checkout_country}+{pm_country}: {msg}")
                    raise RuntimeError(
                        "0 元 PayPal BA 在 ChatGPT approve 后被 Stripe 拒绝："
                        f"{msg}。"
                        "已确认：无 promo 建 checkout + promotion 刷新可得到 amount=0 且含 paypal；"
                        "但 approve 后 setup_attempt_failed/generic_decline，拿不到 BA 跳转。"
                        "同账号同代理满价（非 0）可正常出 BA。"
                        "这通常是 OpenAI/Stripe 对 free-trial + PayPal setup 的账号风控，不是代理池格式问题。"
                    )
                failures.append(f"r{attempt}/{checkout_country}+{pm_country}: {msg}")
                if is_proxy_retryable_error(exc):
                    round_proxy_fail = True
                    # 代理类错误：不必再换账单国组合，直接进入下一轮换 sid
                    break

        if round_proxy_fail and attempt < attempts:
            time.sleep(0.7 + attempt * 0.3)
            continue
        # 非代理失败（或已用尽轮次）→ 跳出
        if not round_proxy_fail:
            break

    hint = ""
    if any("billing country must match request country" in failure.lower() for failure in failures):
        hint = " 提示: 代理出口与账单不一致时可改账单国，或换你自己的代理（程序不强制改 region）。"
    if any(is_proxy_retryable_error(f) for f in failures):
        hint += " 代理隧道不稳（如 CONNECT 408）：已自动换 sid 重试；仍失败请多点几次或换池内另一条。"
    raise RuntimeError(f"所有组合均未提取到 PayPal BA approve 链；{'; '.join(failures)}{hint}")

def random_br_cpf() -> str:
    """Generate a valid-looking Brazilian CPF number for PIX billing."""
    nums = [random.randint(0, 9) for _ in range(9)]
    for weight_start in (10, 11):
        total = sum(n * w for n, w in zip(nums, range(weight_start, 1, -1)))
        digit = 11 - (total % 11)
        nums.append(0 if digit >= 10 else digit)
    return "".join(str(n) for n in nums)

def token_profile_email(token: str) -> str:
    data = decode_jwt_payload(token)
    if not data:
        return ""
    profile = data.get("https://api.openai.com/profile") or {}
    email = str(profile.get("email") or data.get("email") or "").strip()
    return email if "@" in email else ""

def opll_br_billing_with_cpf(payment_email: str = "") -> dict:
    """Brazilian billing profile with CPF tax_id required by PIX."""
    profiles = [
        {"name": "Joao Silva", "phone": "+5511987654321", "line1": "Avenida Paulista 1000", "city": "Sao Paulo", "postal_code": "01310-100"},
        {"name": "Pedro Santos", "phone": "+5521987654321", "line1": "Avenida Atlantica 500", "city": "Rio de Janeiro", "postal_code": "22021-001"},
        {"name": "Carlos Oliveira", "phone": "+5561987654321", "line1": "Praca dos Tres Poderes", "city": "Brasilia", "postal_code": "70150-900"},
        {"name": "Rafael Souza", "phone": "+5531987654321", "line1": "Avenida Afonso Pena 1200", "city": "Belo Horizonte", "postal_code": "30130-003"},
    ]
    base = dict(random.choice(profiles))
    email = str(payment_email or "").strip()
    if not email or "@" not in email:
        email = f"joao.silva{random.randint(1000, 9999)}@gmail.com"
    return {
        "name": base["name"],
        "email": email,
        "phone": base["phone"],
        "country": "BR",
        "line1": base["line1"],
        "city": base["city"],
        "state": "",
        "postal_code": base["postal_code"],
        "tax_id": random_br_cpf(),
    }

def opll_checkout_referer(checkout: dict | None = None) -> str:
    checkout = checkout or {}
    cs_id = str(checkout.get("cs_id") or "").strip()
    country = str(checkout.get("billing_country") or "BR")
    entity = opll_processor_entity_for_country(country, checkout.get("processor_entity", ""))
    if cs_id:
        return f"https://chatgpt.com/checkout/{entity}/{cs_id}"
    return "https://chatgpt.com/"


def opll_update_checkout_taxes(
    access_token: str,
    checkout: dict,
    billing: dict,
    proxy_url: str = "",
    currency: str = "",
) -> dict:
    """同步 ChatGPT checkout 账单/税区，避免 confirm 后 checkout_upcoming_invoice_mismatch。"""
    cs_id = str((checkout or {}).get("cs_id") or "").strip()
    if not cs_id:
        raise RuntimeError("checkout taxes 缺少 cs_id")
    country = str(billing.get("country") or checkout.get("billing_country") or "US").upper()
    entity = opll_processor_entity_for_country(country, (checkout or {}).get("processor_entity", ""))
    cur = str(currency or checkout.get("currency") or currency_for_country(country) or "USD").upper()
    session = opll_build_chatgpt_session(access_token, proxy_url)
    path = "/backend-api/payments/checkout/taxes"
    tax_id = billing.get("tax_id")
    if tax_id in ("", None):
        tax_id = None
    body = {
        "checkout_session_id": cs_id,
        "checkout_email": str(billing.get("email") or ""),
        "billing_country": country,
        "billing_name": str(billing.get("name") or ""),
        "currency": cur,
        "tax_id": tax_id,
        "processor_entity": entity,
        "billing_address": {
            "line1": str(billing.get("line1") or ""),
            "city": str(billing.get("city") or ""),
            "country": country,
            "postal_code": str(billing.get("postal_code") or ""),
        },
    }
    state = str(billing.get("state") or "").strip()
    if state:
        body["billing_address"]["state"] = state
    response = session.post(
        f"https://chatgpt.com{path}",
        json=body,
        headers={
            "Referer": opll_checkout_referer(checkout),
            "x-openai-target-path": path,
            "x-openai-target-route": path,
        },
        timeout=PAY_LONG_LINK_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"checkout taxes update failed: HTTP {response.status_code} {response.text[:400]}")
    return response.json() or {}


def opll_stripe_update_tax_region(stripe: requests.Session, cs_id: str, stripe_pk: str, billing: dict) -> dict:
    """同步 Stripe payment_pages 税区；调用后必须重新 init 以刷新 amount/checksum。"""
    body = {
        "eid": "NA",
        "tax_region[country]": str(billing.get("country") or "US").upper(),
        "tax_region[postal_code]": str(billing.get("postal_code") or ""),
        "tax_region[line1]": str(billing.get("line1") or ""),
        "tax_region[city]": str(billing.get("city") or ""),
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
    }
    state = str(billing.get("state") or "").strip()
    if state:
        body["tax_region[state]"] = state
    response = stripe.post(
        f"https://api.stripe.com/v1/payment_pages/{cs_id}",
        data=body,
        timeout=PAY_LONG_LINK_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(opll_stripe_error_summary("stripe tax region failed", response))
    return response.json() or {}


def opll_sync_billing_tax_and_reinit(
    access_token: str,
    checkout: dict,
    billing: dict,
    stripe: requests.Session,
    proxy_url: str = "",
    payment_locale: str = "en",
    init_payload: dict | None = None,
) -> dict:
    """账单税区同步 + 重新 init，返回新的 init_payload。

    顺序对齐 PIX：先 ChatGPT /checkout/taxes，再 Stripe tax_region，最后 re-init 刷新 amount/checksum。
    EU 税（如 DE 19% VAT）不同步时，approve 后常见 checkout_upcoming_invoice_mismatch。
    """
    cs_id = str(checkout.get("cs_id") or "")
    stripe_pk = opll_stripe_key_for_checkout(checkout)
    tax_ok = False
    region_ok = False
    tax_err = ""
    region_err = ""
    try:
        opll_update_checkout_taxes(
            access_token,
            checkout,
            billing,
            proxy_url=proxy_url,
            currency=str(checkout.get("currency") or ""),
        )
        tax_ok = True
    except Exception as exc:
        tax_err = opll_short_error(str(exc), 160)
    try:
        opll_stripe_update_tax_region(stripe, cs_id, stripe_pk, billing)
        region_ok = True
    except Exception as exc:
        region_err = opll_short_error(str(exc), 160)
    if not region_ok and not tax_ok:
        # 两边都失败：保留原 init，由上层 confirm 暴露真实错误
        return init_payload or {}
    if not region_ok:
        # 仅 ChatGPT taxes 成功时仍 re-init，尽量拉齐 amount
        pass
    refreshed = opll_stripe_init(
        cs_id,
        checkout.get("billing_country") or billing.get("country") or "US",
        checkout.get("currency") or currency_for_country(str(billing.get("country") or "US")),
        proxy_url,
        payment_locale=payment_locale,
        stripe=stripe,
        checkout=checkout,
    )
    if isinstance(refreshed, dict):
        refreshed["_tax_sync"] = {
            "chatgpt_taxes": tax_ok,
            "stripe_tax_region": region_ok,
            "tax_err": tax_err,
            "region_err": region_err,
        }
    return refreshed


def opll_update_checkout_promotion(access_token: str, checkout: dict, proxy_url: str = "") -> dict:
    """Refresh free-trial promo context on an existing checkout session."""
    cs_id = str((checkout or {}).get("cs_id") or "").strip()
    if not cs_id:
        raise RuntimeError("checkout promotion 缺少 cs_id")
    entity = opll_processor_entity_for_country(
        str((checkout or {}).get("billing_country") or "BR"),
        (checkout or {}).get("processor_entity", ""),
    )
    token = extract_access_token_from_session_text(access_token) or str(access_token or "").strip()
    if not token:
        raise RuntimeError("当前账号没有 Access Token，请先注册并获取 Session 信息")
    device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, token))
    is_br = str((checkout or {}).get("billing_country") or "").upper() == "BR"
    path = "/backend-api/payments/checkout/update"
    response = request_with_proxy_fallback(
        "POST",
        f"https://chatgpt.com{path}",
        proxy_url=proxy_url,
        json_body={
            "checkout_session_id": cs_id,
            "processor_entity": entity,
            "plan_name": "chatgptplusplan",
            "price_interval": "month",
            "seat_quantity": 1,
            "promo_campaign": {"promo_campaign_id": "plus-1-month-free", "is_coupon_from_query_param": False},
        },
        headers={
            "Referer": opll_checkout_referer(checkout),
            "x-openai-target-path": path,
            "x-openai-target-route": path,
        },
        timeout=PAY_LONG_LINK_TIMEOUT,
        base_headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8" if is_br else "en-US,en;q=0.9",
            "Authorization": f"Bearer {token}",
            "Origin": "https://chatgpt.com",
            "Content-Type": "application/json",
            "oai-device-id": device_id,
            "oai-language": "pt-BR" if is_br else "en-US",
            "Cookie": f"oai-did={device_id}",
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(f"checkout promotion update failed: HTTP {response.status_code} {response.text[:500]}")
    payload = response.json() or {}
    if payload.get("success") is False:
        raise RuntimeError("checkout promotion update 被拒绝")
    return payload


def opll_openai_checkout_amount_info(payload: dict) -> tuple[str, str]:
    """Extract OpenAI hosted checkout due-today amount from checkout/update payload."""
    if not isinstance(payload, dict):
        return "", "openai_checkout_update.invalid"
    checkout_session = payload.get("checkout_session") if isinstance(payload.get("checkout_session"), dict) else payload
    state = checkout_session.get("checkout_state") if isinstance(checkout_session.get("checkout_state"), dict) else {}
    candidates = [
        ("checkout_state.total.total.minorUnitsAmount", (((state.get("total") or {}).get("total") or {}).get("minorUnitsAmount"))),
        ("checkout_state.total.dueToday.minorUnitsAmount", (((state.get("total") or {}).get("dueToday") or {}).get("minorUnitsAmount"))),
        ("checkout_state.dueToday.minorUnitsAmount", ((state.get("dueToday") or {}).get("minorUnitsAmount") if isinstance(state.get("dueToday"), dict) else None)),
        ("checkout_state.amountDue.minorUnitsAmount", ((state.get("amountDue") or {}).get("minorUnitsAmount") if isinstance(state.get("amountDue"), dict) else None)),
        ("checkout_state.total.total.amount", (((state.get("total") or {}).get("total") or {}).get("amount"))),
        ("checkout_state.total.dueToday.amount", (((state.get("total") or {}).get("dueToday") or {}).get("amount"))),
    ]
    for source, value in candidates:
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            return ("0" if abs(float(value)) < 0.000001 else str(int(value) if float(value).is_integer() else value), source)
        text = str(value).strip()
        if not text:
            continue
        number_match = re.search(r"-?\d[\d,]*(?:\.\d+)?", text)
        if not number_match:
            continue
        number = float(number_match.group(0).replace(",", ""))
        return ("0" if abs(number) < 0.005 else str(int(number) if number.is_integer() else number), source)
    return "", "openai_checkout_update.amount_missing"


def opll_collect_payment_method_types(value) -> list[str]:
    found: list[str] = []

    def add(item) -> None:
        text = str(item or "").strip().lower()
        if text and text not in found:
            found.append(text)

    def walk(v):
        if isinstance(v, dict):
            for k, val in v.items():
                key = str(k)
                if key in ("payment_method_types", "automatic_payment_method_types"):
                    if isinstance(val, list):
                        for item in val:
                            add(item)
                    elif isinstance(val, str):
                        add(val)
                elif key == "payment_method_type":
                    add(val)
                walk(val)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(value)
    return found

def ensure_pix_supported(init_payload: dict) -> list[str]:
    methods = opll_collect_payment_method_types(init_payload)
    if methods and "pix" not in methods:
        raise RuntimeError(f"当前 checkout 不支持 PIX，Stripe 仅返回支付方式：{','.join(methods)}")
    return methods


def ensure_paypal_supported(init_payload: dict) -> list[str]:
    """Stripe init 后校验 PayPal 是否在可用支付方式里，避免 confirm 时才报 mismatch。"""
    methods = opll_collect_payment_method_types(init_payload)
    if methods and "paypal" not in methods:
        raise RuntimeError(
            "当前 checkout 不支持 PayPal（payment_method_types_mismatch 预检失败），"
            f"Stripe 仅返回：{','.join(methods)}。"
            "请确认 checkout_ui_mode=hosted；代理请用你自己设置的自定义线路（不会强制改写出口），"
            "并尽量让账单国家与该代理实际出口一致。"
        )
    return methods


def opll_is_momo_url(value: str) -> bool:
    """识别 MoMo 网关跳转（payment.momo.vn / momo.vn）。"""
    try:
        host = (urlsplit(str(value or "")).netloc or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return (
        host == "momo.vn"
        or host.endswith(".momo.vn")
        or host == "payment.momo.vn"
        or "momo.vn" in host
    )


def _opll_init_merchant_diag(init_payload: dict | None) -> dict:
    """从 Stripe init 抽商户/支付配置诊断字段（不含密钥）。"""
    payload = init_payload if isinstance(init_payload, dict) else {}
    settings = payload.get("account_settings") if isinstance(payload.get("account_settings"), dict) else {}
    elements = payload.get("elements_options") if isinstance(payload.get("elements_options"), dict) else {}
    geo = payload.get("geocoding") if isinstance(payload.get("geocoding"), dict) else {}
    return {
        "methods": opll_collect_payment_method_types(payload),
        "ordered": [
            str(x).strip().lower()
            for x in (payload.get("ordered_payment_method_types") or [])
            if str(x).strip()
        ]
        if isinstance(payload.get("ordered_payment_method_types"), list)
        else [],
        "merchant": str(settings.get("display_name") or "").strip(),
        "mor_country": str(settings.get("merchant_of_record_country") or settings.get("country") or "").upper(),
        "geo_country": str(geo.get("country_code") or "").upper(),
        "pmc": str(elements.get("payment_method_configuration") or "").strip(),
    }


def ensure_momo_supported(init_payload: dict) -> list[str]:
    """Stripe init 后校验 MoMo 是否在可用支付方式里。"""
    methods = opll_collect_payment_method_types(init_payload)
    momo_aliases = {"momo", "momo_wallet", "momo_vn", "momowallet"}
    if methods and not (momo_aliases & set(methods)):
        diag = _opll_init_merchant_diag(init_payload)
        ordered = diag.get("ordered") or []
        mor = diag.get("mor_country") or "?"
        geo = diag.get("geo_country") or "?"
        merchant = diag.get("merchant") or "?"
        pmc = diag.get("pmc") or "?"
        raise RuntimeError(
            "当前 checkout 不支持 MoMo，"
            f"Stripe 仅返回：{','.join(methods)}"
            + (f"（ordered={','.join(ordered)}）" if ordered else "")
            + "。"
            f"诊断：geo={geo} · MOR={mor} · merchant={merchant} · pmc={pmc}。"
            "本账号 VN/VND 会话由 OpenAI OpCo, LLC(US) 结算，支付配置只开 card"
            "（同账号 DE 走 openai_ie 可出 paypal；强制 type=momo 会 payment_method_types_mismatch）。"
            "不是代理标签/custom/0元问题——OpenAI 未对该 checkout 启用 MoMo。"
            "换能出 momo 的账号/区域会话后再提。"
        )
    return methods


def opll_pick_momo_method_type(init_payload: dict | None = None) -> str:
    """从 Stripe methods 里挑 MoMo 的 type；无列表时默认 momo（Stripe 合法类型，不是 momo_wallet）。"""
    methods = opll_collect_payment_method_types(init_payload or {})
    for cand in ("momo", "momo_wallet", "momo_vn", "momowallet"):
        if cand in methods:
            return cand
    return "momo"


def opll_qr_data_url(payload: str, *, box_size: int = 6, border: int = 2) -> str:
    """把支付链接/复制码编码成 PNG data URL，供前端直接展示。"""
    text = str(payload or "").strip()
    if not text:
        return ""
    try:
        import qrcode  # type: ignore
        from io import BytesIO

        img = qrcode.make(text, box_size=box_size, border=border)
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def opll_extract_momo_artifacts(payload) -> dict:
    """从 Stripe confirm/next_action 里尽量捞 MoMo 相关链接与二维码。"""
    artifacts = {
        "pay_url": "",
        "qr_url": "",
        "qr_url_png": "",
        "qr_url_svg": "",
        "next_action_type": "",
    }

    def add_url(text: str, key_hint: str = "") -> None:
        t = str(text or "").strip()
        if not t.startswith(("http://", "https://")):
            return
        low = t.lower()
        if opll_is_momo_url(t):
            artifacts["pay_url"] = artifacts["pay_url"] or t
        if "qr.stripe.com" in low or "image_url" in key_hint or "qr" in key_hint:
            artifacts["qr_url"] = artifacts["qr_url"] or t
            if low.endswith(".png") or "png" in key_hint:
                artifacts["qr_url_png"] = artifacts["qr_url_png"] or t
            if low.endswith(".svg") or "svg" in key_hint:
                artifacts["qr_url_svg"] = artifacts["qr_url_svg"] or t

    def walk(value, key_hint: str = "") -> None:
        if isinstance(value, dict):
            if key_hint == "next_action" and not artifacts["next_action_type"]:
                artifacts["next_action_type"] = str(value.get("type") or "")
            for k, v in value.items():
                nk = str(k or "").lower()
                if isinstance(v, str):
                    add_url(v.strip(), nk)
                walk(v, nk)
        elif isinstance(value, list):
            for item in value:
                walk(item, key_hint)

    walk(payload)
    return artifacts


def opll_extract_pix_artifacts(payload) -> dict:
    """Extract PIX payment artifacts from Stripe confirm/poll payloads."""
    artifacts = {
        "pay_url": "",
        "hooks_url": "",
        "pix_copy_code": "",
        "qr_url": "",
        "qr_url_png": "",
        "qr_url_svg": "",
        "hosted_instructions_url": "",
        "next_action_type": "",
    }

    def add_url(text: str, key_hint: str = "") -> None:
        t = str(text or "").strip()
        if not t.startswith(("http://", "https://")):
            return
        low = t.lower()
        if "https://hooks.stripe.com/" in low or "//hooks.stripe.com/" in low:
            artifacts["hooks_url"] = artifacts["hooks_url"] or t
            artifacts["pay_url"] = artifacts["pay_url"] or t
        if "hosted_instructions" in key_hint or "instructions" in key_hint:
            artifacts["hosted_instructions_url"] = artifacts["hosted_instructions_url"] or t
            artifacts["pay_url"] = artifacts["pay_url"] or t
        if "qr.stripe.com" in low or "image_url" in key_hint or "qr" in key_hint:
            artifacts["qr_url"] = artifacts["qr_url"] or t
            if low.endswith(".png") or "png" in key_hint:
                artifacts["qr_url_png"] = artifacts["qr_url_png"] or t
            if low.endswith(".svg") or "svg" in key_hint:
                artifacts["qr_url_svg"] = artifacts["qr_url_svg"] or t

    def walk(value, key_hint: str = "") -> None:
        if isinstance(value, dict):
            if key_hint == "next_action" and not artifacts["next_action_type"]:
                artifacts["next_action_type"] = str(value.get("type") or "")
            for k, v in value.items():
                nk = str(k or "").lower()
                if isinstance(v, str):
                    text = v.strip()
                    if text.startswith("000201") and len(text) > 40:
                        artifacts["pix_copy_code"] = artifacts["pix_copy_code"] or text
                    if nk in ("data", "pix_code", "copy_code", "payload") and text.startswith("000201"):
                        artifacts["pix_copy_code"] = artifacts["pix_copy_code"] or text
                    add_url(text, nk)
                walk(v, nk)
        elif isinstance(value, list):
            for item in value:
                walk(item, key_hint)

    walk(payload)
    return artifacts

def opll_payment_page_status(stripe: requests.Session, cs_id: str, stripe_pk: str, ctx: dict) -> dict:
    params = {
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[session_id]": ctx.get("elements_session_id") or "",
        "elements_session_client[stripe_js_id]": ctx.get("stripe_js_id") or "",
        "elements_session_client[locale]": "pt-BR",
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
    }
    response = stripe.get(f"https://api.stripe.com/v1/payment_pages/{cs_id}", params=params, timeout=PAY_LONG_LINK_TIMEOUT)
    if response.status_code >= 400:
        raise RuntimeError(f"stripe status failed: HTTP {response.status_code} {response.text[:500]}")
    return response.json() or {}

def _pix_once(
    access_token: str,
    create_proxy_url: str,
    followup_proxy_url: str,
    approve_proxy_url: str,
    target_amount: str,
    payment_email: str,
    promo_max_attempts: int,
    artifact_poll_seconds: int,
) -> dict:
    """单次 PIX 提链（不含代理重试）。"""
    email = str(payment_email or "").strip() or token_profile_email(access_token)
    checkout = opll_create_checkout_with_opts(
        access_token,
        "BR",
        "BRL",
        create_proxy_url,
        checkout_ui_mode="custom",
    )
    cs_id = checkout["cs_id"]

    # promotion 刷新 0 元试用（失败则用原 checkout 继续，由后续 amount check 兜底）
    max_attempts = max(1, min(int(promo_max_attempts or 30), 60))
    promo_errors: list[dict] = []
    for attempt in range(1, max_attempts + 1):
        # 每次 promotion 换 sid，贴近开源「轮换出口」行为
        promo_proxy = randomize_proxy_sid(followup_proxy_url) if followup_proxy_url else ""
        try:
            opll_update_checkout_promotion(access_token, checkout, promo_proxy)
            break
        except Exception as exc:
            promo_errors.append({"attempt": attempt, "error": str(exc)[:400]})
            if attempt >= max_attempts:
                break
            time.sleep(0.8)

    # Stripe 优先 plain requests：住宅代理上 curl_cffi 易 56 断连
    stripe = opll_build_stripe_session(create_proxy_url, engine="plain")
    try:
        init_payload = opll_stripe_init(
            cs_id,
            "BR",
            "BRL",
            create_proxy_url,
            payment_locale="pt-BR",
            stripe=stripe,
            checkout=checkout,
        )
    except Exception as exc:
        if not is_proxy_retryable_error(exc):
            raise
        # 换 sid 后再试一次 plain
        create_proxy_url = randomize_proxy_sid(create_proxy_url) if create_proxy_url else ""
        stripe = opll_build_stripe_session(create_proxy_url, engine="plain")
        init_payload = opll_stripe_init(
            cs_id,
            "BR",
            "BRL",
            create_proxy_url,
            payment_locale="pt-BR",
            stripe=stripe,
            checkout=checkout,
        )
    stripe_hosted_url = str(init_payload.get("stripe_hosted_url") or "").strip()
    if not stripe_hosted_url:
        raise RuntimeError(f"stripe init response missing stripe_hosted_url, keys={sorted(init_payload.keys())}")

    methods = ensure_pix_supported(init_payload)
    stripe_amount, stripe_amount_source = opll_stripe_amount_info(init_payload)
    # PIX 默认要求 0 元试用；仅当用户显式指定非 0 target 时放行
    target_norm = str(target_amount or "").strip()
    if str(stripe_amount) != "0" and target_norm in {"", "0"}:
        raise AmountMismatchError(f"PIX 需要 0 元试用，但 Stripe 返回 {stripe_amount}")

    stripe_pk = opll_stripe_key_for_checkout(checkout)
    ctx = opll_stripe_context(init_payload, payment_locale="pt-BR")
    if not ctx.get("currency"):
        ctx["currency"] = "brl"
    if not ctx.get("checkout_amount"):
        ctx["checkout_amount"] = stripe_amount

    billing = opll_br_billing_with_cpf(email)
    pm_id = opll_stripe_create_paypal_method(stripe, cs_id, ctx, billing, stripe_pk, "pix")
    confirm_payload = opll_stripe_confirm(
        stripe, cs_id, pm_id, stripe_pk, init_payload, ctx, checkout, stripe_hosted_url, "pix"
    )
    submission = opll_find_submission_attempt(confirm_payload)
    submission_state = str(submission.get("state") or "") if isinstance(submission, dict) else ""
    artifacts = opll_extract_pix_artifacts(confirm_payload)

    poll_payload: dict = {}
    if not (artifacts.get("pay_url") or artifacts.get("pix_copy_code") or artifacts.get("qr_url")):
        if submission_state == "requires_approval":
            opll_chatgpt_approve_with_retry(access_token, cs_id, checkout, approve_proxy_url)
        deadline = time.time() + max(1, int(artifact_poll_seconds or 45))
        while time.time() <= deadline:
            poll_payload = opll_payment_page_status(stripe, cs_id, stripe_pk, ctx)
            poll_artifacts = opll_extract_pix_artifacts(poll_payload)
            artifacts.update({k: v for k, v in poll_artifacts.items() if v and not artifacts.get(k)})
            if artifacts.get("pay_url") or artifacts.get("pix_copy_code") or artifacts.get("qr_url"):
                break
            time.sleep(2)

    hosted_long_url = opll_to_openai_pay_url(stripe_hosted_url)
    long_url = (
        artifacts.get("pay_url")
        or artifacts.get("hooks_url")
        or hosted_long_url
        or ""
    )
    if not (long_url or artifacts.get("pix_copy_code") or artifacts.get("qr_url")):
        raise RuntimeError("pix_artifacts_missing: confirm/poll 未返回付款链接、复制码或二维码")

    result = {
        **checkout,
        "billing_country": "BR",
        "currency": "BRL",
        "payment_method_country": "BR",
        "payment_method_id": pm_id,
        "payment_method_type": "pix",
        "stripe_hosted_url": stripe_hosted_url,
        "stripe_redirect_url": artifacts.get("pay_url") or "",
        "provider_redirect_url": long_url,
        "long_url": long_url or hosted_long_url,
        "pay_url": artifacts.get("pay_url") or "",
        "hooks_url": artifacts.get("hooks_url") or "",
        "pix_copy_code": artifacts.get("pix_copy_code") or "",
        "qr_url": artifacts.get("qr_url") or artifacts.get("qr_url_png") or artifacts.get("qr_url_svg") or "",
        "submission_state": submission_state,
        "methods": methods,
        "stripe_amount": stripe_amount,
        "stripe_amount_source": stripe_amount_source,
        "mode": "pix",
        "promo_errors": promo_errors,
        "billing_name": billing.get("name") or "",
        "billing_email": billing.get("email") or "",
    }
    return opll_apply_amount_check(result, target_amount)


def generate_opll_pix_long_link(
    access_token: str,
    create_proxy_url: str = "",
    followup_proxy_url: str = "",
    approve_proxy_url: str = "",
    target_amount: str = "",
    payment_email: str = "",
    promo_max_attempts: int = 30,
    artifact_poll_seconds: int = 45,
    proxy_retries: int = 5,
) -> dict:
    """
    PIX 提链：BR/BRL checkout → promotion 刷新 0 元试用 → 创建 PIX PM → confirm → 提取 pay_url/复制码/二维码。

    代理约定：
    - create_proxy_url: 巴西出链/Stripe（checkout + provider）
    - followup_proxy_url: promotion 刷新线路（可与巴西不同）
    - approve_proxy_url: ChatGPT approve

    代理连接类错误（ConnectionReset 等）会自动换 sid 重试，对齐开源 pix-core。
    """
    base_create = normalize_proxy_url(create_proxy_url)
    base_follow = normalize_proxy_url(followup_proxy_url) or base_create
    base_approve = normalize_proxy_url(approve_proxy_url) or base_create
    attempts = max(1, min(int(proxy_retries or 5), 10))
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        create_p = randomize_proxy_sid(base_create) if base_create else ""
        follow_p = randomize_proxy_sid(base_follow) if base_follow else create_p
        approve_p = randomize_proxy_sid(base_approve) if base_approve else create_p
        try:
            return _pix_once(
                access_token,
                create_p,
                follow_p,
                approve_p,
                target_amount,
                payment_email,
                promo_max_attempts,
                artifact_poll_seconds,
            )
        except AmountMismatchError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not is_proxy_retryable_error(exc):
                raise
            time.sleep(0.8 + 0.2 * attempt)

    raise last_error if (last_error := last_exc) else RuntimeError("PIX 提取失败")

def generate_opll_gopay_long_link(access_token: str, country: str, currency: str, create_proxy_url: str = "", followup_proxy_url: str = "", approve_proxy_url: str = "", target_amount: str = "") -> dict:
    create_proxy_url = str(create_proxy_url or "").strip()
    followup_proxy_url = str(followup_proxy_url or "").strip() or create_proxy_url
    approve_proxy_url = str(approve_proxy_url or "").strip() or followup_proxy_url
    checkout_country = normalize_opll_country(country or "ID")
    # 与 PIX 一致：本地钱包走 custom，否则 Stripe 常只吐 card
    checkout = opll_create_checkout_with_opts(
        access_token,
        checkout_country,
        currency_for_country(checkout_country),
        create_proxy_url,
        checkout_ui_mode="custom",
    )
    stripe = opll_build_stripe_session(followup_proxy_url)
    init_payload = opll_stripe_init(
        checkout["cs_id"],
        checkout["billing_country"],
        checkout["currency"],
        followup_proxy_url,
        payment_locale="id",
        stripe=stripe,
        checkout=checkout,
    )
    stripe_hosted_url = str(init_payload.get("stripe_hosted_url") or "").strip()
    if not stripe_hosted_url:
        raise RuntimeError(f"stripe init response missing stripe_hosted_url, keys={sorted(init_payload.keys())}")
    hosted_long_url = opll_to_openai_pay_url(stripe_hosted_url)
    stripe_pk = opll_stripe_key_for_checkout(checkout)
    ctx = opll_stripe_context(init_payload)
    if not ctx.get("currency"):
        ctx["currency"] = str(checkout.get("currency") or "").lower()
    stripe_amount, stripe_amount_source = opll_stripe_amount_info(init_payload)
    pm_id = opll_stripe_create_paypal_method(stripe, checkout["cs_id"], ctx, opll_billing_for_country("ID"), stripe_pk, "gopay")
    confirm_payload = opll_stripe_confirm(stripe, checkout["cs_id"], pm_id, stripe_pk, init_payload, ctx, checkout, stripe_hosted_url, "gopay")
    stripe_redirect_url = opll_provider_redirect_url_after_confirm(access_token, stripe, confirm_payload, checkout["cs_id"], stripe_pk, ctx, checkout, approve_proxy_url)
    provider_url = opll_resolve_external_redirect(stripe, stripe_redirect_url, preferred_hosts=()) if stripe_redirect_url else ""
    long_url = provider_url or stripe_redirect_url or hosted_long_url
    if not long_url or not opll_is_external_url(long_url) or opll_is_ignored_resource_url(long_url):
        raise RuntimeError(f"未提取到有效 GoPay 跳转长链；当前结果: {long_url or stripe_redirect_url or stripe_hosted_url}")
    return opll_apply_amount_check({
        **checkout,
        "payment_method_country": "ID",
        "payment_method_id": pm_id,
        "stripe_hosted_url": stripe_hosted_url,
        "stripe_redirect_url": stripe_redirect_url,
        "provider_redirect_url": long_url,
        "long_url": long_url,
        "payment_method_type": "gopay",
        "stripe_amount": stripe_amount,
        "stripe_amount_source": stripe_amount_source,
    }, target_amount)


def generate_opll_momo_long_link(
    access_token: str,
    create_proxy_url: str = "",
    followup_proxy_url: str = "",
    approve_proxy_url: str = "",
    target_amount: str = "",
    payment_email: str = "",
) -> dict:
    """越南 MoMo 提链：VN/VND checkout → 创建 MoMo PM → confirm/approve → 跟随到 payment.momo.vn。

    产物：
      - long_url / pay_url: https://payment.momo.vn/v2/gateway/pay?t=...&s=...
      - qr_url / qr_data_url: 对应支付链接的二维码（优先 Stripe 返回图，否则本地生成）

    路径对齐 PIX：
      custom 建单（可无 promo）→ promotion 刷 0 元 → tax 同步 → init → 校验 momo → PM/confirm
    """
    create_proxy_url = str(create_proxy_url or "").strip()
    followup_proxy_url = str(followup_proxy_url or "").strip() or create_proxy_url
    approve_proxy_url = str(approve_proxy_url or "").strip() or followup_proxy_url
    email = str(payment_email or "").strip() or token_profile_email(access_token)

    # 1) custom 建单。0 元意图时先无 promo 创建，再用 promotion update 刷试用（对齐 PIX/PayPal）
    want_zero = str(target_amount or "").strip() in {"", "0"}
    checkout = opll_create_checkout_with_opts(
        access_token,
        "VN",
        currency_for_country("VN"),
        create_proxy_url,
        checkout_ui_mode="custom",
        use_promo=not want_zero,
        promo_campaign_id="plus-1-month-free" if not want_zero else "",
    )
    cs_id = checkout["cs_id"]

    # 2) promotion 刷新 0 元（失败不阻断，后续 amount check / methods 再判定）
    if want_zero:
        for attempt in range(1, 4):
            promo_proxy = randomize_proxy_sid(followup_proxy_url) if followup_proxy_url else create_proxy_url
            try:
                opll_update_checkout_promotion(access_token, checkout, promo_proxy)
                break
            except Exception:
                if attempt >= 3:
                    break
                time.sleep(0.6)

    # 3) Stripe init（plain + 住宅代理）
    stripe = opll_build_stripe_session(followup_proxy_url or create_proxy_url, engine="plain")
    try:
        init_payload = opll_stripe_init(
            cs_id,
            "VN",
            "VND",
            followup_proxy_url or create_proxy_url,
            payment_locale="vi",
            stripe=stripe,
            checkout=checkout,
        )
    except Exception as exc:
        if not is_proxy_retryable_error(exc):
            raise
        followup_proxy_url = randomize_proxy_sid(followup_proxy_url or create_proxy_url)
        stripe = opll_build_stripe_session(followup_proxy_url, engine="plain")
        init_payload = opll_stripe_init(
            cs_id,
            "VN",
            "VND",
            followup_proxy_url,
            payment_locale="vi",
            stripe=stripe,
            checkout=checkout,
        )

    billing = opll_billing_for_country("VN", payment_email=email or "")
    # 4) 税区同步后再 init（可能影响本地支付方式；失败则用原 init）
    try:
        init_payload = opll_sync_billing_tax_and_reinit(
            access_token,
            checkout,
            billing,
            stripe,
            proxy_url=followup_proxy_url or create_proxy_url,
            payment_locale="vi",
            init_payload=init_payload,
        ) or init_payload
    except Exception:
        pass

    stripe_hosted_url = str(init_payload.get("stripe_hosted_url") or "").strip()
    if not stripe_hosted_url:
        raise RuntimeError(f"stripe init response missing stripe_hosted_url, keys={sorted(init_payload.keys())}")
    methods = ensure_momo_supported(init_payload)
    pm_type = opll_pick_momo_method_type(init_payload)
    hosted_long_url = opll_to_openai_pay_url(stripe_hosted_url)
    stripe_pk = opll_stripe_key_for_checkout(checkout)
    ctx = opll_stripe_context(init_payload, payment_locale="vi")
    if not ctx.get("currency"):
        ctx["currency"] = str(checkout.get("currency") or "vnd").lower()
    stripe_amount, stripe_amount_source = opll_stripe_amount_info(init_payload)
    pm_id = opll_stripe_create_paypal_method(
        stripe,
        checkout["cs_id"],
        ctx,
        billing,
        stripe_pk,
        pm_type,
    )
    confirm_payload = opll_stripe_confirm(
        stripe,
        checkout["cs_id"],
        pm_id,
        stripe_pk,
        init_payload,
        ctx,
        checkout,
        stripe_hosted_url,
        pm_type,
    )
    momo_artifacts = opll_extract_momo_artifacts(confirm_payload)
    stripe_redirect_url = opll_provider_redirect_url_after_confirm(
        access_token,
        stripe,
        confirm_payload,
        checkout["cs_id"],
        stripe_pk,
        ctx,
        checkout,
        approve_proxy_url,
    )
    # 跟随 Stripe/pm-redirects 直到 payment.momo.vn
    provider_url = ""
    if stripe_redirect_url:
        if opll_is_momo_url(stripe_redirect_url):
            provider_url = stripe_redirect_url
        else:
            provider_url = opll_resolve_external_redirect(
                stripe,
                stripe_redirect_url,
                preferred_hosts=("momo.vn", "payment.momo.vn"),
            )
            # resolve 对非 paypal 的 preferred_hosts 只在 ba_token 时早退；再扫一遍 URL
            if provider_url and not opll_is_momo_url(provider_url):
                # 若仍停在中间页，再从当前跳转链里找 momo
                for item in re.findall(r"https?://[^\s\"'<>]+", provider_url + " " + stripe_redirect_url):
                    item = item.rstrip("),.;]")
                    if opll_is_momo_url(item):
                        provider_url = item
                        break
    long_url = ""
    for cand in (
        momo_artifacts.get("pay_url"),
        provider_url,
        stripe_redirect_url,
        hosted_long_url,
    ):
        c = str(cand or "").strip()
        if c and opll_is_momo_url(c):
            long_url = c
            break
    if not long_url:
        # 兜底：外部长链（非资源 URL）也可返回，便于排障
        for cand in (provider_url, stripe_redirect_url):
            c = str(cand or "").strip()
            if c and opll_is_external_url(c) and not opll_is_ignored_resource_url(c):
                long_url = c
                break
    if not long_url or not opll_is_external_url(long_url) or opll_is_ignored_resource_url(long_url):
        raise RuntimeError(
            "未提取到有效 MoMo 跳转长链（期望 payment.momo.vn/v2/gateway/pay?...）；"
            f"当前结果: {provider_url or stripe_redirect_url or stripe_hosted_url}"
        )
    if not opll_is_momo_url(long_url):
        raise RuntimeError(
            f"已拿到外部跳转但不是 MoMo 网关：{long_url[:200]}。"
            "请确认 VN 账单 + 越南出口代理，且 checkout 含 momo/momo_wallet。"
        )

    # 二维码：优先 Stripe 返回图；否则把支付链接本地编码成 data URL
    stripe_qr = (
        momo_artifacts.get("qr_url")
        or momo_artifacts.get("qr_url_png")
        or momo_artifacts.get("qr_url_svg")
        or ""
    )
    qr_data_url = opll_qr_data_url(long_url)
    qr_url = str(stripe_qr or qr_data_url or "").strip()
    if not qr_url:
        raise RuntimeError(
            "已拿到 MoMo 支付链接，但二维码生成失败（缺少 qrcode 依赖或编码异常）。"
            f"链接: {long_url[:160]}"
        )

    return opll_apply_amount_check(
        {
            **checkout,
            "billing_country": "VN",
            "currency": "VND",
            "payment_method_country": "VN",
            "payment_method_id": pm_id,
            "payment_method_type": pm_type,
            "methods": methods,
            "stripe_hosted_url": stripe_hosted_url,
            "stripe_redirect_url": stripe_redirect_url,
            "provider_redirect_url": long_url,
            "long_url": long_url,
            "pay_url": long_url,
            "qr_url": qr_url,
            "qr_data_url": qr_data_url,
            "mode": "momo",
            "stripe_amount": stripe_amount,
            "stripe_amount_source": stripe_amount_source,
            "billing_name": billing.get("name") or "",
            "billing_email": billing.get("email") or "",
        },
        target_amount,
    )

def generate_opll_hosted_long_link(
    access_token: str,
    country: str,
    currency: str,
    create_proxy_url: str = "",
    followup_proxy_url: str = "",
    approve_proxy_url: str = "",
    target_amount: str = "",
) -> dict:
    create_proxy_url = str(create_proxy_url or "").strip()
    followup_proxy_url = str(followup_proxy_url or "").strip() or create_proxy_url
    approve_proxy_url = str(approve_proxy_url or "").strip() or followup_proxy_url
    checkout = opll_create_checkout(access_token, country, currency, create_proxy_url)
    if str(checkout.get("cs_id") or "").startswith("oaics_"):
        long_url = build_internal_checkout_url(
            checkout["cs_id"],
            checkout["billing_country"],
            checkout.get("processor_entity", ""),
        )
        target_norm = str(target_amount or "").strip()
        result = {
            **checkout,
            "stripe_hosted_url": "",
            "long_url": long_url,
            "stripe_amount": "",
            "stripe_amount_source": "openai_hosted_checkout_unverified",
            "target_amount": target_norm,
        }
        if target_norm in {"0", "0.0", "0.00"}:
            promo_payload = opll_update_checkout_promotion(access_token, checkout, followup_proxy_url)
            checkout_amount, checkout_amount_source = opll_openai_checkout_amount_info(promo_payload)
            result.update(
                {
                    "stripe_amount": checkout_amount,
                    "stripe_amount_source": checkout_amount_source,
                    "openai_checkout_total": checkout_amount,
                    "openai_checkout_amount_source": checkout_amount_source,
                }
            )
            return opll_apply_amount_check(result, target_amount)
        if target_norm:
            promo_payload = opll_update_checkout_promotion(access_token, checkout, followup_proxy_url)
            checkout_amount, checkout_amount_source = opll_openai_checkout_amount_info(promo_payload)
            result.update({"stripe_amount": checkout_amount, "stripe_amount_source": checkout_amount_source})
            return opll_apply_amount_check(result, target_amount)
        return opll_apply_amount_check(result, target_amount)
    target_norm = str(target_amount or "").strip()
    promo_update_error = ""
    if target_norm in {"0", "0.0", "0.00"}:
        try:
            promo_payload = opll_update_checkout_promotion(access_token, checkout, followup_proxy_url)
            checkout_amount, checkout_amount_source = opll_openai_checkout_amount_info(promo_payload)
            if checkout_amount == "0":
                long_url = build_internal_checkout_url(
                    checkout["cs_id"],
                    checkout["billing_country"],
                    checkout.get("processor_entity", ""),
                )
                return opll_apply_amount_check(
                    {
                        **checkout,
                        "stripe_hosted_url": "",
                        "long_url": long_url,
                        "stripe_amount": checkout_amount,
                        "stripe_amount_source": checkout_amount_source,
                        "openai_checkout_total": checkout_amount,
                        "openai_checkout_amount_source": checkout_amount_source,
                    },
                    target_amount,
                )
            if checkout_amount:
                raise AmountMismatchError(target_norm, checkout_amount, checkout_amount_source)
        except Exception as exc:
            if isinstance(exc, AmountMismatchError):
                raise
            promo_update_error = opll_short_error(str(exc), 180)
    init_payload = opll_stripe_init(checkout["cs_id"], checkout["billing_country"], checkout["currency"], followup_proxy_url, checkout=checkout)
    stripe_hosted_url = str(init_payload.get("stripe_hosted_url") or "").strip()
    if not stripe_hosted_url:
        raise RuntimeError(f"stripe init response missing stripe_hosted_url, keys={sorted(init_payload.keys())}")
    stripe_amount, stripe_amount_source = opll_stripe_amount_info(init_payload)
    if promo_update_error:
        stripe_amount_source = f"{stripe_amount_source}; promotion_update_error={promo_update_error}"
    long_url = opll_to_openai_pay_url(stripe_hosted_url) or opll_stripe_checkout_long_url(
        checkout["cs_id"], checkout["billing_country"], checkout.get("processor_entity", "")
    )
    return opll_apply_amount_check({
        **checkout,
        "stripe_hosted_url": stripe_hosted_url,
        "long_url": long_url,
        "stripe_amount": stripe_amount,
        "stripe_amount_source": stripe_amount_source,
    }, target_amount)

def build_internal_checkout_url(cs_id: str, country: str = "US", processor_entity: str = "") -> str:
    entity = opll_processor_entity_for_country(country, processor_entity)
    return f"https://chatgpt.com/checkout/{entity}/{cs_id}"

def enrich_link_result(result: dict) -> dict:
    """Attach dual links used by mature tools: external long + internal short."""
    if not isinstance(result, dict):
        return result
    cs_id = str(result.get("cs_id") or "").strip()
    is_openai_checkout = cs_id.startswith("oaics_")
    country = str(result.get("billing_country") or result.get("used_country") or "US")
    entity = str(result.get("processor_entity") or "")
    long_url = str(result.get("long_url") or result.get("provider_redirect_url") or "").strip()
    hosted = str(result.get("stripe_hosted_url") or "").strip()
    if not long_url and hosted:
        long_url = opll_to_openai_pay_url(hosted)
    if not long_url and is_openai_checkout:
        long_url = build_internal_checkout_url(cs_id, country, entity)
    if not long_url and cs_id and not is_openai_checkout:
        long_url = opll_to_openai_pay_url(opll_stripe_checkout_long_url(cs_id, country, entity)) or f"https://pay.openai.com/c/pay/{cs_id}"
    if not hosted and cs_id and not is_openai_checkout:
        hosted = f"https://checkout.stripe.com/c/pay/{cs_id}"
    internal = build_internal_checkout_url(cs_id, country, entity) if cs_id else ""
    result["long_url"] = long_url
    result["external_url"] = long_url
    result["stripe_hosted_url"] = hosted
    result["internal_url"] = internal
    result["chatgpt_short_url"] = internal
    result["pay_openai_url"] = long_url if "pay.openai.com" in long_url else (opll_to_openai_pay_url(hosted) if hosted else long_url)
    return result

def generate_link(
    access_token: str,
    country: str = "US",
    mode: str = "hosted",
    currency: str = "",
    create_proxy: str = "",
    followup_proxy: str = "",
    approve_proxy: str = "",
    target_amount: str = "",
    auto_match_proxy_country: bool = False,
    plan_name: str = "chatgptplusplan",
    use_promo: bool = True,
    promo_code: str = "",
    team_seats: int = 5,
    workspace_name: str = "",
    checkout_ui_mode: str = "",
    payment_locale: str = "en",
    payment_email: str = "",
) -> dict:
    mode_norm = str(mode or "hosted").strip().lower()
    # create/follow：单线；approve：可保留多 sid 池（blocked / setup 失败时换线）
    create_proxy = normalize_proxy_url(create_proxy)
    followup_proxy = normalize_proxy_url(followup_proxy) or create_proxy
    approve_proxy = normalize_proxy_pool_text(approve_proxy) or followup_proxy
    country = normalize_opll_country(country)
    prefer_countries: list[str] = []
    exit_country = ""

    # 代理 URL 原样使用：不改 region/sid、不强制某国出口；仅 auto_match 时才跟出口改账单国
    if create_proxy:
        try:
            exit_country = detect_proxy_exit_country(create_proxy)
        except Exception:
            exit_country = ""
        if exit_country and auto_match_proxy_country:
            prefer_countries.append(exit_country)
            if country != exit_country:
                country = exit_country

    currency = str(currency or currency_for_country(country)).upper()
    # plan context for checkout create (Plus/Team/promo)
    # 对齐 oaipay：PayPal/Hosted → hosted；PIX/GoPay/MoMo → custom
    ui_mode = str(checkout_ui_mode or "").strip().lower()
    if not ui_mode:
        if mode_norm in {"pix", "pix_br", "brazil_pix", "gopay", "go-pay", "ideal", "momo", "momo_vn", "momo_wallet"}:
            ui_mode = "custom"
        else:
            ui_mode = "hosted"
    global _ACTIVE_CHECKOUT_OPTS
    _ACTIVE_CHECKOUT_OPTS = {
        "plan_name": plan_name or "chatgptplusplan",
        "use_promo": bool(use_promo),
        "promo_campaign_id": "plus-1-month-free",
        "promo_code": str(promo_code or "").strip(),
        "team_seats": int(team_seats or 5),
        "workspace_name": str(workspace_name or ""),
        "checkout_ui_mode": ui_mode,
        "entry_point": "all_plans_pricing_modal",
    }

    def _attach_meta(result: dict, used_country: str = "") -> dict:
        if exit_country:
            result["proxy_exit_country"] = exit_country
        if used_country:
            result["used_country"] = used_country
        result.setdefault("mode", mode_norm)
        return result

    if mode_norm in {"hosted", "stripe", "card", "apple"}:
        # Keep user country first unless auto-match enabled; still soft-fallback on billing mismatch.
        candidates = [country]
        if auto_match_proxy_country:
            candidates.extend(prefer_countries)
            candidates.extend(["US", "DE", "SG", "JP", "MY", "GB"])
        last_err = None
        seen = set()
        for c in candidates:
            c = normalize_opll_country(c)
            if c in seen:
                continue
            seen.add(c)
            try:
                result = generate_opll_hosted_long_link(
                    access_token,
                    c,
                    currency_for_country(c) if auto_match_proxy_country else (currency or currency_for_country(c)),
                    create_proxy,
                    followup_proxy,
                    approve_proxy,
                    target_amount=target_amount,
                )
                return enrich_link_result(_attach_meta(result, c))
            except AmountMismatchError:
                raise
            except Exception as exc:
                last_err = exc
                msg = str(exc).lower()
                if auto_match_proxy_country and (
                    "billing country must match request country" in msg or "checkout create failed" in msg
                ):
                    continue
                raise
        raise RuntimeError(str(last_err) if last_err else "hosted link failed")

    if mode_norm in {"pix", "pix_br", "brazil_pix"}:
        result = generate_opll_pix_long_link(
            access_token,
            create_proxy,
            followup_proxy,
            approve_proxy,
            target_amount,
            payment_email=payment_email or "",
        )
        return enrich_link_result(_attach_meta(result, "BR"))

    if mode_norm in {"gopay", "go-pay"}:
        result = generate_opll_gopay_long_link(
            access_token,
            "ID",
            currency_for_country("ID"),
            create_proxy,
            followup_proxy,
            approve_proxy,
            target_amount,
        )
        return enrich_link_result(_attach_meta(result, "ID"))

    if mode_norm in {"momo", "momo_vn", "momo_wallet", "vn_momo"}:
        result = generate_opll_momo_long_link(
            access_token,
            create_proxy,
            followup_proxy,
            approve_proxy,
            target_amount,
            payment_email=payment_email or "",
        )
        return enrich_link_result(_attach_meta(result, "VN"))

    result = generate_opll_paypal_long_link(
        access_token,
        country,
        currency or currency_for_country(country),
        create_proxy,
        followup_proxy,
        approve_proxy,
        target_amount,
        # 默认不写死德国、不串国；仅 auto_match 时用出口国做 prefer/回退
        prefer_countries=prefer_countries if auto_match_proxy_country else [],
        payment_locale=payment_locale or "en",
        payment_email=payment_email or "",
        allow_country_fallback=bool(auto_match_proxy_country),
        proxy_exit_country=exit_country,
    )
    return enrich_link_result(_attach_meta(result, result.get("billing_country") or country))

def parse_expired_time(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return int(datetime.fromisoformat(text).timestamp())
    except Exception:
        return 0

def resolve_organization_id(id_claims: dict, access_claims: dict) -> str:
    id_auth = get_nested_record(id_claims, "https://api.openai.com/auth")
    access_auth = get_nested_record(access_claims, "https://api.openai.com/auth")
    organizations = id_auth.get("organizations") if isinstance(id_auth.get("organizations"), list) else access_auth.get("organizations")
    if not isinstance(organizations, list) or not organizations:
        return ""

