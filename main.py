from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import bind_this_machine, ensure_config_file, load_config, save_config
from app.machine import assert_allowed, current_machine_id, describe_machine
from app.telegram_sender import create_sender, parse_mtproto_proxy_link
from app.tray_app import run_tray


def setup_logging() -> None:
    log_path = ROOT / "screen-telegram.log"
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    # pythonw has no console — skip stdout handler to avoid noise/errors
    if sys.stdout is not None and hasattr(sys.stdout, "write"):
        try:
            if sys.stdout.fileno() >= 0:
                handlers.append(logging.StreamHandler(sys.stdout))
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def cmd_bind(write_lock: bool = False) -> int:
    ensure_config_file()
    machine_id = bind_this_machine(write_lock=write_lock)
    print("Машина привязана.")
    print(f"Описание : {describe_machine()}")
    print(f"MachineID: {machine_id}")
    print(f"Конфиг   : {ROOT / 'config.json'}")
    if write_lock:
        print(f"Жёсткий lock: {ROOT / 'app' / 'owner_lock.py'}")
        print("На других ПК приложение не запустится (перепривязка отключена).")
    return 0


def cmd_whoami() -> int:
    print(f"Описание : {describe_machine()}")
    print(f"MachineID: {current_machine_id()}")
    return 0


def cmd_set_proxy(link: str) -> int:
    cfg = load_config()
    parsed = parse_mtproto_proxy_link(link)
    cfg.mtproto_server = parsed["server"]
    cfg.mtproto_port = int(parsed["port"])
    cfg.mtproto_secret = parsed["secret"]
    save_config(cfg)
    print("MTProto proxy сохранён в config.json:")
    print(f"  server: {cfg.mtproto_server}")
    print(f"  port  : {cfg.mtproto_port}")
    print(f"  secret: {cfg.mtproto_secret[:8]}...")
    return 0


def cmd_list_chats() -> int:
    cfg = load_config()
    ids = cfg.all_chat_ids()
    if not ids:
        print("Получателей нет.")
        return 1
    print("Получатели скриншотов:")
    for cid in ids:
        mark = " (primary)" if cid == cfg.chat_id else ""
        print(f"  {cid}{mark}")
    return 0


def _save_found_chat(chat_id: str, title: str, append: bool) -> None:
    cfg = load_config()
    if append:
        added = cfg.add_chat_id(chat_id)
        save_config(cfg)
        if added:
            print(f"Добавлен получатель: {chat_id} ({title})")
        else:
            print(f"Уже был в списке: {chat_id} ({title})")
    else:
        cfg.chat_ids = [chat_id]
        cfg.chat_id = chat_id
        save_config(cfg)
        print(f"Записал chat_id={chat_id} ({title})")
    print(f"Всего получателей: {len(load_config().all_chat_ids())}")


def cmd_fetch_chat(append: bool = False, need_count: int = 1) -> int:
    cfg = load_config()
    if not cfg.bot_token or cfg.bot_token.startswith("PASTE_"):
        raise RuntimeError("Сначала укажите bot_token в config.json")

    known = cfg.all_chat_ids()
    using_mtproto = bool(cfg.mtproto_server and cfg.mtproto_port and cfg.mtproto_secret)
    if using_mtproto:
        print("Подключаюсь через MTProto proxy...")
        sender = create_sender(cfg)
        ignore = known if append else []
        already = len(known) if append else 0
        target_new = max(1, need_count)
        if append and already >= need_count:
            print(f"Уже есть {already} получатель(ей). Жду ещё {target_new} новых...")
        print(
            f"Ок. Сейчас ОБА пользователя должны открыть @Screen_checker_oni_bot, "
            f"нажать Start и написать что угодно."
        )
        print(f"Жду новых чатов: {target_new} (таймаут 3 мин)...")
        try:
            found = sender.wait_incoming_chats(
                count=target_new,
                timeout=180,
                ignore_ids=ignore,
            )
        finally:
            sender.close()
        for chat_id, title in found:
            _save_found_chat(chat_id, title, append=True)
        return 0

    sender = create_sender(cfg)
    try:
        payload = sender.get_updates()
    finally:
        sender.close()
    if not payload.get("ok"):
        raise RuntimeError(f"getUpdates failed: {payload}")
    chats: dict[str, str] = {}
    for upd in payload.get("result", []):
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "?"
        chats[str(chat_id)] = str(title)
    if not chats:
        print("Чаты не найдены. Напиши боту любое сообщение и повтори: python main.py --fetch-chat")
        return 1
    print("Найденные chat_id:")
    for cid, title in chats.items():
        print(f"  {cid}  ({title})")
    cfg = load_config()
    for cid in chats:
        cfg.add_chat_id(cid)
    save_config(cfg)
    print(f"Сохранено получателей: {len(cfg.all_chat_ids())}")
    return 0


