from __future__ import annotations

import importlib
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from statistics import mean

import requests


TIMEOUT = 20

STATUS_OK_TWSE = "\u66f4\u65b0\u6210\u529f\uff08TWSE\uff09"
STATUS_OK_TPEX = "\u66f4\u65b0\u6210\u529f\uff08TPEX\uff09"
STATUS_OK_YAHOO_HISTORY = "\u66f4\u65b0\u6210\u529f\uff08Yahoo\u6b77\u53f2\u5099\u63f4\uff09"
STATUS_OK_YAHOO_FALLBACK = "\u66f4\u65b0\u6210\u529f\uff08Yahoo\u5099\u63f4\uff09"
STATUS_CODE_NOT_FOUND = "\u4ee3\u865f\u4e0d\u5b58\u5728\uff08TWSE/TPEX\uff09"
STATUS_SOURCE_DOWN = "\u8cc7\u6599\u6e90\u66ab\u6642\u4e0d\u53ef\u7528"
STATUS_MA_UNAVAILABLE = "\u8cc7\u6599\u7570\u5e38\uff08\u7121\u6cd5\u53d6\u5f97\u5747\u7dda\uff09"
STATUS_MA_UNAVAILABLE_WITH_REASON = "\u8cc7\u6599\u7570\u5e38\uff08\u7121\u6cd5\u53d6\u5f97\u5747\u7dda\uff1a{reason}\uff09"
STATUS_GOODINFO_PARSE_FAIL = "\u8cc7\u6599\u7570\u5e38\uff08Goodinfo\u89e3\u6790\u5931\u6557\uff09"
STATUS_GOODINFO_BLOCKED = "\u8cc7\u6599\u7570\u5e38\uff08Goodinfo\u9023\u7dda\u53d7\u9650\uff09"
STATUS_MEGA_NOT_CONFIGURED = "MegaAPI \u672a\u8a2d\u5b9a\uff0c\u8acb\u8a2d\u5b9a MEGA_QUOTE_HOST / MEGA_QUOTE_ID / MEGA_QUOTE_PASSWORD"
STATUS_MEGA_SDK_MISSING = "MegaAPI SDK \u672a\u5b89\u88dd\uff0c\u8acb\u5728\u672c\u6a5f Windows \u5b89\u88dd megaSpeedy/pySpeedy"
STATUS_MEGA_LOGON_FAILED = "MegaAPI \u884c\u60c5\u767b\u5165\u5931\u6557"
STATUS_MEGA_TIMEOUT = "MegaAPI \u7b49\u5f85\u6210\u4ea4\u4e8b\u4ef6\u903e\u6642\uff0c\u4fdd\u7559\u65e2\u6709\u50f9\u683c"
STATUS_OK_MEGA = "\u66f4\u65b0\u6210\u529f\uff08MegaAPI \u5373\u6642\u884c\u60c5\uff09"


