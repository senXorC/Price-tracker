"""
Price Tracker - Theo dõi giá vàng, USD, dầu và cảnh báo Telegram
Nguồn ổn định: Yahoo Finance (vàng TG, USD/VND, dầu), SJC scrape cải tiến
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ALERT_THRESHOLD  = float(os.environ.get("ALERT_THRESHOLD", "5.0"))
PRICE_HISTORY_FILE = Path("price_history.json")
VN_TZ = timezone(timedelta(hours=7))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


# ── Lấy giá Yahoo Finance ─────────────────────────────────────────────────────

def fetch_yahoo(symbol: str, label: str) -> dict:
    """Lấy giá từ Yahoo Finance theo symbol."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"}
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice") or meta.get("previousClose")
    prev  = meta.get("previousClose") or price

    return {
        "price":      float(price),
        "prev_close": float(prev),
        "change_pct": round((price - prev) / prev * 100, 2) if prev else 0,
        "label":      label,
        "source":     "Yahoo Finance",
    }


def fetch_gold_world() -> dict:
    """Vàng thế giới XAU/USD (oz)."""
    return fetch_yahoo("GC%3DF", "Vàng TG (USD/oz)")


def fetch_usd_vnd() -> dict:
    """Tỷ giá USD/VND."""
    return fetch_yahoo("USDVND%3DX", "USD/VND")


def fetch_oil() -> dict:
    """Dầu WTI (USD/thùng)."""
    return fetch_yahoo("CL%3DF", "Dầu WTI (USD/thùng)")


# ── Lấy giá vàng trong nước (VN) ─────────────────────────────────────────────

# ── Lấy giá vàng trong nước (VN) ─────────────────────────────────────────────

