from __future__ import annotations

import argparse
import sys

from app.config import load_config
from app.telegram_sender import HttpTelegramSender, TelegramError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Screen → Telegram")
    parser.add_argument("--fetch-chat", action="store_true", help="Показать ID чатов своего бота")
    args = parser.parse_args(argv)

    try:
        config = load_config()
        sender = HttpTelegramSender(config.bot_token, config.proxy_url)

        if args.fetch_chat:
            chats = sender.get_chats()
            if not chats:
                print("Напишите своему боту в Telegram и повторите команду.")
                return 1
            for chat_id, title in chats.items():
                print(f"{chat_id}  {title}")
            print("Запишите ID выбранного чата в chat_id в config.json.")
            return 0

        if not config.chat_id:
            raise ValueError("Укажите chat_id в config.json. Для поиска ID запустите --fetch-chat.")

        from app.window import run_window

        run_window(config, sender)
        return 0
    except (ValueError, TelegramError, OSError) as exc:
        print(f"Screen → Telegram: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
