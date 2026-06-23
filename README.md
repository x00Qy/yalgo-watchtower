# YALGO Watchtower

A lightweight support/resistance alert tool for Indian equities. Monitors your watchlist every 5 minutes during market hours and sends instant push notifications to your phone when a stock approaches or touches a key level.

Built with Python. Alerts delivered via [ntfy.sh](https://ntfy.sh) — no Telegram, no email, no browser tab required.

---

## What it does

- Polls live prices every 5 minutes via Angel One SmartAPI
- Fires alerts when price is within 3% of any configured support or resistance level
- Three alert types:
  - **TOUCH** — price within 1% of level or has crossed it (always fires, restarts cooldown)
  - **APPROACHING** — price within 1–3% of level (fires once per fresh zone entry)
  - **OVERRIDE** — price moved ≥1% in a single poll, bypasses cooldown suppression
- 1-hour cooldown per level to prevent spam
- Auto-stops at 3:30 PM IST every day
- Push notifications straight to your phone via ntfy app

---

## Project structure

```
yalgo-watchtower/
├── config/
│   ├── watchlist.json          # Your stocks and levels (gitignored — never committed)
│   └── watchlist.example.json  # Template to copy from
├── data/
│   └── reliance_sample.csv     # Synthetic data for replay testing
├── scripts/
│   └── lookup_angel_tokens.py  # One-time script to fetch Angel One tokens
├── tests/
│   ├── test_classifier.py      # 22 unit tests for alert logic
│   ├── test_alert_engine.py    # 7 unit tests for alert engine
│   └── test_price_fetcher.py   # Price fetcher tests
├── watchtower/
│   ├── classifier.py           # Core alert decision engine
│   ├── alert_engine.py         # Stateful engine — wraps classifier per stock
│   ├── price_fetcher.py        # Price fetching with fallback chain
│   ├── notifier.py             # ntfy.sh push notification sender
│   ├── poller.py               # 5-minute polling loop
│   └── price_providers/        # Angel One, Twelve Data, RapidAPI providers
├── run_watchtower.py           # Main entrypoint
├── run_replay.py               # Historical replay CLI
├── .env.example                # Environment variable template
└── requirements.txt
```

---

## Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/x00Qy/yalgo-watchtower.git
cd yalgo-watchtower
python -m venv venv
```

**Windows:**
```powershell
venv\Scripts\activate
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
ANGEL_ONE_API_KEY=your_api_key
ANGEL_ONE_CLIENT_ID=your_client_id
ANGEL_ONE_MPIN=your_mpin
ANGEL_ONE_TOTP_SECRET=your_totp_secret
NTFY_TOPIC=your_ntfy_topic
```

> Get your Angel One API credentials from [smartapi.angelbroking.com](https://smartapi.angelbroking.com).
> For `NTFY_TOPIC`, create a unique topic name at [ntfy.sh](https://ntfy.sh) and subscribe to it in the ntfy app on your phone.

### 4. Set up your watchlist

Copy the example watchlist:

```bash
cp config/watchlist.example.json config/watchlist.json
```

Edit `config/watchlist.json` with your stocks and levels (see [Adding stocks](#adding-stocks-to-your-watchlist) below).

### 5. Fetch Angel One tokens

Angel One requires a numeric token for each stock symbol. Run this once to populate tokens:

```bash
python scripts/lookup_angel_tokens.py
```

This downloads the instrument master from Angel One and saves tokens to `watchtower/symbol_tokens.json`.

### 6. Run the bot

```bash
python run_watchtower.py
```

The bot will start polling immediately and shut down automatically at 3:30 PM IST.

---

## Adding stocks to your watchlist

Open `config/watchlist.json`. The format is:

```json
{
  "stocks": {
    "SYMBOL": {
      "support": [
        { "level": 1280, "note": "200 DMA" },
        { "level": 1250, "note": "Previous swing low" }
      ],
      "resistance": [
        { "level": 1380, "note": "Previous high" },
        { "level": 1420, "note": "All-time high" }
      ]
    }
  }
}
```

**Rules:**
- `SYMBOL` must be the exact NSE symbol (e.g. `RELIANCE`, `HDFCBANK`, `INFY`)
- You can add as many support and resistance levels as you want per stock
- The `note` field is optional — use it to remind yourself why the level matters
- After adding a new symbol, run `python scripts/lookup_angel_tokens.py` again to fetch its token

**Watchlist cap:** The Angel One batch quote API supports up to **50 symbols per request**. In practice, a focused watchlist of 10–20 stocks works best.

---

## Running tests

```bash
python -m pytest tests/test_classifier.py tests/test_alert_engine.py -v
```

Expected: **29 passed**.

---

## Historical replay

Test alert logic against historical data without live prices:

```bash
python run_replay.py RELIANCE data/reliance_sample.csv
```

Add `--verbose` for raw debug output.

---

## Auto-start on Windows boot

To have Watchtower start automatically every weekday at 9:00 AM, run this once in PowerShell as Administrator:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "C:\Users\abhishek\Downloads\yalgo-watchtower\venv\Scripts\python.exe" `
    -Argument "C:\Users\abhishek\Downloads\yalgo-watchtower\run_watchtower.py" `
    -WorkingDirectory "C:\Users\abhishek\Downloads\yalgo-watchtower"

$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "09:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 7) `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday

Register-ScheduledTask `
    -TaskName "YALGO Watchtower" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "YALGO Watchtower — auto start at 9AM weekdays"
```

To remove the task later:
```powershell
Unregister-ScheduledTask -TaskName "YALGO Watchtower" -Confirm:$false
```

> **Note:** Update the paths above if you move the project folder.

---

## Alert logic summary

| Zone | Distance from level | Behaviour |
|---|---|---|
| TOUCH | ≤ 1% or breached | Always fires. Restarts 1hr cooldown. |
| APPROACHING | 1% – 3% | Fires once per fresh zone entry. Suppressed during cooldown. |
| OVERRIDE | Any zone, ≥1% single-poll move | Bypasses cooldown suppression. Does not reset cooldown. |
| FAR | > 3% | No alert. Resets zone entry state. |

Cooldown is per `(stock, level)` pair — independent across levels and stocks.

---

## Built by

**YALGO Quant Labs** — [github.com/x00Qy](https://github.com/x00Qy)
