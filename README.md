# 📊 Price Tracker — Theo dõi giá & cảnh báo Telegram

Tự động lấy giá **vàng SJC**, **vàng thế giới**, **USD/VND**, **dầu WTI** và gửi thông báo về Telegram.
Cảnh báo tự động khi có biến động ±5% (tuỳ chỉnh được).

---

## Tính năng

- 🥇 Giá vàng SJC mua/bán thực tế thị trường VN (nguồn: webgia.com)
- 🌐 Giá vàng thế giới USD/oz (nguồn: Yahoo Finance)
- 💵 Tỷ giá USD/VND (nguồn: Yahoo Finance)
- 🛢 Giá dầu WTI USD/thùng (nguồn: Yahoo Finance)
- Báo cáo định kỳ theo lịch cài đặt
- Cảnh báo ngay khi biến động vượt ngưỡng (mặc định ±5%)
- Lưu lịch sử giá giữa các lần chạy để so sánh

---

## Nguồn dữ liệu

| Loại giá | Nguồn chính | Ghi chú |
|---|---|---|
| Vàng SJC (VN) | webgia.com | Giá thực tế thị trường trong nước |
| Vàng thế giới | Yahoo Finance `GC=F` | USD/oz |
| USD/VND | Yahoo Finance `USDVND=X` | Tỷ giá thị trường |
| Dầu WTI | Yahoo Finance `CL=F` | USD/thùng |

> **Lưu ý:** SJC trực tiếp block IP từ server nước ngoài nên dùng webgia.com làm nguồn chính. Nếu webgia.com thất bại, code tự động thử webtygia.com → VNAppMob → SJC XML theo thứ tự.

---

## Cài đặt

### 1. Tạo repo GitHub

Upload 3 file lên repo mới:
```
├── price_tracker.py
├── requirements.txt
└── .github/
    └── workflows/
        └── price_tracker.yml
```

### 2. Tạo Telegram Bot

1. Nhắn tin cho **@BotFather** trên Telegram
2. Gõ `/newbot` → đặt tên → nhận **Bot Token** (dạng `123456789:ABCdef...`)
3. Lấy **Chat ID**: nhắn tin cho **@userinfobot** → nó trả về ID ngay lập tức

### 3. Thêm Secrets vào GitHub

Vào repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Giá trị |
|---|---|
| `TELEGRAM_TOKEN` | Token từ BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID của bạn |
| `VNAPPMOB_API_KEY` | *(Tuỳ chọn)* Key từ `https://api.vnappmob.com/api/request_api_key?scope=gold` |

### 4. Tuỳ chỉnh ngưỡng cảnh báo

Vào **Settings → Variables → Actions → New repository variable**:

| Variable | Mặc định | Ý nghĩa |
|---|---|---|
| `ALERT_THRESHOLD` | `5.0` | % biến động để gửi cảnh báo |

### 5. Kích hoạt workflow

Vào tab **Actions** → chọn workflow **Price Tracker** → **Enable workflow**

---

## Lịch chạy

Mặc định chạy mỗi **5 phút** (có thể chỉnh trong file workflow):

```yaml
schedule:
  - cron: "*/5 * * * *"
```

> ⚠️ GitHub Actions free account có giới hạn **2,000 phút/tháng**. Sau khi test xong nên đổi về lịch hợp lý hơn, ví dụ 3 lần/ngày:
> ```yaml
> - cron: "0 1 * * *"    # 08:00 ICT
> - cron: "0 5 * * *"    # 12:00 ICT
> - cron: "0 10 * * *"   # 17:00 ICT
> - cron: "*/30 1-10 * * 1-5"  # cảnh báo mỗi 30 phút giờ giao dịch
> ```

---

## Test tính năng cảnh báo

Để test cảnh báo biến động mà không cần chờ giá thay đổi thật, tạo file `price_history.json` trong repo với giá thấp hơn ~10%:

```json
{
  "gold_sjc_sell": 14900000,
  "gold_world": 4200.0,
  "usd_vnd": 24000.0,
  "oil": 92.0
}
```

Commit file này lên repo, sau đó nhấn **Run workflow** thủ công. Code sẽ so sánh giá thực với giá cũ → phát hiện chênh lệch >5% → gửi cảnh báo Telegram ngay.

---

## Chạy local

```bash
pip install -r requirements.txt

export TELEGRAM_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export RUN_MODE="report"        # hoặc "alert_only"
export ALERT_THRESHOLD="5.0"

python price_tracker.py
```

---

## Ví dụ tin nhắn Telegram

**Báo cáo đầy đủ:**
```
📊 Báo cáo giá thị trường
🕐 01/05/2026 22:35 (ICT)

🥇 Vàng SJC
   Mua: 16,300,000 ₫  |  Bán: 16,600,000 ₫/lượng
   🔺 +0.60%
🌐 Vàng TG: $4,647.00/oz  —
💵 USD/VND: 26,355 ₫  —
🛢 Dầu WTI: $101.62/thùng  🔻 -1.65%

Nguồn: webgia.com, Yahoo Finance
```

**Cảnh báo biến động:**
```
🚨 CẢNH BÁO biến động giá!
🕐 01/05/2026 14:30 (ICT)

Biến động vượt ngưỡng 5%:
  • Vàng SJC (bán) tăng 11.40%
  • Dầu WTI giảm 6.12%
```
