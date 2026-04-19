import requests

from backend.config import get_settings


def send_telegram_alert(message: str) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": settings.telegram_chat_id, "text": message},
        timeout=10,
    )
    return response.ok
