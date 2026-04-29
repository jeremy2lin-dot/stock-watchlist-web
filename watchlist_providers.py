from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from statistics import mean

import requests


TIMEOUT = 20

STATUS_OK_TWSE = "更新成功（TWSE）"
STATUS_OK_TPEX = "更新成功（TPEX）"
STATUS_OK_YAHOO_HISTORY = "更新成功（Yahoo歷史備援）"
STATUS_OK_YAHOO_FALLBACK = "更新成功（Yahoo備援）"
STATUS_CODE_NOT_FOUND = "代號不存在（TWSE/TPEX）"
STATUS_SOURCE_DOWN = "資料源暫時不可用"
STATUS_MA_UNAVAILABLE = "資料異常（無法取得均線）"
STATUS_MA_UNAVAILABLE_WITH_REASON = "資料異常（無法取得均線：{reason}）"
STATUS_GOODINFO_PARSE_FAIL = "資料異常（Goodinfo解析失敗）"
STATUS_GOODINFO_BLOCKED = "資料異常（Goodinfo連線受限）"


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
        return "資料不足"
    p, m5, m10, m20, m50 = float(price), float(ma5), float(ma10), float(ma20), float(ma50)
    if p > m5 > m10 > m20 > m50:
        return "強多頭"
    if p < m5 < m10 and m10 > m20 > m50:
        return "強轉弱"
    if p < m5 < m10 < m20 and m20 > m50:
        return "弱多頭"
    if p > m5 > m10 > m20 and m20 < m50:
        return "弱轉強"
    return "整理"


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
                return ProviderResult(None, None, None, None, None, None, "資料不足", STATUS_SOURCE_DOWN)

        in_twse = code in self.twse_map
        in_tpex = code in self.tpex_map
        if not in_twse and not in_tpex:
            try:
                return self.fetch_yahoo_fallback(code, existing_row)
            except Exception as exc:
                reason = str(exc)[:80] or "not_found"
                return ProviderResult(None, None, None, None, None, None, "資料不足", f"{STATUS_CODE_NOT_FOUND}；Yahoo備援失敗：{reason}")

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
                return ProviderResult(name, price, None, None, None, None, "資料不足", note)

        trend = derive_trend(price, ma5, ma10, ma20, ma50)
        return ProviderResult(name, price, ma5, ma10, ma20, ma50, trend, note)


class MegaApiProvider:
    def fetch(self, code: str, existing_row: dict) -> ProviderResult:
        return ProviderResult(
            None,
            None,
            None,
            None,
            None,
            None,
            "資料不足",
            "MegaAPI 尚未設定（請先完成憑證與 API 申請）",
        )


class GoodinfoExperimentalProvider:
    URL_TMPL = "https://goodinfo.tw/tw/StockDetail/StockDetail.asp?STOCK_ID={code}"

    def _pick_ma(self, text: str, aliases: list[str]) -> float | None:
        for alias in aliases:
            m = re.search(rf"{alias}\s*</[^>]*>\s*<[^>]*>\s*([0-9][0-9,]*\.?[0-9]*)", text)
            if not m:
                m = re.search(rf"{alias}\s*[:：]\s*([0-9][0-9,]*\.?[0-9]*)", text)
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
            return ProviderResult(None, None, None, None, None, None, "資料不足", STATUS_GOODINFO_BLOCKED)

        ma5 = self._pick_ma(text, ["5日均價", "5MA"])
        ma10 = self._pick_ma(text, ["10日均價", "10MA"])
        ma20 = self._pick_ma(text, ["20日均價", "20MA"])
        ma50 = self._pick_ma(text, ["50日均價", "50MA", "60日均價"])
        price = self._pick_ma(text, ["成交", "現價", "收盤"])

        if None in (ma5, ma10, ma20, ma50):
            return ProviderResult(None, price, None, None, None, None, "資料不足", STATUS_GOODINFO_PARSE_FAIL)

        trend = derive_trend(price, ma5, ma10, ma20, ma50)
        return ProviderResult(None, price, ma5, ma10, ma20, ma50, trend, "更新成功（Goodinfo實驗）")
