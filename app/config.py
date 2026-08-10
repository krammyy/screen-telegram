from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.machine import current_machine_id


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"


def _clean_ids(values: list) -> list[str]:
    out: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item.startswith("PASTE_"):
            continue
        if item not in out:
            out.append(item)
    return out


@dataclass
class AppConfig:
    bot_token: str = ""
    chat_id: str = ""
    chat_ids: list[str] = field(default_factory=list)
    interval_seconds: int = 300
    jpeg_quality: int = 70
    hotkey: str = "ctrl+shift+s"
    allowed_machine_id: str = ""
    caption_prefix: str = "screen"
    # No tray icon / no popup noise — control via hotkey and stop.bat
    stealth: bool = True
    # HTTP/SOCKS proxy for Bot API, e.g. socks5://127.0.0.1:1080
    proxy_url: str = ""
    # MTProto proxy from https://t.me/proxy?...
    mtproto_server: str = ""
    mtproto_port: int = 0
    mtproto_secret: str = ""
    # Optional override; for MTProto empty values fall back to Telegram Desktop defaults
    api_id: int = 0
    api_hash: str = ""

    def all_chat_ids(self) -> list[str]:
        ids = _clean_ids(list(self.chat_ids))
        primary = str(self.chat_id).strip()
        if primary and not primary.startswith("PASTE_") and primary not in ids:
            ids.insert(0, primary)
        return ids

    def add_chat_id(self, chat_id: str) -> bool:
        chat_id = str(chat_id).strip()
        if not chat_id or chat_id.startswith("PASTE_"):
            return False
        ids = self.all_chat_ids()
        if chat_id in ids:
            self.chat_ids = ids
            self.chat_id = ids[0]
            return False
        ids.append(chat_id)
        self.chat_ids = ids
        self.chat_id = ids[0]
        return True

    def resolved_api_id(self) -> int:
        return int(self.api_id)

    def resolved_api_hash(self) -> str:
        return self.api_hash

    def validate_runtime(self) -> None:
        if not self.bot_token or self.bot_token.startswith("PASTE_"):
            raise RuntimeError("Укажите bot_token в config.json")
        if not self.all_chat_ids():
            raise RuntimeError(
                "Нет получателей. Запустите: python main.py --fetch-chat "
                "или python main.py --add-chat"
            )
        if self.interval_seconds < 5:
            raise RuntimeError("interval_seconds должен быть >= 5")
        if not 10 <= self.jpeg_quality <= 95:
            raise RuntimeError("jpeg_quality должен быть в диапазоне 10..95")


def ensure_config_file() -> Path:
    if not CONFIG_PATH.exists():
        if EXAMPLE_PATH.exists():
            shutil.copyfile(EXAMPLE_PATH, CONFIG_PATH)
        else:
            save_config(AppConfig())
    return CONFIG_PATH


def load_config() -> AppConfig:
    ensure_config_file()
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = AppConfig(
        bot_token=str(raw.get("bot_token", "")).strip(),
        chat_id=str(raw.get("chat_id", "")).strip(),
        chat_ids=_clean_ids(list(raw.get("chat_ids") or [])),
        interval_seconds=int(raw.get("interval_seconds", 300)),
        jpeg_quality=int(raw.get("jpeg_quality", 70)),
        hotkey=str(raw.get("hotkey", "ctrl+shift+s")).strip().lower(),
        allowed_machine_id=str(raw.get("allowed_machine_id", "")).strip(),
        caption_prefix=str(raw.get("caption_prefix", "screen")).strip() or "screen",
        stealth=bool(raw.get("stealth", True)),
        proxy_url=str(raw.get("proxy_url", "")).strip(),

        mtproto_server=str(raw.get("mtproto_server", "")).strip(),
        mtproto_port=int(raw.get("mtproto_port", 0) or 0),
        mtproto_secret=str(raw.get("mtproto_secret", "")).strip(),
        api_id=int(raw.get("api_id", 0) or 0),
        api_hash=str(raw.get("api_hash", "")).strip(),
    )
    # Normalize primary + list
    ids = cfg.all_chat_ids()
    cfg.chat_ids = ids
    cfg.chat_id = ids[0] if ids else cfg.chat_id
    return cfg


def save_config(cfg: AppConfig) -> None:
    ids = cfg.all_chat_ids()
    cfg.chat_ids = ids
    cfg.chat_id = ids[0] if ids else cfg.chat_id
    CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def bind_this_machine(*, write_lock: bool = False) -> str:
    from app import owner_lock

    machine_id = current_machine_id()
    baked = (owner_lock.OWNER_MACHINE_ID or "").strip()
    if baked and baked != machine_id and not owner_lock.ALLOW_REBIND:
        raise RuntimeError(
            "Жёсткая привязка уже задана на другую машину. "
            "Перепривязка на чужом ПК отключена (ALLOW_REBIND=False)."
        )
    if baked and not write_lock and not owner_lock.ALLOW_REBIND:
        # Still refresh config.json for convenience on the owner machine.
        pass

    cfg = load_config()
    cfg.allowed_machine_id = machine_id
    save_config(cfg)

    if write_lock:
        if baked and baked != machine_id and not owner_lock.ALLOW_REBIND:
            raise RuntimeError("Нельзя перезаписать owner_lock на этой машине.")
        lock_path = ROOT / "app" / "owner_lock.py"
        lock_path.write_text(
            (
                '"""Hard machine lock baked into source.\n\n'
                "Unlike config.json, this cannot be casually rewritten with --bind on another PC\n"
                "unless ALLOW_REBIND is explicitly set True (owner-only).\n"
                '"""\n\n'
                "from __future__ import annotations\n\n"
                "# Fingerprint of the only allowed Windows machine (sha256[:32]).\n"
                "# Filled by: python main.py --bind --lock\n"
                f'OWNER_MACHINE_ID = "{machine_id}"\n\n'
                "# Keep False so copies of the app cannot re-bind themselves on another PC.\n"
                "ALLOW_REBIND = False\n"
            ),
            encoding="utf-8",
        )
    return machine_id
