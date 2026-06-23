"""
Sends push notifications via ntfy.sh.
"""
import os
import requests
from dotenv import load_dotenv
from watchtower.classifier import AlertEvent

load_dotenv()

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
BASE_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

TAG_MAP = {
    "touch": "rotating_light",
    "override": "zap",
    "approaching": "eyes",
}


def send_alert(event: AlertEvent, symbol: str) -> None:
    if not NTFY_TOPIC:
        print("[notifier] NTFY_TOPIC not set, skipping alert")
        return
    title = f"YALGO | {symbol} {event.alert_reason.upper()}"
    priority = "urgent" if event.alert_reason in ("touch", "override") else "default"
    tags = TAG_MAP.get(event.alert_reason, "bell")
    body = (
        f"{symbol} {event.alert_reason.upper()} {event.level_type} {event.level}\n"
        f"Price within {event.distance_pct:.2f}% of level"
    )
    headers = {
        "Title": title,
        "Priority": priority,
        "Tags": tags,
    }
    try:
        resp = requests.post(BASE_URL, data=body.encode("utf-8"), headers=headers, timeout=5)
        if not resp.ok:
            print(f"[notifier] ntfy POST failed: {resp.status_code}")
    except requests.RequestException as e:
        print(f"[notifier] ntfy network error: {e}")