def cmd_run() -> int:
    ensure_config_file()
    cfg = load_config()
    assert_allowed(cfg.allowed_machine_id)
    cfg.validate_runtime()
    mode = "MTProto" if cfg.mtproto_server else ("HTTP-proxy" if cfg.proxy_url else "direct")
    print(f"Старт на {describe_machine()}")
    print(f"Режим Telegram: {mode}")
    print(f"Получатели: {', '.join(cfg.all_chat_ids())}")
    print(f"Интервал: {cfg.interval_seconds} сек | hotkey: {cfg.hotkey}")
    if cfg.stealth:
        print("Stealth: иконки в трее нет. Остановка: stop.bat")
    else:
        print("Иконка будет в системном трее. Лог: screen-telegram.log")
    print("Лог: screen-telegram.log")
    print("Новый пользователь может просто написать боту — добавится автоматически.")
    print("Для постоянной работы запускайте run.bat (watchdog автоперезапуск).")
    try:
        run_tray(cfg)
    except Exception:
        logging.exception("tray crashed")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Видимая утилита скриншотов с отправкой в Telegram"
    )
    parser.add_argument(
        "--bind",
        action="store_true",
        help="Привязать приложение к текущей машине и записать allowed_machine_id",
    )
    parser.add_argument(
        "--lock",
        action="store_true",
        help="С --bind: зашить machine id в app/owner_lock.py (чужой ПК не перепривяжет)",
    )
    parser.add_argument(
        "--whoami",
        action="store_true",
        help="Показать fingerprint текущей машины",
    )
    parser.add_argument(
        "--fetch-chat",
        action="store_true",
        help="Получить chat_id (через MTProto или Bot API) и записать в config.json",
    )
    parser.add_argument(
        "--add-chat",
        action="store_true",
        help="Дождаться НОВОГО пользователя и добавить его в получатели",
    )
    parser.add_argument(
        "--sync-two",
        action="store_true",
        help="Сбросить получателей и поймать 2 пользователей, которые напишут боту",
    )
    parser.add_argument(
        "--list-chats",
        action="store_true",
        help="Показать список получателей",
    )
    parser.add_argument(
        "--set-proxy",
        metavar="LINK",
        help="Сохранить MTProto proxy из ссылки https://t.me/proxy?...",
    )
    args = parser.parse_args(argv)

    try:
        if args.bind:
            return cmd_bind(write_lock=bool(args.lock))
        if args.whoami:
            return cmd_whoami()
        if args.set_proxy:
            return cmd_set_proxy(args.set_proxy)
        if args.list_chats:
            return cmd_list_chats()
        if args.sync_two:
            cfg = load_config()
            cfg.chat_ids = []
            cfg.chat_id = ""
            save_config(cfg)
            print("Список получателей очищен. Жду 2 пользователей...")
            return cmd_fetch_chat(append=False, need_count=2)
        if args.add_chat:
            return cmd_fetch_chat(append=True, need_count=1)
        if args.fetch_chat:
            return cmd_fetch_chat(append=False, need_count=1)
        return cmd_run()
    except Exception as exc:
        logging.error("%s", exc)
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
