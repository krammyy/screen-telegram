from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from pynput import keyboard

from app.capture import grab_screenshot_jpeg
from app.config import AppConfig, load_config, save_config
from app.machine import describe_machine
from app.telegram_sender import MtprotoTelegramSender, create_sender

log = logging.getLogger("screen-telegram")
ROOT = Path(__file__).resolve().parent.parent


def _make_icon(paused: bool = False, *, invisible: bool = False) -> Image.Image:
    if invisible:
        return Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = (180, 90, 40, 255) if paused else (30, 120, 90, 255)
    draw.ellipse((4, 4, 60, 60), fill=color)
    draw.rectangle((20, 22, 44, 42), outline=(245, 245, 245, 255), width=3)
    draw.ellipse((28, 28, 36, 36), fill=(245, 245, 245, 255))
    return image


def _parse_hotkey(hotkey: str) -> set[keyboard.Key | keyboard.KeyCode]:
    mapping = {
        "ctrl": keyboard.Key.ctrl_l,
        "control": keyboard.Key.ctrl_l,
        "alt": keyboard.Key.alt_l,
        "shift": keyboard.Key.shift_l,
        "win": keyboard.Key.cmd,
        "cmd": keyboard.Key.cmd,
    }
    keys: set[keyboard.Key | keyboard.KeyCode] = set()
    for part in hotkey.lower().split("+"):
        token = part.strip()
        if not token:
            continue
        if token in mapping:
            keys.add(mapping[token])
        elif len(token) == 1:
            keys.add(keyboard.KeyCode.from_char(token))
        else:
            raise ValueError(f"Неподдерживаемая часть hotkey: {token}")
    if not keys:
        raise ValueError("Пустой hotkey")
    return keys


