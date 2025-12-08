# ==============================================================
# Smart Garage Door - Periodic Monitor
# File: timer.py
# Author: Lello Molinario, Matteo Tuzi
# Version: 1.0 - Oct 2025
# ==============================================================
# Descrizione:
# Esegue richieste periodiche al server Flask per:
#   - Verificare lo stato del sistema (/health e /status)
#   - Registrare i risultati su log
#   - (Facoltativo) Inviare notifiche Telegram in caso di errore
#
# Può essere eseguito come processo separato o schedulato (cron/systemd)
# ==============================================================
'''Funzionalità principali
Funzione	Descrizione
get_status()	Chiama il server Flask e restituisce lo stato JSON.
send_telegram()	Invia messaggi al tuo account Telegram in caso di errore (opzionale).
main()	Ciclo continuo: registra stato e latenza in timer.log.
INTERVAL	Frequenza di controllo (predefinita 60 s, configurabile da config.json).'''

import os
import json
import time
import logging
import requests
from datetime import datetime

# ----------------------- Config -------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE_DIR, "config.json")

if os.path.exists(CFG_PATH):
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        CFG = json.load(f)
else:
    CFG = {}

APP_URL = CFG.get("FLASK_URL", "http://127.0.0.1:5000")
API_KEY = CFG.get("API_KEY", "")
BOT_TOKEN = CFG.get("TELEGRAM_TOKEN", "")
CHAT_ID = CFG.get("ADMIN_CHAT_ID", "")  # opzionale, se vuoi ricevere alert via Telegram

INTERVAL = int(CFG.get("TIMER_INTERVAL", 60))  # secondi tra controlli

# ----------------------- Logging ------------------------------

LOG_PATH = os.path.join(BASE_DIR, "timer.log")
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("timer")

# ----------------------- Helper HTTP --------------------------

def get_status():
    """Effettua una chiamata /status al server Flask."""
    try:
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        resp = requests.get(f"{APP_URL}/status", headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def send_telegram(msg: str):
    """Invia un messaggio Telegram (opzionale)."""
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": msg}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.warning(f"Errore invio Telegram: {e}")

# ----------------------- Main loop ----------------------------

def main():
    logger.info("Timer monitor avviato.")
    print("Timer monitor attivo. Intervallo:", INTERVAL, "s")

    while True:
        start = time.time()
        result = get_status()

        if "error" in result:
            msg = f"Errore nel contattare il server: {result['error']}"
            logger.error(msg)
            send_telegram(f"Smart Garage Door ALERT:\n{msg}")
        else:
            door = "APERTA" if result.get("door") else "CHIUSA"
            mqtt_ok = result.get("mqtt_connected", False)
            gps_in = result.get("gps_inside", False)
            latency = time.time() - start
            msg = (
                f"Porta {door}, MQTT {'OK' if mqtt_ok else 'DOWN'}, "
                f"GPS {'INSIDE' if gps_in else 'OUT'}, "
                f"latency={latency:.2f}s"
            )
            logger.info(msg)
            print(datetime.now().strftime("%H:%M:%S"), "-", msg)

        time.sleep(INTERVAL)

# ----------------------- Run ---------------------------------

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTimer monitor interrotto manualmente.")
        logger.info("Timer monitor terminato manualmente.")
