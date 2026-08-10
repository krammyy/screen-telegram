from __future__ import annotations

import hashlib
import platform
import winreg

from app import owner_lock


def _machine_guid() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except OSError:
        return "unknown-guid"


def _hostname() -> str:
    return platform.node().strip().lower() or "unknown-host"


def current_machine_id() -> str:
    """Stable fingerprint for this Windows machine."""
    raw = f"{_hostname()}|{_machine_guid()}|{platform.system()}|{platform.machine()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def describe_machine() -> str:
    return f"{_hostname()} ({platform.system()} {platform.machine()})"


def assert_allowed(allowed_machine_id: str) -> None:
    """Refuse to run unless this PC matches the baked-in owner lock (and config)."""
    current = current_machine_id()
    baked = (owner_lock.OWNER_MACHINE_ID or "").strip()

    if baked:
        if baked != current:
            raise RuntimeError(
                "Приложение жёстко привязано к другой машине и здесь неактивно.\n"
                f"Текущая: {describe_machine()} / {current}"
            )
        # Keep config in sync when possible, but baked lock is authoritative.
        if allowed_machine_id and allowed_machine_id != current:
            raise RuntimeError(
                "config.json указывает другую машину, чем жёсткая привязка.\n"
                "На чужом ПК запуск запрещён."
            )
        return

    if not allowed_machine_id:
        raise RuntimeError(
            "Нет привязки к машине. На своём ПК выполните:\n"
            "  python main.py --bind --lock"
        )
    if allowed_machine_id != current:
        raise RuntimeError(
            "Приложение привязано к другой машине и здесь неактивно.\n"
            f"Текущая: {describe_machine()} / {current}\n"
            f"Разрешена: {allowed_machine_id}"
        )
