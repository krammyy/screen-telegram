from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)


@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    chat_id: str
    jpeg_quality: int = 70
    proxy_url: str = ""


def load_config() -> AppConfig:
    path = ROOT / "config.json"
    if not path.exists():
        example = ROOT / "config.example.json"
        if example.exists():
            shutil.copyfile(example, path)
        else:
            path.write_text('{"bot_token": "", "chat_id": ""}\n', encoding="utf-8")

    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("config.json должен содержать объект JSON.")

    token = str(raw.get("bot_token") or "").strip()
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
        raise ValueError("Укажите токен своего Telegram-бота в bot_token в config.json.")

    chat_id = str(raw.get("chat_id") or "").strip()
    if chat_id.startswith("PASTE_"):
        chat_id = ""
    legacy_chats = raw.get("chat_ids")
    if not chat_id and isinstance(legacy_chats, list) and len(legacy_chats) == 1:
        chat_id = str(legacy_chats[0]).strip()
    if chat_id and not re.fullmatch(r"-?\d+", chat_id):
        raise ValueError("Укажите числовой chat_id в config.json.")

    quality = raw.get("jpeg_quality", 70)
    if type(quality) is not int or not 10 <= quality <= 95:
        raise ValueError("jpeg_quality должен быть целым числом от 10 до 95.")

    return AppConfig(token, chat_id, quality, str(raw.get("proxy_url") or "").strip())