def fetch_gold_sjc() -> dict:
    """
    Lấy giá vàng SJC thực tế thị trường VN.
    Dùng webgia.com và webtygia.com — các trang tổng hợp không block GitHub Actions IP.
    SJC trực tiếp block IP nước ngoài nên không dùng.
    """

    # ── Nguồn 1: webgia.com — scrape bảng giá vàng ───────────────────────────
    try:
        from bs4 import BeautifulSoup
        r = requests.get(
            "https://webgia.com/gia-vang/",
            headers={**HEADERS, "Referer": "https://webgia.com/"},
            timeout=20,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # Tìm bảng giá vàng SJC
        for row in soup.select("table tr"):
            cells = row.find_all(["td", "th"])
            text  = " ".join(c.get_text(strip=True) for c in cells).upper()
            if "SJC" in text and len(cells) >= 3:
                nums = []
                for c in cells:
                    t = c.get_text(strip=True).replace(",", "").replace(".", "")
                    if t.isdigit() and len(t) >= 7:
                        nums.append(float(t))
                if len(nums) >= 2:
                    log.info(f"webgia.com SJC: buy={nums[0]}, sell={nums[1]}")
                    return {"buy": nums[0], "sell": nums[1], "unit": "VND/lượng", "source": "webgia.com", "name": "Vàng SJC"}
    except Exception as e:
        log.warning(f"Nguồn 1 webgia.com: {e}")

    # ── Nguồn 2: webtygia.com JSON API ───────────────────────────────────────
    try:
        r = requests.get(
            "https://webtygia.com/api/gold",
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        for item in (data if isinstance(data, list) else data.get("data", [])):
            name = str(item.get("name", "") or item.get("loai", "")).upper()
            if "SJC" in name or "MIẾNG" in name:
                buy  = float(str(item.get("buy")  or item.get("mua", 0)).replace(",", ""))
                sell = float(str(item.get("sell") or item.get("ban", 0)).replace(",", ""))
                if buy > 1_000_000:
                    log.info(f"webtygia.com SJC: buy={buy}, sell={sell}")
                    return {"buy": buy, "sell": sell, "unit": "VND/lượng", "source": "webtygia.com", "name": "Vàng SJC"}
    except Exception as e:
        log.warning(f"Nguồn 2 webtygia.com: {e}")

    # ── Nguồn 3: VNAppMob (nếu có key còn hạn) ───────────────────────────────
    api_key = os.environ.get("VNAPPMOB_API_KEY", "")
    if api_key:
        try:
            r = requests.get(
                "https://api.vnappmob.com/api/v2/gold/sjc",
                headers={**HEADERS, "Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            r.raise_for_status()
            item = r.json()["results"][0]
            buy  = float(item.get("buy_1l") or item.get("buy_hcm") or 0)
            sell = float(item.get("sell_1l") or item.get("sell_hcm") or 0)
            if buy > 0:
                log.info(f"VNAppMob SJC: buy={buy}, sell={sell}")
                return {"buy": buy, "sell": sell, "unit": "VND/lượng", "source": "SJC (VNAppMob)", "name": "Vàng SJC 1 lượng"}
        except Exception as e:
            log.warning(f"Nguồn 3 VNAppMob: {e}")

    # ── Nguồn 4: SJC XML (có thể bị block từ IP nước ngoài) ──────────────────
    try:
        import xml.etree.ElementTree as ET
        r = requests.get(
            "https://sjc.com.vn/xml/tygiavang.xml",
            headers={**HEADERS, "Referer": "https://sjc.com.vn/"},
            timeout=15,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//Data"):
            name = (item.get("n_1") or "").upper()
            if "SJC" in name or "MIẾNG" in name:
                buy  = float(item.get("pb_1", "0"))
                sell = float(item.get("ps_1", "0"))
                if buy < 100_000:
                    buy *= 1_000; sell *= 1_000
                log.info(f"SJC XML: buy={buy}, sell={sell}")
                return {"buy": buy, "sell": sell, "unit": "VND/lượng", "source": "SJC XML", "name": item.get("n_1", "SJC")}
    except Exception as e:
        log.warning(f"Nguồn 4 SJC XML: {e}")

    raise RuntimeError("Tất cả nguồn giá vàng VN đều thất bại")


# ── Lịch sử giá ───────────────────────────────────────────────────────────────

def load_history() -> dict:
    if PRICE_HISTORY_FILE.exists():
        with open(PRICE_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(data: dict):
    with open(PRICE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Đã lưu lịch sử giá → {PRICE_HISTORY_FILE}")


def check_change(key: str, current: float, history: dict) -> tuple:
    prev = history.get(key)
    if prev is None:
        return None, False
    pct = (current - prev) / prev * 100
    return round(pct, 2), abs(pct) >= ALERT_THRESHOLD


# ── Format & gửi Telegram ─────────────────────────────────────────────────────

def fmt(n: float, dec: int = 0) -> str:
    return f"{n:,.{dec}f}"


def arrow(pct) -> str:
    if pct is None:
        return "—"
    if pct > 0:
        return f"🔺 +{pct:.2f}%"
    if pct < 0:
        return f"🔻 {pct:.2f}%"
    return "➡️ 0.00%"


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=15)
    r.raise_for_status()
    msg_id = r.json().get("result", {}).get("message_id")
    log.info(f"Gửi Telegram OK (message_id={msg_id})")


def build_report(prices: dict, history: dict, alerts: list) -> str:
    now = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    lines = [f"<b>📊 Báo cáo giá thị trường</b>", f"🕐 {now} (ICT)\n"]

    # Vàng SJC
    g = prices.get("gold_sjc")
    if g:
        pct, _ = check_change("gold_sjc_sell", g["sell"], history)
        est = " <i>(ước tính)</i>" if g.get("estimated") else ""
        lines.append(
            f"🥇 <b>Vàng SJC</b>{est}\n"
            f"   Mua: {fmt(g['buy'])} ₫  |  Bán: {fmt(g['sell'])} ₫/lượng\n"
            f"   {arrow(pct)}"
        )

    # Vàng TG
    gw = prices.get("gold_world")
    if gw:
        pct, _ = check_change("gold_world", gw["price"], history)
        lines.append(
            f"🌐 <b>Vàng TG</b>: ${fmt(gw['price'], 2)}/oz  {arrow(pct)}"
        )

    # USD/VND
    u = prices.get("usd_vnd")
    if u:
        pct, _ = check_change("usd_vnd", u["price"], history)
        lines.append(
            f"💵 <b>USD/VND</b>: {fmt(u['price'], 0)} ₫  {arrow(pct)}"
        )

    # Dầu WTI
    o = prices.get("oil")
    if o:
        pct, _ = check_change("oil", o["price"], history)
        lines.append(
            f"🛢 <b>Dầu WTI</b>: ${fmt(o['price'], 2)}/thùng  {arrow(pct)}"
        )

    # Cảnh báo
    if alerts:
        lines.append(f"\n⚠️ <b>CẢNH BÁO biến động &gt;{ALERT_THRESHOLD:.0f}%:</b>")
        for a in alerts:
            lines.append(f"  • {a}")

    sources = ", ".join(filter(None, {
        prices.get("gold_sjc", {}).get("source"),
        "Yahoo Finance",
    }))
    lines.append(f"\n<i>Nguồn: {sources}</i>")
    return "\n".join(lines)


def build_alert_message(alerts: list) -> str:
    now = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    lines = [
        f"🚨 <b>CẢNH BÁO biến động giá!</b>",
        f"🕐 {now} (ICT)\n",
        f"Biến động vượt ngưỡng <b>{ALERT_THRESHOLD:.0f}%</b>:",
    ]
    for a in alerts:
        lines.append(f"  • {a}")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    mode = os.environ.get("RUN_MODE", "report")
    log.info(f"mode={mode}, threshold={ALERT_THRESHOLD}%")

    history = load_history()
    prices  = {}
    errors  = []

    # Vàng TG (Yahoo) — fetch trước vì SJC có thể dùng làm fallback
    try:
        prices["gold_world"] = fetch_gold_world()
        log.info(f"Vàng TG: {prices['gold_world']}")
    except Exception as e:
        log.error(f"Vàng TG: {e}")
        errors.append(f"Vàng TG: {e}")

    # USD/VND (Yahoo)
    try:
        prices["usd_vnd"] = fetch_usd_vnd()
        log.info(f"USD/VND: {prices['usd_vnd']}")
    except Exception as e:
        log.error(f"USD/VND: {e}")
        errors.append(f"USD/VND: {e}")

    # Vàng SJC (có fallback tính từ TG×USD)
    try:
        prices["gold_sjc"] = fetch_gold_sjc()
        log.info(f"Vàng SJC: {prices['gold_sjc']}")
    except Exception as e:
        log.error(f"Vàng SJC: {e}")
        errors.append(f"Vàng SJC: {e}")

    # Dầu WTI (Yahoo)
    try:
        prices["oil"] = fetch_oil()
        log.info(f"Dầu: {prices['oil']}")
    except Exception as e:
        log.error(f"Dầu: {e}")
        errors.append(f"Dầu: {e}")

    # Kiểm tra biến động & cập nhật lịch sử
    alerts = []
    new_history = dict(history)
    checks = [
        ("gold_sjc_sell", prices.get("gold_sjc",   {}).get("sell"),  "Vàng SJC (bán)"),
        ("gold_world",    prices.get("gold_world",  {}).get("price"), "Vàng TG (USD/oz)"),
        ("usd_vnd",       prices.get("usd_vnd",     {}).get("price"), "USD/VND"),
        ("oil",           prices.get("oil",         {}).get("price"), "Dầu WTI"),
    ]
    for key, val, label in checks:
        if val is None:
            continue
        pct, is_alert = check_change(key, val, history)
        if is_alert:
            direction = "tăng" if pct > 0 else "giảm"
            alerts.append(f"{label} {direction} {abs(pct):.2f}%")
            log.warning(f"ALERT: {label} {pct:+.2f}%")
        new_history[key] = val

    # Gửi Telegram
    if mode == "alert_only":
        if alerts:
            send_telegram(build_alert_message(alerts))
        else:
            log.info("Không có biến động — bỏ qua gửi Telegram")
    else:
        send_telegram(build_report(prices, history, alerts))

    save_history(new_history)

    if errors:
        log.warning(f"{len(errors)} lỗi: {errors}")
    log.info("Hoàn thành.")


if __name__ == "__main__":
    main()
