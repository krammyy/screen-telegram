from __future__ import annotations

import requests


class TelegramError(RuntimeError):
    pass


class HttpTelegramSender:
    def __init__(self, bot_token: str, proxy_url: str = "") -> None:
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self.proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    def _request(self, method: str, **kwargs):
        try:
            response = requests.post(
                f"{self.base}/{method}",
                timeout=(5, 25),
                proxies=self.proxies,
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException:
            raise TelegramError("Не удалось подключиться к Telegram.") from None

        if response.status_code in (401, 404):
            raise TelegramError("Telegram отклонил токен бота. Проверьте bot_token.")
        if response.status_code in (400, 403) and method == "sendPhoto":
            raise TelegramError("Telegram отклонил снимок. Проверьте chat_id и доступ бота к чату.")
        if not response.ok:
            raise TelegramError(f"Telegram вернул HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError:
            raise TelegramError("Telegram вернул некорректный ответ.") from None
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise TelegramError("Telegram отклонил запрос.")
        return data.get("result")

    def send_photo(self, image_bytes: bytes, filename: str, chat_id: str) -> None:
        self._request(
            "sendPhoto",
            data={"chat_id": chat_id},
            files={"photo": (filename, image_bytes, "image/jpeg")},
        )

    def get_chats(self) -> dict[str, str]:
        updates = self._request("getUpdates", json={"timeout": 0})
        if not isinstance(updates, list):
            raise TelegramError("Telegram вернул некорректный список чатов.")
        chats: dict[str, str] = {}
        for update in updates:
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            if chat_id is not None:
                title = chat.get("title") or chat.get("username") or chat.get("first_name") or "чат"
                chats[str(chat_id)] = str(title)
        return chats
