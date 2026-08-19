#!/usr/bin/env python3
"""ESP32 DHT22 -vastaanotin ja aikajananäyttö (Windows / Linux)."""

import calendar
import json
import math
import os
import queue
import sqlite3
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from tkinter import ttk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(APP_DIR, "mittaukset.sqlite3")
ESP32_URL = "http://192.168.4.1/data"
POLL_INTERVAL_SECONDS = 1800
MAX_POINTS = 900
SENSOR_COLORS = ("#d9485f", "#276fbf", "#20825a")


class Storage:
    # Luo tietokannan käyttöä varten lukon ja varmistaa, että taulukko ja indeksi ovat olemassa.
    def __init__(self):
        self.lock = threading.Lock()
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY,
                recorded_at TEXT NOT NULL,
                sensor INTEGER NOT NULL,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS ix_measurements_time ON measurements(recorded_at)")

    # Avaa uuden SQLite-yhteyden ohjelman omaan mittaustietokantaan.
    @staticmethod
    def connection():
        return sqlite3.connect(DATABASE_PATH, timeout=10)

    # Tallentaa ESP32:lta saadut sensorilukemat SQLite-tietokantaan aikaleiman kanssa.
    def save(self, payload):
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        rows = []
        for sensor in range(1, 4):
            values = payload.get(f"sensor{sensor}", {})
            temperature, humidity = values.get("temperature"), values.get("humidity")
            if isinstance(temperature, (int, float)) and isinstance(humidity, (int, float)):
                rows.append((timestamp, sensor, float(temperature), float(humidity)))
        if rows:
            with self.lock, self.connection() as db:
                db.executemany("INSERT INTO measurements(recorded_at,sensor,temperature,humidity) VALUES (?,?,?,?)", rows)
                print("Tallennettu", len(rows), "arvoa", timestamp)
        else:
            print("Ei kelvollisia sensorilukemia", payload)
        return len(rows), timestamp

    # Hakee tietokannasta valitun aikavälin mittaukset kuvaajia varten.
    def read_since(self, hours):
        since = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.lock, self.connection() as db:
            return db.execute(
                "SELECT recorded_at,sensor,temperature,humidity FROM measurements "
                "WHERE recorded_at >= ? ORDER BY recorded_at LIMIT ?", (since, MAX_POINTS * 3)
            ).fetchall()

    # Uusi metodi: hakee mittaukset mielivaltaiselta aikaväliltä (sisältäen päätepisteet).
    def read_between(self, start_iso, end_iso):
        with self.lock, self.connection() as db:
            return db.execute(
                "SELECT recorded_at,sensor,temperature,humidity FROM measurements "
                "WHERE recorded_at >= ? AND recorded_at <= ? "
                "ORDER BY recorded_at LIMIT ?",
                (start_iso, end_iso, MAX_POINTS * 3)
            ).fetchall()

    # Palauttaa tietokantaan tallennettujen sensoririvien kokonaismäärän.
    def count(self):
        with self.lock, self.connection() as db:
            return db.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]


