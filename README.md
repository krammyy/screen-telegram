# Screen → Telegram

Утилита для **вашей** Windows-машины: снимает экран и шлёт JPEG в Telegram.
На других ПК не работает — жёсткая привязка в `app/owner_lock.py`.

В режиме `stealth: true` иконки в трее нет, окон при старте нет. Остановка: `stop.bat`.

## Установка

```bat
cd screen-telegram
python -m pip install -r requirements.txt
copy config.example.json config.json
```

## Настройка Telegram

1. В [@BotFather](https://t.me/BotFather) создай бота → получи `bot_token`.
2. Напиши боту любое сообщение.
3. Открой в браузере:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Найди `"chat":{"id": ...}` — это `chat_id` (для лички число, для группы часто отрицательное).
5. Впиши `bot_token` в `config.json`.
6. Если `api.telegram.org` недоступен:
   - **MTProto** (ссылка `t.me/proxy?...`):

```bat
python main.py --set-proxy "https://t.me/proxy?server=...&port=...&secret=..."
```

     Затем получи `api_id` и `api_hash` на https://my.telegram.org → API development tools и впиши в `config.json`.
   - либо обычный HTTP/SOCKS в `proxy_url`, например `socks5://127.0.0.1:1080`.
7. Напиши боту сообщение и выполни:

```bat
python main.py --fetch-chat
```

## Привязка только к этой машине

```bat
python main.py --bind --lock
```

Это записывает fingerprint в `config.json` **и** зашивает его в `app/owner_lock.py`.
На чужом ПК:
- приложение молча не стартует;
- `--bind` не перепривяжет (пока `ALLOW_REBIND = False`).

Проверка fingerprint:

```bat
python main.py --whoami
```

## Запуск

```bat
python main.py
```

или `run.bat` / `ScreenTelegram.exe` с рабочего стола.

- Stealth: без иконки в трее; ручной снимок — горячая клавиша (`ctrl+shift+s` по умолчанию).
- Остановка: `stop.bat`.
- Чтобы снова видеть трей: `"stealth": false` в `config.json`.

## Параметры `config.json`

| Поле | Смысл |
|------|--------|
| `bot_token` | токен бота |
| `chat_id` | куда слать |
| `interval_seconds` | минимум 5 |
| `jpeg_quality` | 10..95 |
| `hotkey` | например `ctrl+shift+s` |
| `allowed_machine_id` | дублирует привязку; авторитет — `owner_lock.py` |
| `stealth` | `true` = без иконки/окон |
| `caption_prefix` | префикс подписи к фото |

Лог: `screen-telegram.log`.
