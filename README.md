# 📊 Price Tracker — Theo dõi giá & cảnh báo Telegram

Tự động lấy giá **vàng SJC**, **USD/VND (Vietcombank)**, **dầu WTI** và gửi thông báo về Telegram.
Cảnh báo tự động khi có biến động ±5% (tuỳ chỉnh được).

## Tính năng

- Giá vàng SJC mua/bán (nguồn: sjc.com.vn)
- Giá vàng thế giới USD/oz (nguồn: metals.live)
- Tỷ giá USD/VND mua/bán (nguồn: Vietcombank)
- Giá dầu WTI USD/thùng (nguồn: Yahoo Finance)
- Báo cáo định kỳ 3 lần/ngày (8h, 12h, 17h)
- Kiểm tra biến động mỗi 30 phút trong giờ giao dịch
- Cảnh báo ngay khi biến động vượt ngưỡng (mặc định ±5%)

---

## Cài đặt nhanh

### 1. Fork/Clone repo về GitHub của bạn

```bash
git clone https://github.com/your-username/price-tracker.git
cd price-tracker
```

### 2. Tạo Telegram Bot

1. Nhắn tin cho **@BotFather** trên Telegram
2. Gõ `/newbot` → đặt tên → nhận **Bot Token** (dạng `123456789:ABCdef...`)
3. Lấy **Chat ID**:
   - Nhắn tin bất kỳ cho bot vừa tạo
   - Truy cập: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Tìm `"chat": {"id": <số>}` — đó là Chat ID của bạn
   - Hoặc nhắn tin cho **@userinfobot** để lấy ID của mình

### 3. Thêm Secrets vào GitHub

Vào repo GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret name | Giá trị |
|---|---|
| `TELEGRAM_TOKEN` | Token từ BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID của bạn |

### 4. Tuỳ chỉnh ngưỡng cảnh báo (tuỳ chọn)

Vào **Settings** → **Variables** → **Actions** → **New repository variable**:

| Variable | Mặc định | Ý nghĩa |
|---|---|---|
| `ALERT_THRESHOLD` | `5.0` | % biến động để cảnh báo |

### 5. Kích hoạt workflow

Vào tab **Actions** → chọn workflow **Price Tracker** → **Enable workflow**

Workflow sẽ tự chạy theo lịch. Để chạy thủ công: nhấn **Run workflow** → chọn mode.

---

## Lịch chạy

| Thời gian (ICT) | Mode | Hành động |
|---|---|---|
| 08:00 | `report` | Gửi báo cáo đầy đủ sáng |
| 12:00 | `report` | Gửi báo cáo đầy đủ trưa |
| 17:00 | `report` | Gửi báo cáo đầy đủ chiều |
| Mỗi 30 phút (8h–17h, T2–T6) | `alert_only` | Chỉ gửi nếu có biến động |

---

## Chạy local để test

```bash
pip install -r requirements.txt

export TELEGRAM_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export RUN_MODE="report"   # hoặc "alert_only"
export ALERT_THRESHOLD="5.0"

python price_tracker.py
```

---

## Cấu trúc file

```
├── price_tracker.py          # Script chính
├── requirements.txt          # Dependencies
├── price_history.json        # Lịch sử giá (tự tạo, được cache)
└── .github/
    └── workflows/
        └── price_tracker.yml # GitHub Actions workflow
```

---

## Ví dụ tin nhắn Telegram

**Báo cáo thường:**
```
📊 Báo cáo giá thị trường
🕐 15/01/2025 08:00 (ICT)

🥇 Vàng SJC
   Mua: 8,450,000 ₫ | Bán: 8,550,000 ₫/lượng
   🔺 +0.23%
🌐 Vàng TG: $2,680.50/oz  🔺 +0.15%
💵 USD (VCB)
   Mua: 25,100 ₫ | Bán: 25,430 ₫
   — 
🛢 Dầu WTI: $72.40/thùng  🔻 -0.82%

Nguồn: SJC, Vietcombank, Yahoo Finance
```

**Cảnh báo biến động:**
```
🚨 CẢNH BÁO biến động giá!
🕐 15/01/2025 14:30 (ICT)

Biến động vượt ngưỡng 5%:
  • Vàng SJC (bán) tăng 5.40%
  • Dầu WTI (USD/thùng) giảm 6.12%
```