class SensorChart(tk.Canvas):
    """Yhden sensorin aikajana, jossa yksittäisiä pisteitä voi tarkastella hiirellä."""

    # Luo yhden sensorin kuvaaja-alueen ja määrittää hiiren tapahtumien käsittelyn.
    def __init__(self, parent, sensor_number):
        super().__init__(parent, height=205, background="white", highlightthickness=0, cursor="crosshair")
        self.sensor_number = sensor_number
        self.color = SENSOR_COLORS[sensor_number - 1]
        self.rows = []
        self.field = "temperature"
        self.drawn_points = []
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<Motion>", self.hover)
        self.bind("<Leave>", lambda _event: self.hide_tooltip())

    # Päivittää kuvaajan datan ja valitun suureen, eli lämpötilan tai kosteuden.
    def update_data(self, rows, field):
        self.rows = [row for row in rows if row[1] == self.sensor_number]
        self.field = field
        self.draw()

    # Piirtää sensorin aikajanan, asteikon, viivan ja mittauspisteet uudelleen.
    def draw(self):
        self.delete("all")
        self.drawn_points = []
        width, height = max(350, self.winfo_width()), max(180, self.winfo_height())
        left, top, right, bottom = 58, 15, width - 18, height - 34
        self.create_rectangle(left, top, right, bottom, outline="#d8dee8")
        values = []
        for recorded_at, _sensor, temperature, humidity in self.rows:
            try:
                value = temperature if self.field == "temperature" else humidity
                values.append((datetime.fromisoformat(recorded_at).timestamp(), value, recorded_at, temperature, humidity))
            except (ValueError, TypeError):
                pass
        if not values:
            self.create_text(width / 2, height / 2, text="Ei mittauksia valitulla ajalta", fill="#7a8492")
            return

        x_min, x_max = min(point[0] for point in values), max(point[0] for point in values)
        y_min, y_max = min(point[1] for point in values), max(point[1] for point in values)
        if x_min == x_max:
            x_min -= 1800
            x_max += 1800
        padding = max((y_max - y_min) * .10, .4)
        y_min, y_max = y_min - padding, y_max + padding
        if y_min == y_max:
            y_max += 1

        for index in range(4):
            y = top + (bottom - top) * index / 3
            value = y_max - (y_max - y_min) * index / 3
            self.create_line(left, y, right, y, fill="#edf0f4")
            self.create_text(left - 7, y, text=f"{value:.1f}", anchor="e", fill="#667085", font=("Segoe UI", 8))
        for index in range(3):
            x = left + (right - left) * index / 2
            stamp = x_min + (x_max - x_min) * index / 2
            self.create_text(x, bottom + 7, text=datetime.fromtimestamp(stamp).strftime("%d.%m %H:%M"),
                             anchor="n", fill="#667085", font=("Segoe UI", 8))

        line = []
        for stamp, value, recorded_at, temperature, humidity in values:
            x = left + (stamp - x_min) / (x_max - x_min) * (right - left)
            y = bottom - (value - y_min) / (y_max - y_min) * (bottom - top)
            line.extend((x, y))
            self.drawn_points.append((x, y, recorded_at, temperature, humidity))
        if len(line) >= 4:
            self.create_line(*line, fill=self.color, width=2, smooth=False)
        for x, y, *_details in self.drawn_points:
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill="white", outline=self.color, width=2)

    # Etsii hiiren lähellä olevan mittauspisteen ja näyttää sen tarkat arvot.
    def hover(self, event):
        closest, distance = None, 10
        for point in self.drawn_points:
            current = math.hypot(event.x - point[0], event.y - point[1])
            if current < distance:
                closest, distance = point, current
        if closest is None:
            self.hide_tooltip()
            return
        _x, _y, recorded_at, temperature, humidity = closest
        try:
            time_text = datetime.fromisoformat(recorded_at).strftime("%d.%m.%Y %H:%M:%S")
        except ValueError:
            time_text = recorded_at
        text = f"{time_text}\nLämpötila: {temperature:.1f} °C\nKosteus: {humidity:.1f} %"
        self.delete("tooltip")
        x = min(event.x + 14, max(10, self.winfo_width() - 180))
        y = max(8, event.y - 56)
        label = self.create_text(x, y, text=text, anchor="nw", fill="#ffffff", font=("Segoe UI", 9), tags="tooltip")
        box = self.bbox(label)
        background = self.create_rectangle(box[0] - 7, box[1] - 5, box[2] + 7, box[3] + 5,
                                           fill="#1f2937", outline="", tags="tooltip")
        self.tag_lower(background, label)

    # Poistaa mittauspisteen päälle näytettävän työkaluvihjeen.
    def hide_tooltip(self):
        self.delete("tooltip")