def parse_float(value: object) -> float | None:
    if value in (None, "", "--", "---", "----", "X0.00"):
        return None
    text = str(value).replace(",", "").replace("X", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_stock_code(value: object) -> str:
    raw = str(value).strip()
    if not raw:
        return ""
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return raw
    return digits.zfill(4) if len(digits) < 4 else digits


def get_json_with_retry(url: str, params: dict | None = None, retries: int = 2) -> list | dict:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    last_error = None
    for _ in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def month_starts(count: int = 6) -> list[datetime]:
    today = datetime.today()
    cursor = datetime(today.year, today.month, 1)
    out: list[datetime] = []
    for _ in range(count):
        out.append(cursor)
        if cursor.month == 1:
            cursor = datetime(cursor.year - 1, 12, 1)
        else:
            cursor = datetime(cursor.year, cursor.month - 1, 1)
    return out


def roc_month(dt: datetime) -> str:
    return f"{dt.year - 1911}/{dt.month:02d}"


def compute_mas(closes: list[float]) -> tuple[float, float, float, float]:
    if len(closes) < 20:
        raise ValueError("not_enough_data")
    ma5 = round(mean(closes[-5:]), 2)
    ma10 = round(mean(closes[-10:]), 2)
    ma20 = round(mean(closes[-20:]), 2)
    ma50 = round(mean(closes[-50:]), 2) if len(closes) >= 50 else round(mean(closes), 2)
    return ma5, ma10, ma20, ma50


def derive_trend(price: float | None, ma5: float | None, ma10: float | None, ma20: float | None, ma50: float | None) -> str:
    if None in (price, ma5, ma10, ma20, ma50):
        return "\u8cc7\u6599\u4e0d\u8db3"
    p, m5, m10, m20, m50 = float(price), float(ma5), float(ma10), float(ma20), float(ma50)
    if p > m5 > m10 > m20 > m50:
        return "\u5f37\u591a\u982d"
    if p < m5 < m10 and m10 > m20 > m50:
        return "\u5f37\u8f49\u5f31"
    if p < m5 < m10 < m20 and m20 > m50:
        return "\u5f31\u591a\u982d"
    if p > m5 > m10 > m20 and m20 < m50:
        return "\u5f31\u8f49\u5f37"
    return "\u6574\u7406"


@dataclass
class ProviderResult:
    name: str | None
    price: float | None
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma50: float | None
    trend: str
    note: str


class TwseTpexProvider:
    def __init__(self) -> None:
        self.twse_map, self.twse_ok = self.fetch_twse_snapshot()
        self.tpex_map, self.tpex_ok = self.fetch_tpex_snapshot()

    def fetch_twse_snapshot(self) -> tuple[dict[str, tuple[str, float]], bool]:
        try:
            rows = get_json_with_retry("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
            out: dict[str, tuple[str, float]] = {}
            if isinstance(rows, list):
                for row in rows:
                    code = str(row.get("Code", "")).strip()
                    name = str(row.get("Name", "")).strip()
                    close = parse_float(row.get("ClosingPrice"))
                    if code and name and close is not None:
                        out[code] = (name, close)
            return out, True
        except Exception:
            return {}, False

    def fetch_tpex_snapshot(self) -> tuple[dict[str, tuple[str, float]], bool]:
        try:
            rows = get_json_with_retry("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
            out: dict[str, tuple[str, float]] = {}
            if isinstance(rows, list):
                for row in rows:
                    code = normalize_stock_code(row.get("SecuritiesCompanyCode", ""))
                    name = str(row.get("CompanyName", "")).strip()
                    close = parse_float(row.get("Close"))
                    if code and name and close is not None:
                        out[code] = (name, close)
            return out, True
        except Exception:
            return {}, False

    def fetch_twse_closes(self, code: str) -> list[float]:
        closes: list[float] = []
        for dt in reversed(month_starts(6)):
            payload = get_json_with_retry(
                "https://www.twse.com.tw/exchangeReport/STOCK_DAY",
                {"date": dt.strftime("%Y%m01"), "stockNo": code, "response": "json"},
            )
            if not isinstance(payload, dict) or payload.get("stat") != "OK":
                continue
            for row in payload.get("data", []):
                if len(row) >= 7:
                    value = parse_float(row[6])
                    if value is not None:
                        closes.append(value)
        return closes

    def fetch_tpex_closes(self, code: str) -> list[float]:
        closes: list[float] = []
        for dt in reversed(month_starts(6)):
            payload = get_json_with_retry(
                "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php",
                {"l": "zh-tw", "d": roc_month(dt), "stkno": code},
            )
            if not isinstance(payload, dict):
                continue
            rows = payload.get("aaData", []) or payload.get("data", [])
            for row in rows:
                if len(row) >= 7:
                    value = parse_float(row[6])
                    if value is not None:
                        closes.append(value)
        return closes

    def fetch_yahoo_history_closes(self, code: str, market: str) -> list[float]:
        suffix = "TW" if market == "TWSE" else "TWO"
        return self.fetch_yahoo_chart(code, suffix)[1]

    def fetch_yahoo_chart(self, code: str, suffix: str) -> tuple[dict, list[float]]:
        symbol = f"{code}.{suffix}"
        last_error = None
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                payload = get_json_with_retry(
                    f"https://{host}/v8/finance/chart/{symbol}",
                    {"range": "6mo", "interval": "1d"},
                )
                result = payload.get("chart", {}).get("result", []) if isinstance(payload, dict) else []
                if not result:
                    raise ValueError(f"{host}:empty_result")
                meta = result[0].get("meta", {})
                closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                clean = [float(v) for v in closes if v is not None]
                if len(clean) < 20:
                    raise ValueError(f"{host}:not_enough_history:{len(clean)}")
                return meta, clean
            except Exception as exc:
                last_error = exc
        raise ValueError(str(last_error) if last_error else "yahoo_history_failed")

    def fetch_yahoo_fallback(self, code: str, existing_row: dict) -> ProviderResult:
        last_error = None
        for suffix in ("TW", "TWO"):
            try:
                meta, closes = self.fetch_yahoo_chart(code, suffix)
                ma5, ma10, ma20, ma50 = compute_mas(closes)
                price = parse_float(meta.get("regularMarketPrice")) or closes[-1]
                name = str(existing_row.get("name") or meta.get("shortName") or meta.get("symbol") or "").strip()
                trend = derive_trend(price, ma5, ma10, ma20, ma50)
                return ProviderResult(name, price, ma5, ma10, ma20, ma50, trend, STATUS_OK_YAHOO_FALLBACK)
            except Exception as exc:
                last_error = exc
        raise ValueError(str(last_error) if last_error else "yahoo_fallback_failed")

    def fetch(self, code: str, existing_row: dict) -> ProviderResult:
        if not self.twse_ok and not self.tpex_ok:
            try:
                return self.fetch_yahoo_fallback(code, existing_row)
            except Exception:
                return ProviderResult(None, None, None, None, None, None, "\u8cc7\u6599\u4e0d\u8db3", STATUS_SOURCE_DOWN)

        in_twse = code in self.twse_map
        in_tpex = code in self.tpex_map
        if not in_twse and not in_tpex:
            try:
                return self.fetch_yahoo_fallback(code, existing_row)
            except Exception as exc:
                reason = str(exc)[:80] or "not_found"
                return ProviderResult(None, None, None, None, None, None, "\u8cc7\u6599\u4e0d\u8db3", f"{STATUS_CODE_NOT_FOUND}\uff1bYahoo\u5099\u63f4\u5931\u6557\uff1a{reason}")

        if in_twse:
            name, price = self.twse_map[code]
            market = "TWSE"
        else:
            name, price = self.tpex_map[code]
            market = "TPEX"

        try:
            closes = self.fetch_twse_closes(code) if market == "TWSE" else self.fetch_tpex_closes(code)
            ma5, ma10, ma20, ma50 = compute_mas(closes)
            note = STATUS_OK_TWSE if market == "TWSE" else STATUS_OK_TPEX
        except Exception:
            try:
                closes = self.fetch_yahoo_history_closes(code, market)
                ma5, ma10, ma20, ma50 = compute_mas(closes)
                note = STATUS_OK_YAHOO_HISTORY
            except Exception as exc:
                reason = str(exc)[:80] or "history_failed"
                note = STATUS_MA_UNAVAILABLE_WITH_REASON.format(reason=reason)
                return ProviderResult(name, price, None, None, None, None, "\u8cc7\u6599\u4e0d\u8db3", note)

        trend = derive_trend(price, ma5, ma10, ma20, ma50)
        return ProviderResult(name, price, ma5, ma10, ma20, ma50, trend, note)


class MegaApiProvider:
    """Mega Speedy quote provider.

    Mega's Python API is event based. This wrapper logs in once per update run,
    subscribes each symbol, then waits briefly for OnTrade to supply the latest
    traded price. Moving averages still come from the public provider because
    spdQuoteAPI supplies realtime quotes rather than historical MA series.
    """

    def __init__(self) -> None:
        self.host = os.getenv("MEGA_QUOTE_HOST", "").strip()
        self.port = int(os.getenv("MEGA_QUOTE_PORT", "34567") or "34567")
        self.user_id = os.getenv("MEGA_QUOTE_ID", "").strip()
        self.password = os.getenv("MEGA_QUOTE_PASSWORD", "").strip()
        self.download_contracts = os.getenv("MEGA_QUOTE_DOWNLOAD_CONTRACTS", "0").strip().lower() in ("1", "true", "yes")
        self.timeout = float(os.getenv("MEGA_QUOTE_TIMEOUT", "8") or "8")
        self.public_provider = None
        self.sdk_error = ""
        self.client = None
        self.logon_ready = threading.Event()
        self.logon_ok = False
        self.logon_message = ""

        sdk_class = self._load_quote_class()
        if not sdk_class:
            return
        if not self._is_configured():
            return

        provider = self

        class QuoteClient(sdk_class):
            def __init__(self):
                super().__init__()
                self.trades = {}
                self.trade_events = {}

            def OnLogonResponse(self, IsSucceed, ReplyString):
                provider.logon_ok = bool(IsSucceed)
                provider.logon_message = str(ReplyString)
                provider.logon_ready.set()

            def OnTrade(self, Exchange, Symbol, MatchTime, MatchPrice, MatchQty, IsTestMatch):
                symbol = normalize_stock_code(Symbol)
                self.trades[symbol] = {
                    "exchange": str(Exchange),
                    "price": parse_float(MatchPrice),
                    "time": str(MatchTime),
                    "qty": MatchQty,
                    "is_test": bool(IsTestMatch),
                }
                event = self.trade_events.get(symbol)
                if event:
                    event.set()

        try:
            self.client = QuoteClient()
            started = self.client.Logon(self.host, self.port, self.user_id, self.password, self.download_contracts)
            if started is False:
                self.sdk_error = STATUS_MEGA_LOGON_FAILED
                return
            self.logon_ready.wait(self.timeout)
            if not self.logon_ok:
                self.sdk_error = f"{STATUS_MEGA_LOGON_FAILED}: {self.logon_message or 'no_response'}"
        except Exception as exc:
            self.sdk_error = f"{STATUS_MEGA_LOGON_FAILED}: {exc}"
            self.client = None

    def _load_quote_class(self):
        for module_name in ("megaSpeedy.spdQuoteAPI", "pySpeedy.spdQuoteAPI"):
            try:
                module = importlib.import_module(module_name)
                return getattr(module, "spdQuoteAPI")
            except Exception as exc:
                self.sdk_error = f"{STATUS_MEGA_SDK_MISSING}: {exc}"
        return None

    def _is_configured(self) -> bool:
        return bool(self.host and self.port and self.user_id and self.password)

    def _exchange_for_code(self, code: str) -> str:
        if self.public_provider is None:
            self.public_provider = TwseTpexProvider()
        if code in self.public_provider.twse_map:
            return "TWSE"
        if code in self.public_provider.tpex_map:
            return "OTC"
        return "TWSE"

    def _public_baseline(self, code: str, existing_row: dict) -> ProviderResult:
        if self.public_provider is None:
            self.public_provider = TwseTpexProvider()
        return self.public_provider.fetch(code, existing_row)

    def _existing_baseline(self, existing_row: dict, note: str) -> ProviderResult:
        price = parse_float(existing_row.get("price"))
        ma5 = parse_float(existing_row.get("ma5"))
        ma10 = parse_float(existing_row.get("ma10"))
        ma20 = parse_float(existing_row.get("ma20"))
        ma50 = parse_float(existing_row.get("ma50"))
        trend = derive_trend(price, ma5, ma10, ma20, ma50)
        return ProviderResult(str(existing_row.get("name", "")).strip() or None, price, ma5, ma10, ma20, ma50, trend, note)

    def fetch(self, code: str, existing_row: dict) -> ProviderResult:
        if not self._is_configured():
            return self._existing_baseline(existing_row, STATUS_MEGA_NOT_CONFIGURED)
        if self.client is None:
            return self._existing_baseline(existing_row, self.sdk_error or STATUS_MEGA_SDK_MISSING)
        if not self.logon_ok:
            return self._existing_baseline(existing_row, self.sdk_error or STATUS_MEGA_LOGON_FAILED)

        baseline = self._public_baseline(code, existing_row)
        exchange = self._exchange_for_code(code)
        event = threading.Event()
        self.client.trade_events[code] = event
        try:
            ok = self.client.Subscribe(exchange, code)
            if ok is False:
                baseline.note = f"MegaAPI \u8a02\u95b1\u5931\u6557\uff08{exchange}:{code}\uff09"
                return baseline
            event.wait(self.timeout)
            trade = self.client.trades.get(code)
            price = parse_float(trade.get("price")) if trade else None
            if price is None:
                baseline.note = STATUS_MEGA_TIMEOUT
                return baseline
            name = baseline.name or existing_row.get("name", "")
            trend = derive_trend(price, baseline.ma5, baseline.ma10, baseline.ma20, baseline.ma50)
            return ProviderResult(name, price, baseline.ma5, baseline.ma10, baseline.ma20, baseline.ma50, trend, STATUS_OK_MEGA)
        except Exception as exc:
            baseline.note = f"MegaAPI \u66f4\u65b0\u5931\u6557: {exc}"
            return baseline
        finally:
            self.client.trade_events.pop(code, None)


class GoodinfoExperimentalProvider:
    URL_TMPL = "https://goodinfo.tw/tw/StockDetail/StockDetail.asp?STOCK_ID={code}"

    def _pick_ma(self, text: str, aliases: list[str]) -> float | None:
        for alias in aliases:
            m = re.search(rf"{alias}\s*</[^>]*>\s*<[^>]*>\s*([0-9][0-9,]*\.?[0-9]*)", text)
            if not m:
                m = re.search(rf"{alias}\s*[:\uff1a]\s*([0-9][0-9,]*\.?[0-9]*)", text)
            if m:
                try:
                    return float(m.group(1).replace(",", ""))
                except Exception:
                    pass
        return None

    def fetch(self, code: str, existing_row: dict) -> ProviderResult:
        try:
            resp = requests.get(
                self.URL_TMPL.format(code=code),
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            text = resp.text
        except Exception:
            return ProviderResult(None, None, None, None, None, None, "\u8cc7\u6599\u4e0d\u8db3", STATUS_GOODINFO_BLOCKED)

        ma5 = self._pick_ma(text, ["5\u65e5\u5747\u50f9", "5MA"])
        ma10 = self._pick_ma(text, ["10\u65e5\u5747\u50f9", "10MA"])
        ma20 = self._pick_ma(text, ["20\u65e5\u5747\u50f9", "20MA"])
        ma50 = self._pick_ma(text, ["50\u65e5\u5747\u50f9", "50MA", "60\u65e5\u5747\u50f9"])
        price = self._pick_ma(text, ["\u6210\u4ea4", "\u73fe\u50f9", "\u6536\u76e4"])

        if None in (ma5, ma10, ma20, ma50):
            return ProviderResult(None, price, None, None, None, None, "\u8cc7\u6599\u4e0d\u8db3", STATUS_GOODINFO_PARSE_FAIL)

        trend = derive_trend(price, ma5, ma10, ma20, ma50)
        return ProviderResult(None, price, ma5, ma10, ma20, ma50, trend, "\u66f4\u65b0\u6210\u529f\uff08Goodinfo\u5be6\u9a57\uff09")
