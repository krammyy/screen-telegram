from __future__ import annotations

import asyncio
import io
import threading
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import requests


def normalize_mtproto_secret(secret: str) -> str:
    """Convert t.me base64 secret to hex for Telethon, keep hex as-is."""
    secret = secret.strip()
    if not secret:
        raise ValueError("Пустой MTProto secret")
    hex_chars = set("0123456789abcdefABCDEF")
    if all(c in hex_chars for c in secret) and len(secret) % 2 == 0:
        return secret.lower()
    import base64

    padded = secret + "=" * ((4 - len(secret) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise ValueError(f"Не удалось декодировать MTProto secret: {exc}") from exc
    return raw.hex()


def parse_mtproto_proxy_link(link: str) -> dict[str, Any]:
    """Parse https://t.me/proxy?server=...&port=...&secret=..."""
    parsed = urlparse(link.strip())
    if parsed.scheme in {"http", "https"} and parsed.netloc in {"t.me", "telegram.me"}:
        qs = parse_qs(parsed.query)
        server = (qs.get("server") or [""])[0].strip()
        port = int((qs.get("port") or ["0"])[0])
        secret = normalize_mtproto_secret((qs.get("secret") or [""])[0].strip())
        if not server or not port or not secret:
            raise ValueError("В ссылке proxy не хватает server/port/secret")
        return {"server": server, "port": port, "secret": secret}
    raise ValueError("Ожидалась ссылка вида https://t.me/proxy?server=...&port=...&secret=...")


def _peer(chat_id: str):
    return int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id


class HttpTelegramSender:
    def __init__(
        self,
        bot_token: str,
        chat_ids: list[str],
        proxy_url: str = "",
        timeout: int = 60,
    ) -> None:
        self.bot_token = bot_token
        self.chat_ids = list(chat_ids)
        self.chat_id = self.chat_ids[0] if self.chat_ids else ""
        self.timeout = timeout
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self.session = requests.Session()
        if proxy_url:
            self.session.proxies.update({"http": proxy_url, "https": proxy_url})

    def set_chat_ids(self, chat_ids: list[str]) -> None:
        self.chat_ids = list(chat_ids)
        self.chat_id = self.chat_ids[0] if self.chat_ids else ""

    def send_photo(self, image_bytes: bytes, filename: str, caption: str) -> None:
        url = f"{self.base}/sendPhoto"
        errors: list[str] = []
        for chat_id in self.chat_ids:
            files = {"photo": (filename, image_bytes, "image/jpeg")}
            data = {"chat_id": chat_id, "caption": caption}
            response = self.session.post(url, data=data, files=files, timeout=self.timeout)
            if response.status_code != 200 or not response.json().get("ok"):
                errors.append(f"{chat_id}: {response.text[:200]}")
        if errors and len(errors) == len(self.chat_ids):
            raise RuntimeError("Telegram sendPhoto failed: " + " | ".join(errors))
        if errors:
            raise RuntimeError("Частичная ошибка sendPhoto: " + " | ".join(errors))

    def send_text(self, text: str) -> None:
        url = f"{self.base}/sendMessage"
        errors: list[str] = []
        for chat_id in self.chat_ids:
            response = self.session.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=self.timeout,
            )
            if response.status_code != 200 or not response.json().get("ok"):
                errors.append(f"{chat_id}: {response.text[:200]}")
        if errors and len(errors) == len(self.chat_ids):
            raise RuntimeError("Telegram sendMessage failed: " + " | ".join(errors))

    def get_updates(self) -> dict:
        response = self.session.get(f"{self.base}/getUpdates", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self.session.close()


class MtprotoTelegramSender:
    """Bot sender over MTProto proxy (t.me/proxy), via Telethon."""

    def __init__(
        self,
        bot_token: str,
        chat_ids: list[str],
        api_id: int,
        api_hash: str,
        mtproto: dict[str, Any],
        session_path: str,
    ) -> None:
        from telethon import TelegramClient
        from telethon.network.connection.tcpmtproxy import (
            ConnectionTcpMTProxyRandomizedIntermediate,
        )

        self.bot_token = bot_token
        self.chat_ids = list(chat_ids)
        self.chat_id = self.chat_ids[0] if self.chat_ids else "0"
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._auto_handler = None

        secret_raw = str(mtproto["secret"]).strip()
        secret_hex = normalize_mtproto_secret(secret_raw)
        # ee... = FakeTLS; plain Telethon can't do it, need TelethonFakeTLS
        if secret_hex.startswith("ee"):
            import TelethonFakeTLS

            # Library expects base64 without leading '7', or hex without leading 'ee'
            if not all(c in "0123456789abcdefABCDEF" for c in secret_raw):
                proxy_secret = secret_raw[1:] if secret_raw.startswith("7") else secret_raw
            else:
                proxy_secret = secret_hex[2:]
            connection = TelethonFakeTLS.ConnectionTcpMTProxyFakeTLS
            proxy = (mtproto["server"], int(mtproto["port"]), proxy_secret)
        else:
            connection = ConnectionTcpMTProxyRandomizedIntermediate
            proxy = (mtproto["server"], int(mtproto["port"]), secret_hex)

        self._client = TelegramClient(
            session_path,
            int(api_id),
            api_hash,
            loop=self._loop,
            connection=connection,
            proxy=proxy,
        )

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=90):
            raise RuntimeError("Не удалось подключить Telethon через MTProto proxy за 90с")
        if self._error is not None:
            raise RuntimeError(f"MTProto connect failed: {self._error}") from self._error

    def set_chat_ids(self, chat_ids: list[str]) -> None:
        self.chat_ids = list(chat_ids)
        self.chat_id = self.chat_ids[0] if self.chat_ids else "0"

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)

        async def _boot():
            await self._client.connect()
            if not await self._client.is_user_authorized():
                await self._client.sign_in(bot_token=self.bot_token)

        try:
            self._loop.run_until_complete(_boot())
            self._ready.set()
            self._loop.run_forever()
        except BaseException as exc:
            self._error = exc
            self._ready.set()

    def _call(self, coro, timeout: float = 120):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    def send_photo(self, image_bytes: bytes, filename: str, caption: str) -> None:
        async def _send():
            errors: list[str] = []
            for chat_id in self.chat_ids:
                try:
                    bio = io.BytesIO(image_bytes)
                    bio.name = filename
                    await self._client.send_file(_peer(chat_id), bio, caption=caption)
                except Exception as exc:
                    errors.append(f"{chat_id}: {exc}")
            if errors and len(errors) == len(self.chat_ids):
                raise RuntimeError("sendPhoto failed: " + " | ".join(errors))
            if errors:
                raise RuntimeError("Частичная ошибка sendPhoto: " + " | ".join(errors))

        self._call(_send())

    def send_text(self, text: str) -> None:
        async def _send():
            errors: list[str] = []
            for chat_id in self.chat_ids:
                try:
                    await self._client.send_message(_peer(chat_id), text)
                except Exception as exc:
                    errors.append(f"{chat_id}: {exc}")
            if errors and len(errors) == len(self.chat_ids):
                raise RuntimeError("sendMessage failed: " + " | ".join(errors))

        self._call(_send())

    def get_me_username(self) -> str:
        async def _me():
            me = await self._client.get_me()
            return me.username or str(me.id)

        return self._call(_me())

    def wait_incoming_chat(
        self,
        timeout: float = 120,
        ignore_ids: list[str] | None = None,
    ) -> tuple[str, str]:
        found = self.wait_incoming_chats(count=1, timeout=timeout, ignore_ids=ignore_ids)
        return found[0]

    def wait_incoming_chats(
        self,
        count: int = 1,
        timeout: float = 180,
        ignore_ids: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        from telethon import events

        ignore = {str(x) for x in (ignore_ids or [])}
        need = max(1, int(count))

        async def _wait():
            done = asyncio.Event()
            found: list[tuple[str, str]] = []
            seen = set(ignore)

            @self._client.on(events.NewMessage(incoming=True))
            async def handler(event):
                chat_id = str(event.chat_id)
                if chat_id in seen:
                    return
                seen.add(chat_id)
                chat = await event.get_chat()
                title = (
                    getattr(chat, "title", None)
                    or getattr(chat, "username", None)
                    or getattr(chat, "first_name", None)
                    or "?"
                )
                found.append((chat_id, str(title)))
                print(f"Пойман получатель {len(found)}/{need}: {chat_id} ({title})", flush=True)
                if len(found) >= need:
                    done.set()

            try:
                await asyncio.wait_for(done.wait(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                if found:
                    return found
                raise TimeoutError(
                    "Никто новый не написал боту за отведённое время. "
                    "Оба пользователя должны открыть @Screen_checker_oni_bot, "
                    "нажать Start и отправить любое сообщение."
                ) from exc
            finally:
                self._client.remove_event_handler(handler)
            return found

        return self._call(_wait(), timeout=timeout + 10)

    def start_auto_add_chats(
        self,
        known_ids: list[str],
        on_new: Callable[[str, str], None],
    ) -> None:
        """Background: when a new user writes the bot, call on_new(chat_id, title)."""
        from telethon import events

        known = set(str(x) for x in known_ids)

        async def _register():
            if self._auto_handler is not None:
                self._client.remove_event_handler(self._auto_handler)

            @self._client.on(events.NewMessage(incoming=True))
            async def handler(event):
                chat_id = str(event.chat_id)
                if chat_id in known:
                    return
                known.add(chat_id)
                chat = await event.get_chat()
                title = (
                    getattr(chat, "title", None)
                    or getattr(chat, "username", None)
                    or getattr(chat, "first_name", None)
                    or "?"
                )
                on_new(chat_id, str(title))

            self._auto_handler = handler

        self._call(_register())

    def close(self) -> None:
        async def _close():
            await self._client.disconnect()

        try:
            self._call(_close(), timeout=30)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)


def create_sender(cfg) -> HttpTelegramSender | MtprotoTelegramSender:
    chat_ids = cfg.all_chat_ids() or ["0"]
    if cfg.mtproto_server and cfg.mtproto_port and cfg.mtproto_secret:
        from app.config import ROOT

        return MtprotoTelegramSender(
            bot_token=cfg.bot_token,
            chat_ids=chat_ids,
            api_id=cfg.resolved_api_id(),
            api_hash=cfg.resolved_api_hash(),
            mtproto={
                "server": cfg.mtproto_server,
                "port": int(cfg.mtproto_port),
                "secret": cfg.mtproto_secret,
            },
            session_path=str(ROOT / "screen_bot_session"),
        )
    return HttpTelegramSender(cfg.bot_token, chat_ids, cfg.proxy_url)


# backward-compatible alias
TelegramSender = HttpTelegramSender