class App(tk.Tk):
    # Luo pääikkunan, tietokannan, käyttöliittymän, kuvaajat ja automaattisen tiedonhaun.
    def __init__(self):
        super().__init__()
        self.title("ESP32 DHT22 Monitor")
        self.geometry("1000x820")
        self.minsize(760, 650)
        self.storage, self.events = Storage(), queue.Queue()
        self.status = tk.StringVar()
        self.hours = tk.StringVar(value="24h")
        self.field = tk.StringVar(value="temperature")
        # Uudet muuttujat kuukauden valintaa varten
        self.month_var = tk.StringVar(value="Tammikuu")
        self.year_var = tk.StringVar(value=str(datetime.now().year))
        self.charts = []
        self.time_range_hours = {"6h": 6, "24h": 24, "1 week": 168, "1 month": 720}
        self.configure_style()
        self.build()
        self.start_polling()
        self.refresh()
        self.after(400, self.process_events)

    # Määrittää käyttöliittymän värit, fontit, painikkeet ja muut tyylit.
    def configure_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        self.configure(background="#f4f6f9")
        style.configure("App.TFrame", background="#f4f6f9")
        style.configure("Card.TFrame", background="white")
        style.configure("Title.TLabel", background="#f4f6f9", foreground="#172033", font=("Segoe UI", 18, "bold"))
        style.configure("Subtle.TLabel", background="#f4f6f9", foreground="#667085", font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", background="white", foreground="#172033", font=("Segoe UI", 11, "bold"))
        style.configure("CardInfo.TLabel", background="white", foreground="#667085", font=("Segoe UI", 9))
        style.configure("TButton", padding=(10, 5))

    # Rakentaa käyttöliittymän, painikkeet, sensorikortit ja kuvaajat.
    def build(self):
        root = ttk.Frame(self, padding=16, style="App.TFrame")
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="ESP32 DHT22 Monitor", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, textvariable=self.status, style="Subtle.TLabel").pack(anchor="w", pady=(2, 12))

        # ---------- Olemassa olevat pika‑aikavälivalinnat ----------
        controls = ttk.Frame(root, style="App.TFrame")
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="Aikaväli", style="Subtle.TLabel").pack(side="left")
        chooser = ttk.Combobox(controls, values=("6h", "24h", "1 week", "1 month"), width=10, textvariable=self.hours, state="readonly")
        chooser.pack(side="left", padx=6)
        chooser.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Radiobutton(controls, text="Lämpötila", variable=self.field, value="temperature", command=self.refresh).pack(side="left", padx=(20, 8))
        ttk.Radiobutton(controls, text="Kosteus", variable=self.field, value="humidity", command=self.refresh).pack(side="left")
        ttk.Button(controls, text="Hae ESP32:lta heti", command=self.fetch_now).pack(side="right", padx=(6, 0))
        ttk.Button(controls, text="Päivitä näkymä", command=self.refresh).pack(side="right")

        # ---------- Uusi kuukausivalintarivi ----------
        month_frame = ttk.Frame(root, style="App.TFrame")
        month_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(month_frame, text="Kuukausi", style="Subtle.TLabel").pack(side="left")
        month_choices = ["Tammikuu", "Helmikuu", "Maaliskuu", "Huhtikuu",
                         "Toukokuu", "Kesäkuu", "Heinäkuu", "Elokuu",
                         "Syyskuu", "Lokakuu", "Marraskuu", "Joulukuu"]
        month_combo = ttk.Combobox(month_frame, values=month_choices,
                                   textvariable=self.month_var, width=10, state="readonly")
        month_combo.pack(side="left", padx=(6, 4))

        ttk.Label(month_frame, text="Vuosi", style="Subtle.TLabel").pack(side="left")
        current_year = datetime.now().year
        year_choices = [str(y) for y in range(current_year - 5, current_year + 1)]
        year_combo = ttk.Combobox(month_frame, values=year_choices,
                                  textvariable=self.year_var, width=6, state="readonly")
        year_combo.pack(side="left", padx=(6, 4))

        ttk.Button(month_frame, text="Näytä kuukausi", command=self.show_month).pack(side="left", padx=(8, 0))
        ttk.Button(month_frame, text="Nollaa aikaikkuna", command=self.reset_to_quick_range).pack(side="left", padx=(8, 0))

        # ---------- Sensorikortit ----------
        for sensor in range(1, 4):
            card = ttk.Frame(root, padding=12, style="Card.TFrame")
            card.pack(fill="both", expand=True, pady=(0, 10))
            header = ttk.Frame(card, style="Card.TFrame")
            header.pack(fill="x")
            ttk.Label(header, text=f"Sensori {sensor}", style="CardTitle.TLabel").pack(side="left")
            ttk.Label(header, text="Siirrä hiiri mittauspisteen päälle nähdäksesi arvot", style="CardInfo.TLabel").pack(side="right")
            chart = SensorChart(card, sensor)
            chart.pack(fill="both", expand=True, pady=(7, 0))
            self.charts.append(chart)

        ttk.Label(root, text=f"Hakee ESP32:n dataa osoitteesta {ESP32_URL}", style="Subtle.TLabel").pack(anchor="w", pady=(0, 2))

    # Käynnistää taustasäikeen, joka hakee ESP32:lta dataa automaattisesti 30 minuutin välein.
    def start_polling(self):
        threading.Thread(target=self.poll_loop, daemon=True).start()
        self.status.set(f"Aloitetaan ESP32:n tietojen hakua  •  Tallennettuja arvoja: {self.storage.count()}")

    # Käynnistää välittömän ESP32-haun taustasäikeessä, jotta käyttöliittymä pysyy reagoivana.
    def fetch_now(self):
        threading.Thread(target=self.fetch_data, daemon=True).start()

    # Hakee JSON-datan ESP32:lta, käsittelee vastauksen ja tallentaa kelvolliset arvot tietokantaan.
    def fetch_data(self):
        try:
            with urllib.request.urlopen(ESP32_URL, timeout=10) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body)
                count, timestamp = self.storage.save(payload)
                if count > 0:
                    self.events.put(("data", count, timestamp))
                else:
                    self.events.put(("info", "ESP32 palautti dataa, mutta sensorilukemat eivät olleet kelvollisia"))
        except urllib.error.HTTPError as error:
            try:
                body = error.read().decode("utf-8", errors="ignore")
                payload = json.loads(body)
            except Exception:
                payload = {}
            if error.code == 404 and payload.get("error") in ("no data", "no data available", "not found"):
                self.events.put(("info", "ESP32 ei ole vielä tuottanut mittausta"))
            else:
                self.events.put(("network", f"HTTP {error.code} - {payload.get('error', error.reason)}"))
        except urllib.error.URLError as error:
            self.events.put(("network", f"Yhteysvirhe: {error.reason}"))
        except (ValueError, json.JSONDecodeError) as error:
            self.events.put(("network", f"JSON-virhe: {error}"))
        except Exception as error:
            self.events.put(("network", str(error)))

    # Suorittaa automaattisen haun ja odottaa seuraavaan 30 minuutin hakuun.
    def poll_loop(self):
        while True:
            self.fetch_data()
            time.sleep(POLL_INTERVAL_SECONDS)

    # Lukee valitun aikavälin mittaukset ja päivittää kaikki kolme kuvaajaa.
    def refresh(self):
        hours = self.time_range_hours.get(self.hours.get(), 24)
        rows = self.storage.read_since(hours)
        for chart in self.charts:
            chart.update_data(rows, self.field.get())

    # Uusi metodi: näyttää valitun kuukauden kaikki mittaukset.
    def show_month(self):
        month_name = self.month_var.get()
        year_str = self.year_var.get()
        if not month_name or not year_str:
            return
        try:
            year = int(year_str)
        except ValueError:
            return

        month_map = {
            "Tammikuu": 1, "Helmikuu": 2, "Maaliskuu": 3, "Huhtikuu": 4,
            "Toukokuu": 5, "Kesäkuu": 6, "Heinäkuu": 7, "Elokuu": 8,
            "Syyskuu": 9, "Lokakuu": 10, "Marraskuu": 11, "Joulukuu": 12
        }
        month = month_map.get(month_name)
        if not month:
            return

        first_day = datetime(year, month, 1)
        last_day = datetime(year, month, calendar.monthrange(year, month)[1],
                            23, 59, 59)

        start_iso = first_day.astimezone().isoformat(timespec="seconds")
        end_iso = last_day.astimezone().isoformat(timespec="seconds")

        rows = self.storage.read_between(start_iso, end_iso)
        for chart in self.charts:
            chart.update_data(rows, self.field.get())

        self.status.set(
            f"Näytetään {month_name} {year}  •  Mittauksia: {len(rows)} "
            f"(viimeisin {rows[-1][0] if rows else 'ei dataa'})"
        )

    # Uusi metodi: palauttaa näkymän pika‑aikaväliin (oletuksena 24h).
    def reset_to_quick_range(self):
        self.hours.set("24h")
        self.refresh()

    # Käsittelee taustasäikeiden ilmoitukset turvallisesti Tkinter-käyttöliittymässä.
    def process_events(self):
        changed = False
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == "data":
                self.status.set(f"Vastaanotettu {event[1]} arvoa  •  {event[2]}")
                changed = True
            elif event[0] == "network":
                self.status.set(event[1])
            elif event[0] == "info":
                self.status.set(event[1])
            else:
                self.status.set("Virhe: " + event[1])
        if changed:
            self.refresh()
        self.after(400, self.process_events)

    # Sulkee tarvittavat resurssit ja päättää käyttöliittymän hallitusti.
    def destroy(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
        super().destroy()


if __name__ == "__main__":
    App().mainloop()