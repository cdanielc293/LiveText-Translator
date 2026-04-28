import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab, Image, ImageDraw
import easyocr
import numpy as np
from deep_translator import GoogleTranslator
import keyboard
import threading
import re
import os
import sys
import json
from gtts import gTTS
import pygame
import pystray
from pystray import MenuItem as item
import winreg
import webbrowser

CONFIG_FILE = "config.json"
APP_NAME = "LiveText Translator"
DEVELOPER = "Daniel Hagbi"
PAYPAL_EMAIL = "cdanielc293@gmail.com"

class LiveTextTranslator:
    def __init__(self):
        self.add_to_startup()
        self.load_config()
        self.is_paused = False
        
        # Load OCR and Audio
        self.reader = easyocr.Reader(['en'])
        self.translator = GoogleTranslator(source='auto', target='iw')
        self.file_path = "translated_words.txt"
        pygame.mixer.init()
        
        self.root = tk.Tk()
        self.root.withdraw() 
        
        self.init_display_window()
        self.setup_tray_icon()
        self.snip_requested = False
        
        keyboard.add_hotkey(self.config["hotkey_translate"], self.request_snip)
        keyboard.add_hotkey(self.config["hotkey_pause"], self.toggle_pause_hotkey)
        
        self.update_translation_display("System Active", f"Developed by {DEVELOPER}\nPress {self.config['hotkey_translate']} to start.")
        self.check_queue()

    def add_to_startup(self):
        try:
            if getattr(sys, 'frozen', False):
                app_path = sys.executable
            else:
                app_path = os.path.abspath(__file__)
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(registry_key, "LiveTextTranslator", 0, winreg.REG_SZ, app_path)
            winreg.CloseKey(registry_key)
        except: pass

    def load_config(self):
        default = {"hotkey_translate": "F2", "hotkey_pause": "F3", "enable_speech": True}
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'w') as f: json.dump(default, f, indent=4)
            self.config = default
        else:
            with open(CONFIG_FILE, 'r') as f: self.config = json.load(f)

    def open_donation(self, amount):
        url = f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business={PAYPAL_EMAIL}&item_name=Support+LiveText+Translator+Project&amount={amount}&currency_code=USD"
        webbrowser.open(url)

    def show_donation_menu(self):
        donate_win = tk.Toplevel(self.display_win)
        donate_win.title("Support Project")
        donate_win.geometry("250x300")
        donate_win.configure(bg='#1a1a1a')
        donate_win.attributes('-topmost', True)
        
        tk.Label(donate_win, text="Choose amount:", font=("Arial", 12, "bold"), fg="white", bg="#1a1a1a").pack(pady=10)
        
        amounts = [5, 10, 20, 30]
        for amt in amounts:
            btn = tk.Button(donate_win, text=f"${amt}", width=15, bg="#2e7d32", fg="white", 
                            font=("Arial", 10, "bold"), command=lambda a=amt: self.open_donation(a))
            btn.pack(pady=5)
        
        tk.Label(donate_win, text="Thank you for your support!", font=("Arial", 8), fg="gray", bg="#1a1a1a").pack(pady=10)

    def init_display_window(self):
        self.display_win = tk.Toplevel(self.root)
        self.display_win.title(APP_NAME)
        self.display_win.attributes('-topmost', True)
        self.display_win.geometry("500x550+50+50")
        self.display_win.configure(bg='#0f0f0f')
        self.display_win.protocol("WM_DELETE_WINDOW", self.display_win.withdraw)
        
        # Header / Branding
        header = tk.Frame(self.display_win, bg='#1a1a1a', height=60)
        header.pack(fill="x")
        tk.Label(header, text=APP_NAME, font=("Segoe UI", 18, "bold"), fg="#4caf50", bg='#1a1a1a').pack(pady=(5,0))
        tk.Label(header, text=f"by {DEVELOPER}", font=("Segoe UI", 9), fg="gray", bg='#1a1a1a').pack()

        # English Box
        self.en_text = tk.Text(self.display_win, font=("Arial", 15), fg="white", bg="#0f0f0f", 
                               bd=0, height=5, wrap=tk.WORD, cursor="hand2", insertofftime=0)
        self.en_text.pack(expand=True, fill="both", padx=20, pady=10)
        self.en_text.tag_configure("center", justify='center')
        self.en_text.tag_configure("highlight", background="#2e7d32", foreground="white")

        tk.Frame(self.display_win, height=1, bg="#333333").pack(fill="x", padx=40)

        # Hebrew Box
        self.he_text = tk.Text(self.display_win, font=("Arial", 15), fg="#e0e0e0", bg="#0f0f0f", 
                               bd=0, height=5, wrap=tk.WORD, cursor="hand2", insertofftime=0)
        self.he_text.pack(expand=True, fill="both", padx=20, pady=10)
        self.he_text.tag_configure("center", justify='center')
        self.he_text.tag_configure("highlight", background="#2e7d32", foreground="white")

        # Info & Support Footer
        footer = tk.Frame(self.display_win, bg='#0f0f0f')
        footer.pack(fill="x", side="bottom", pady=10)
        
        self.word_translation_lbl = tk.Label(footer, text="", font=("Arial", 11, "italic"), fg="#fdd835", bg="#0f0f0f")
        self.word_translation_lbl.pack(pady=5)

        support_btn = tk.Button(footer, text="❤ Support the Project", font=("Arial", 10, "bold"), 
                                fg="white", bg="#d32f2f", padx=10, command=self.show_donation_menu)
        support_btn.pack(pady=5)

    def insert_clickable_words(self, text_widget, text, lang):
        words = text.split()
        for i, word in enumerate(words):
            tag_name = f"word_{lang}_{i}"
            text_widget.insert(tk.END, word, ("center", tag_name))
            text_widget.insert(tk.END, " ", "center")
            text_widget.tag_bind(tag_name, "<Button-1>", lambda e, w=word, t=tag_name, l=lang, tw=text_widget: self.on_exact_word_click(w, t, l, tw))

    def on_exact_word_click(self, word, tag_name, lang, text_widget):
        clean_word = word.strip(" .,?!;:'\"()[]{}")
        if not clean_word: return
        self.en_text.tag_remove("highlight", "1.0", tk.END)
        self.he_text.tag_remove("highlight", "1.0", tk.END)
        ranges = text_widget.tag_ranges(tag_name)
        if ranges: text_widget.tag_add("highlight", ranges[0], ranges[1])
        self.word_translation_lbl.config(text=f"Translating: {clean_word}...")
        threading.Thread(target=self.find_and_highlight_match, args=(clean_word, lang), daemon=True).start()

    def find_and_highlight_match(self, word, lang):
        try:
            if lang == "en":
                translated_word = self.translator.translate(word)
                target_widget = self.he_text
            else:
                translated_word = GoogleTranslator(source='iw', target='en').translate(word)
                target_widget = self.en_text
            self.root.after(0, self.word_translation_lbl.config, {"text": f"{word} ➔ {translated_word}"})
            self.root.after(0, self.highlight_word_in_widget, target_widget, translated_word)
        except: pass

    def highlight_word_in_widget(self, text_widget, word):
        if not word: return
        pos = text_widget.search(word, "1.0", tk.END, nocase=True)
        if pos: text_widget.tag_add("highlight", pos, f"{pos}+{len(word)}c")

    def update_translation_display(self, original, translated):
        self.display_win.deiconify() 
        for widget in [self.en_text, self.he_text]:
            widget.config(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
        
        self.insert_clickable_words(self.en_text, original, "en")
        self.insert_clickable_words(self.he_text, translated, "he")
        
        for widget in [self.en_text, self.he_text]: widget.config(state=tk.DISABLED)
        self.display_win.update()

    def setup_tray_icon(self):
        img = Image.new('RGB', (64, 64), color=(30, 30, 30))
        d = ImageDraw.Draw(img)
        d.text((18, 20), "LT", fill=(0, 255, 0))
        self.icon = pystray.Icon("LiveTextTranslator", img, APP_NAME, pystray.Menu(
            item('Pause / Resume', lambda: self.toggle_pause_hotkey()),
            item('Quit', self.quit_app)
        ))
        threading.Thread(target=self.icon.run, daemon=True).start()

    def toggle_pause_hotkey(self):
        self.is_paused = not self.is_paused
        msg = "SYSTEM PAUSED" if self.is_paused else "SYSTEM ACTIVE"
        self.root.after(0, self.update_translation_display, msg, "Hotkeys disabled" if self.is_paused else "Ready to translate")

    def quit_app(self, icon, item):
        self.icon.stop(); pygame.mixer.quit(); self.root.quit(); os._exit(0)

    def request_snip(self):
        if not self.is_paused: self.snip_requested = True

    def check_queue(self):
        if self.snip_requested:
            self.snip_requested = False
            self.start_snipping()
        self.root.after(100, self.check_queue)

    def start_snipping(self):
        self.snip_win = tk.Toplevel(self.root)
        self.snip_win.attributes('-alpha', 0.3, '-fullscreen', True, '-topmost', True)
        self.snip_win.config(cursor="cross")
        canvas = tk.Canvas(self.snip_win, cursor="cross", bg="gray11")
        canvas.pack(fill="both", expand=True)
        canvas.bind("<ButtonPress-1>", self.on_button_press)
        canvas.bind("<B1-Motion>", self.on_move_press)
        canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.canvas = canvas

    def on_button_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='red', width=2)

    def on_move_press(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_button_release(self, event):
        x1, y1, x2, y2 = min(self.start_x, event.x), min(self.start_y, event.y), max(self.start_x, event.x), max(self.start_y, event.y)
        self.snip_win.destroy()
        if abs(x2 - x1) > 10: threading.Thread(target=self.process_image, args=(x1, y1, x2, y2), daemon=True).start()

    def process_image(self, x1, y1, x2, y2):
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            text = " ".join(self.reader.readtext(np.array(img), detail=0)).strip()
            if text:
                clean = re.sub(r'[_|~@^*]', '', text)
                clean = " ".join(clean.split())
                trans = self.translator.translate(clean)
                with open(self.file_path, "a", encoding="utf-8") as f: f.write(f"{clean} | {trans}\n")
                self.root.after(0, self.update_translation_display, clean, trans)
                if self.config.get("enable_speech", True):
                    threading.Thread(target=self.speak_text, args=(clean, trans), daemon=True).start()
        except: pass

    def speak_text(self, en, he):
        try:
            for t, l, f in [(en, 'en', 'en.mp3'), (he, 'iw', 'he.mp3')]:
                gTTS(text=t, lang=l).save(f)
                pygame.mixer.music.load(f)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy(): pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
        except: pass

if __name__ == "__main__":
    app = LiveTextTranslator()
    app.root.mainloop()