class ScreenTelegramApp:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.stealth = bool(cfg.stealth)
        self.sender = create_sender(cfg)
        self.paused = False
        self._stop = threading.Event()
        self._busy = threading.Lock()
        self._sender_lock = threading.Lock()
        self.last_status = "запуск..."
        self.last_ok_at: str | None = None
        self.icon: pystray.Icon | None = None
        if not self.stealth:
            self.icon = pystray.Icon(
                "screen-telegram",
                _make_icon(False),
                "Screen → Telegram",
                menu=self._build_menu(),
            )
        self._hotkey_listener: keyboard.Listener | None = None
        self._pressed: set[keyboard.Key | keyboard.KeyCode] = set()
        self._target_hotkey = _parse_hotkey(cfg.hotkey)
        self._enable_auto_add_recipients()

    def _enable_auto_add_recipients(self) -> None:
        if not isinstance(self.sender, MtprotoTelegramSender):
            return

        def on_new(chat_id: str, title: str) -> None:
            cfg = load_config()
            if not cfg.add_chat_id(chat_id):
                return
            save_config(cfg)
            self.cfg = cfg
            with self._sender_lock:
                self.sender.set_chat_ids(cfg.all_chat_ids())
            self._set_status(f"добавлен получатель {title}")

        try:
            self.sender.start_auto_add_chats(self.cfg.all_chat_ids(), on_new)
        except Exception as exc:
            log.warning("auto-add recipients disabled: %s", exc)

    def _reconnect_sender(self) -> None:
        """Recreate Telegram connection after transport errors."""
        with self._sender_lock:
            old = self.sender
            try:
                old.close()
            except Exception:
                pass
            self.cfg = load_config()
            self.sender = create_sender(self.cfg)
            self._enable_auto_add_recipients()
            log.info("telegram sender reconnected")

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda _item: f"Статус: {self.last_status}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _item: f"Получателей: {len(self.cfg.all_chat_ids())}",
                None,
                enabled=False,
            ),
            pystray.MenuItem("Снять сейчас", self.capture_now),
            pystray.MenuItem(
                lambda _item: "Продолжить" if self.paused else "Пауза",
                self.toggle_pause,
            ),
            pystray.MenuItem("Отправить тест в Telegram", self.send_test),
            pystray.MenuItem("Переподключить Telegram", self.reconnect_now),
            # No Exit in menu: process must stay alive; use stop.bat only if needed
        )

    def _set_status(self, text: str) -> None:
        self.last_status = text
        log.info(text)
        if self.icon is None:
            return
        try:
            self.icon.title = f"Screen → Telegram | {text}"
            self.icon.update_menu()
        except Exception:
            pass

    def toggle_pause(self, _icon=None, _item=None) -> None:
        self.paused = not self.paused
        if self.icon is not None:
            self.icon.icon = _make_icon(self.paused)
        self._set_status("пауза" if self.paused else "активно")

    def quit_app(self, _icon=None, _item=None) -> None:
        # Kept for emergency API use; not exposed in tray menu.
        self._stop.set()
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        try:
            self.sender.close()
        except Exception:
            pass
        if self.icon is not None:
            self.icon.stop()

    def reconnect_now(self, _icon=None, _item=None) -> None:
        def worker() -> None:
            try:
                self._set_status("переподключение...")
                self._reconnect_sender()
                self._set_status("переподключено")
            except Exception as exc:
                self._set_status(f"reconnect fail: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def send_test(self, _icon=None, _item=None) -> None:
        def worker() -> None:
            try:
                with self._sender_lock:
                    self.sender.send_text(
                        f"Тест Screen→Telegram\n{describe_machine()}\n{datetime.now():%Y-%m-%d %H:%M:%S}"
                    )
                self._set_status("тест отправлен")
            except Exception as exc:
                self._set_status(f"ошибка теста: {exc}")
                try:
                    self._reconnect_sender()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def capture_now(self, _icon=None, _item=None) -> None:
        threading.Thread(target=self._capture_and_send, args=("manual",), daemon=True).start()

    def _capture_and_send(self, reason: str) -> None:
        if not self._busy.acquire(blocking=False):
            self._set_status("уже идёт съёмка")
            return
        try:
            self._set_status(f"съёмка ({reason})...")
            # Pick up chat_ids changes without restart
            try:
                fresh = load_config()
                self.cfg = fresh
                self.stealth = bool(fresh.stealth)
                with self._sender_lock:
                    self.sender.set_chat_ids(fresh.all_chat_ids())
            except Exception:
                pass
            image_bytes, filename = grab_screenshot_jpeg(self.cfg.jpeg_quality)
            caption = (
                f"{self.cfg.caption_prefix} | {reason} | "
                f"{describe_machine()} | {datetime.now():%Y-%m-%d %H:%M:%S}"
            )
            try:
                with self._sender_lock:
                    self.sender.send_photo(image_bytes, filename, caption)
            except Exception as send_exc:
                log.warning("send failed, reconnecting: %s", send_exc)
                self._reconnect_sender()
                with self._sender_lock:
                    self.sender.send_photo(image_bytes, filename, caption)
            self.last_ok_at = datetime.now().strftime("%H:%M:%S")
            self._set_status(f"ок {self.last_ok_at}")
        except Exception as exc:
            log.exception("capture/send error")
            self._set_status(f"ошибка: {exc}")
        finally:
            self._busy.release()

    def _scheduler_loop(self) -> None:
        # First shot shortly after start, then on interval.
        next_at = time.monotonic() + 5
        while not self._stop.is_set():
            try:
                now = time.monotonic()
                if not self.paused and now >= next_at:
                    self._capture_and_send("timer")
                    next_at = time.monotonic() + max(5, self.cfg.interval_seconds)
            except Exception:
                log.exception("scheduler tick failed")
                next_at = time.monotonic() + max(5, self.cfg.interval_seconds)
            self._stop.wait(0.5)

    def _normalize_key(self, key: keyboard.Key | keyboard.KeyCode):
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return keyboard.Key.ctrl_l
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            return keyboard.Key.alt_l
        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            return keyboard.Key.shift_l
        if isinstance(key, keyboard.KeyCode) and key.char:
            return keyboard.KeyCode.from_char(key.char.lower())
        return key

    def _on_press(self, key) -> None:
        norm = self._normalize_key(key)
        self._pressed.add(norm)
        if self._target_hotkey.issubset(self._pressed):
            self.capture_now()

    def _on_release(self, key) -> None:
        norm = self._normalize_key(key)
        self._pressed.discard(norm)

    def _start_hotkey(self) -> None:
        self._hotkey_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    def _stealth_wait(self) -> None:
        """Keep process alive without a tray icon. Stop via stop.bat / stop.flag."""
        stop_flag = ROOT / "stop.flag"
        log.info("stealth mode: no tray icon; stop with stop.bat")
        while not self._stop.is_set():
            if stop_flag.exists():
                log.info("stop.flag seen — stealth exit")
                self.quit_app()
                return
            self._stop.wait(1.0)

    def run(self) -> None:
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        try:
            self._start_hotkey()
            self._set_status(f"активно, hotkey={self.cfg.hotkey}")
        except Exception as exc:
            self._set_status(f"без hotkey: {exc}")
        if self.stealth or self.icon is None:
            self._stealth_wait()
        else:
            self.icon.run()


def run_tray(cfg: AppConfig) -> None:
    ScreenTelegramApp(cfg).run()
