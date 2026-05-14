import requests
import os

def test_telegram_notification():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": "Test notification from yt-watcher"
    }

    response = requests.post(url, data=payload)

    assert response.status_code == 200
