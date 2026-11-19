# Screen → Telegram

Приложение делает снимок экрана и отправляет его в выбранный чат через **вашего Telegram-бота**. Снимок можно проверить в окне перед отправкой. Настройки привязаны к боту и чату, поэтому проект можно запустить на другом компьютере с графическим сеансом и разрешением на захват экрана.

## Установка

Нужны Python 3.10+ с Tkinter и доступ к Telegram Bot API. Выполните из папки проекта:

```text
python -m pip install -r requirements.txt
```

## Настройка и запуск

1. Создайте своего бота через [@BotFather](https://t.me/BotFather) и напишите ему в Telegram.
2. Скопируйте `config.example.json` в `config.json` и укажите токен в `bot_token`.
3. Выполните `python main.py --fetch-chat` и перенесите ID нужного чата в `chat_id`.
4. Запустите `python main.py` или `run.bat` в Windows. Нажмите **Сделать снимок**, затем **Отправить снимок**.

При необходимости задайте `proxy_url` для HTTP/SOCKS или `jpeg_quality` в диапазоне 10–95. Храните токен в локальном `config.json`.

Для сборки Windows EXE установите PyInstaller (`python -m pip install pyinstaller`) и запустите `build_desktop_exe.bat`. Скопируйте `config.json` рядом с `dist/ScreenTelegram.exe`.
