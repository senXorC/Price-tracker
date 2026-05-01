"""
Price Tracker - Theo dõi giá vàng, USD, dầu và cảnh báo Telegram
Nguồn: SJC (vàng VN), Vietcombank (USD), investing.com proxy (dầu)
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

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "5.0"))  # % chênh lệch
PRICE_HISTORY_FILE = Path("price_history.json")

VN_TZ = timezone(timedelta(hours=7))

# ── Lấy giá ───────────────────────────────────────────────────────────────────

def fetch_gold_sjc() -> dict:
    """
    Lấy giá vàng SJC từ API chính thức của SJC.
    Trả về giá mua/bán (đơn vị: nghìn đồng/chỉ).
    """
    url = "https://sjc.com.vn/GoldPrice/Services/PriceService.ashx"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)",
        "Referer": "https://sjc.com.vn/",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    # Tìm item SJC 1L, 1C, 1 Lượng
    for item in data:
        name = item.get("n", "").upper()
        if "1L" in name or "1 L" in name or "LƯỢNG" in name:
            buy = float(item.get("pb", 0)) * 1000   # về VND
            sell = float(item.get("ps", 0)) * 1000
            return {
                "buy": buy,
                "sell": sell,
                "unit": "VND/lượng",
                "name": item.get("n", "SJC"),
                "source": "SJC",
            }

    # Fallback: lấy item đầu tiên
    item = data[0]
    return {
        "buy": float(item.get("pb", 0)) * 1000,
        "sell": float(item.get("ps", 0)) * 1000,
        "unit": "VND/lượng",
        "name": item.get("n", "SJC"),
        "source": "SJC",
    }


def fetch_gold_world_usd() -> dict:
    """Lấy giá vàng thế giới USD/oz từ metals-api (miễn phí)."""
    # metals.live - không cần API key, CORS-friendly
    url = "https://api.metals.live/v1/spot/gold"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    price = float(data[0]["price"])
    return {"price": price, "unit": "USD/oz", "source": "metals.live"}


def fetch_usd_vcb() -> dict:
    """
    Lấy tỷ giá USD từ Vietcombank XML feed.
    Trả về giá mua/bán (VND/USD).
    """
    url = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.Trading.FX/fx.aspx?FuncID=06&BankID=vietcombank"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()

    import xml.etree.ElementTree as ET
    root = ET.fromstring(r.text)

    for exrate in root.findall(".//Exrate"):
        if exrate.get("CurrencyCode") == "USD":
            buy = exrate.get("Buy", "0").replace(",", "")
            sell = exrate.get("Sell", "0").replace(",", "")
            return {
                "buy": float(buy),
                "sell": float(sell),
                "unit": "VND/USD",
                "source": "Vietcombank",
            }

    raise ValueError("Không tìm thấy tỷ giá USD từ Vietcombank")


def fetch_oil_price() -> dict:
    """
    Lấy giá dầu WTI từ EIA (Energy Information Administration) - API công khai.
    Fallback sang stooq.com nếu cần API key.
    """
    # Thử EIA open data (không cần key cho dữ liệu cơ bản)
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/CL%3DF"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)",
            "Accept": "application/json",
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        prev_close = data["chart"]["result"][0]["meta"]["previousClose"]
        return {
            "price": float(price),
            "prev_close": float(prev_close),
            "unit": "USD/barrel",
            "source": "Yahoo Finance (WTI)",
        }
    except Exception as e:
        log.warning(f"Yahoo Finance thất bại: {e}, thử stooq...")

    # Fallback: stooq
    url = "https://stooq.com/q/l/?s=cl.f&f=sd2t2ohlcv&h&e=csv"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    fields = lines[1].split(",")
    price = float(fields[4])  # Close price
    return {
        "price": price,
        "unit": "USD/barrel",
        "source": "Stooq (WTI)",
    }


# ── Lịch sử giá ───────────────────────────────────────────────────────────────

def load_history() -> dict:
    if PRICE_HISTORY_FILE.exists():
        with open(PRICE_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(data: dict):
    with open(PRICE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Đã lưu lịch sử giá vào {PRICE_HISTORY_FILE}")


def check_change(key: str, current: float, history: dict) -> tuple[float | None, bool]:
    """Tính % thay đổi, trả về (pct_change, is_alert)."""
    prev = history.get(key)
    if prev is None:
        return None, False
    pct = (current - prev) / prev * 100
    is_alert = abs(pct) >= ALERT_THRESHOLD
    return pct, is_alert


# ── Telegram ───────────────────────────────────────────────────────────────────

def fmt_num(n: float, decimals: int = 0) -> str:
    return f"{n:,.{decimals}f}"


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    log.info(f"Đã gửi Telegram: {r.json().get('result', {}).get('message_id')}")


def arrow(pct: float | None) -> str:
    if pct is None:
        return "—"
    return f"🔺 +{pct:.2f}%" if pct > 0 else f"🔻 {pct:.2f}%"


def build_report(prices: dict, history: dict, alerts: list[str]) -> str:
    now = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    lines = [f"<b>📊 Báo cáo giá thị trường</b>", f"🕐 {now} (ICT)\n"]

    # Vàng SJC
    g = prices.get("gold_sjc")
    if g:
        pct, _ = check_change("gold_sjc_sell", g["sell"], history)
        lines.append(
            f"🥇 <b>Vàng SJC</b>\n"
            f"   Mua: {fmt_num(g['buy'])} ₫ | Bán: {fmt_num(g['sell'])} ₫/lượng\n"
            f"   {arrow(pct)}"
        )

    # Vàng thế giới
    gw = prices.get("gold_world")
    if gw:
        pct, _ = check_change("gold_world", gw["price"], history)
        lines.append(
            f"🌐 <b>Vàng TG</b>: ${fmt_num(gw['price'], 2)}/oz  {arrow(pct)}"
        )

    # USD/VND
    u = prices.get("usd_vcb")
    if u:
        pct, _ = check_change("usd_sell", u["sell"], history)
        lines.append(
            f"💵 <b>USD (VCB)</b>\n"
            f"   Mua: {fmt_num(u['buy'])} ₫ | Bán: {fmt_num(u['sell'])} ₫\n"
            f"   {arrow(pct)}"
        )

    # Dầu
    o = prices.get("oil")
    if o:
        pct, _ = check_change("oil", o["price"], history)
        lines.append(
            f"🛢 <b>Dầu WTI</b>: ${fmt_num(o['price'], 2)}/thùng  {arrow(pct)}"
        )

    # Cảnh báo
    if alerts:
        lines.append(f"\n⚠️ <b>CẢNH BÁO biến động &gt;{ALERT_THRESHOLD:.0f}%:</b>")
        lines.extend([f"  • {a}" for a in alerts])

    lines.append(f"\n<i>Nguồn: SJC, Vietcombank, Yahoo Finance</i>")
    return "\n".join(lines)


def build_alert_only(alerts: list[str]) -> str:
    now = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    lines = [
        f"🚨 <b>CẢNH BÁO biến động giá!</b>",
        f"🕐 {now} (ICT)\n",
        f"Biến động vượt ngưỡng <b>{ALERT_THRESHOLD:.0f}%</b>:",
    ]
    lines.extend([f"  • {a}" for a in alerts])
    lines.append("\n<i>Chạy báo cáo đầy đủ: xem GitHub Actions log</i>")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    mode = os.environ.get("RUN_MODE", "report")  # "report" | "alert_only"
    log.info(f"Bắt đầu chạy, mode={mode}, threshold={ALERT_THRESHOLD}%")

    history = load_history()
    prices = {}
    errors = []

    # Lấy giá vàng SJC
    try:
        prices["gold_sjc"] = fetch_gold_sjc()
        log.info(f"Vàng SJC: {prices['gold_sjc']}")
    except Exception as e:
        log.error(f"Lỗi lấy giá vàng SJC: {e}")
        errors.append(f"Vàng SJC: {e}")

    # Lấy giá vàng thế giới
    try:
        prices["gold_world"] = fetch_gold_world_usd()
        log.info(f"Vàng TG: {prices['gold_world']}")
    except Exception as e:
        log.error(f"Lỗi lấy giá vàng TG: {e}")
        errors.append(f"Vàng TG: {e}")

    # Lấy tỷ giá USD
    try:
        prices["usd_vcb"] = fetch_usd_vcb()
        log.info(f"USD VCB: {prices['usd_vcb']}")
    except Exception as e:
        log.error(f"Lỗi lấy tỷ giá USD: {e}")
        errors.append(f"USD VCB: {e}")

    # Lấy giá dầu
    try:
        prices["oil"] = fetch_oil_price()
        log.info(f"Dầu WTI: {prices['oil']}")
    except Exception as e:
        log.error(f"Lỗi lấy giá dầu: {e}")
        errors.append(f"Dầu: {e}")

    # Kiểm tra biến động
    alerts = []
    check_pairs = [
        ("gold_sjc_sell", prices.get("gold_sjc", {}).get("sell"), "Vàng SJC (bán)"),
        ("gold_world",    prices.get("gold_world", {}).get("price"), "Vàng TG (USD/oz)"),
        ("usd_sell",      prices.get("usd_vcb", {}).get("sell"), "USD/VND (bán)"),
        ("oil",           prices.get("oil", {}).get("price"), "Dầu WTI (USD/thùng)"),
    ]

    new_history = dict(history)

    for key, current, label in check_pairs:
        if current is None:
            continue
        pct, is_alert = check_change(key, current, history)
        if is_alert:
            direction = "tăng" if pct > 0 else "giảm"
            alerts.append(f"{label} {direction} {abs(pct):.2f}%")
            log.warning(f"ALERT: {label} thay đổi {pct:.2f}%")
        new_history[key] = current

    # Gửi Telegram
    if mode == "alert_only":
        if alerts:
            msg = build_alert_only(alerts)
            send_telegram(msg)
            log.info(f"Gửi cảnh báo {len(alerts)} mục")
        else:
            log.info("Không có biến động đáng kể, bỏ qua gửi Telegram")
    else:
        # Gửi báo cáo đầy đủ + highlight cảnh báo nếu có
        msg = build_report(prices, history, alerts)
        send_telegram(msg)

    # Lưu lịch sử giá
    save_history(new_history)

    if errors:
        log.warning(f"Có {len(errors)} lỗi trong quá trình lấy giá: {errors}")

    log.info("Hoàn thành.")


if __name__ == "__main__":
    main()
