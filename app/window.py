from __future__ import annotations

import io
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

from PIL import Image, ImageTk

from app.capture import grab_screenshot_jpeg
from app.config import AppConfig
from app.telegram_sender import HttpTelegramSender, TelegramError


class ScreenWindow:
    def __init__(self, root: tk.Tk, config: AppConfig, sender: HttpTelegramSender) -> None:
        self.root = root
        self.config = config
        self.sender = sender
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.photo: tuple[bytes, str] | None = None
        self.preview_image: ImageTk.PhotoImage | None = None

        root.title("Screen → Telegram")
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text=f"Чат Telegram: {config.chat_id}").grid(sticky="w")
        self.preview = ttk.Label(frame)
        self.preview.grid(pady=12)
        controls = ttk.Frame(frame)
        controls.grid(sticky="w")
        self.capture_button = ttk.Button(controls, text="Сделать снимок", command=self.capture)
        self.capture_button.grid(row=0, column=0, padx=(0, 8))
        self.send_button = ttk.Button(controls, text="Отправить снимок", command=self.send, state="disabled")
        self.send_button.grid(row=0, column=1)
        self.status = tk.StringVar(value="Сделайте снимок и проверьте его перед отправкой.")
        ttk.Label(frame, textvariable=self.status, wraplength=480).grid(sticky="w", pady=(12, 0))

    def capture(self) -> None:
        self.photo = None
        self.preview.configure(image="")
        self.preview_image = None
        self.capture_button.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self.root.withdraw()
        self.root.after(250, self.capture_preview)

    def capture_preview(self) -> None:
        try:
            photo = grab_screenshot_jpeg(self.config.jpeg_quality)
            with Image.open(io.BytesIO(photo[0])) as image:
                image.thumbnail((640, 400))
                self.preview_image = ImageTk.PhotoImage(image, master=self.root)
            self.preview.configure(image=self.preview_image)
            self.photo = photo
            self.send_button.configure(state="normal")
            self.status.set("Снимок готов к отправке.")
        except Exception:
            self.status.set("Не удалось сделать снимок. Проверьте доступ к захвату экрана.")
        finally:
            self.root.deiconify()
            self.capture_button.configure(state="normal")

    def send(self) -> None:
        if self.photo is None:
            return
        image_bytes, filename = self.photo
        self.capture_button.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self.status.set("Отправка…")
        future = self.executor.submit(self.sender.send_photo, image_bytes, filename, self.config.chat_id)

        def finish_send() -> None:
            if not future.done():
                self.root.after(100, finish_send)
                return
            try:
                future.result()
            except TelegramError as exc:
                self.status.set(str(exc))
                self.send_button.configure(state="normal")
            else:
                self.status.set("Снимок отправлен.")
                self.photo = None
            self.capture_button.configure(state="normal")

        finish_send()

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def run_window(config: AppConfig, sender: HttpTelegramSender) -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        raise ValueError("Откройте приложение в доступном графическом сеансе.") from None
    ScreenWindow(root, config, sender)
    root.mainloop()
