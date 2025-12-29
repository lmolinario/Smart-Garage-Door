# ==============================================================
# Smart Garage Door - Telegram Bot Interface
# File: telegram_listener.py
# Author: Lello Molinario, Matteo Tuzi
# Version: 1.0 - Oct 2025
# ==============================================================
# Descrizione:
# Bot Telegram che interagisce con il server Flask del progetto
# Smart Garage Door. Consente all'utente di:
#   - Aprire / Chiudere la porta
#   - Consultare lo stato in tempo reale
#   - Visualizzare eventi recenti (door/gps)
#   - Eseguire autenticazione opzionale
#
# Requisiti:
#   - Python 3.11+
#   - python-telegram-bot 20+
#   - Server Flask attivo (app.py)
# ==============================================================
'''Spiegazione
Funzione	Descrizione
/on, /off	Inviano richieste HTTP a Flask (/on, /off) → Flask → MQTT → NodeMCU → Arduino.
/status	Mostra stato porta, GPS e connessione MQTT.
/events	Mostra ultimi eventi registrati da Flask (door_update, gps_update, cmd_publish).
/help, /start	Mostrano comandi e istruzioni base.
periodic_status()	Ogni 60s invia aggiornamento automatico (puoi disattivarlo).
Sicurezza

Se nel config.json hai impostato "API_KEY": "12345", il bot invierà automaticamente l’header X-API-Key a Flask.

Tutte le richieste vengono fatte su APP_URL (default http://127.0.0.1:5000).'''
import time
import os
import json
import requests
import logging
import asyncio
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
)

# ----------------------- Configurazione -----------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE_DIR, "config.json")

if os.path.exists(CFG_PATH):
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        CFG = json.load(f)
else:
    CFG = {}

API_KEY = CFG.get("API_KEY", "")
BOT_TOKEN = CFG.get("TELEGRAM_TOKEN", "")
APP_URL = CFG.get("FLASK_URL", "http://127.0.0.1:5000")

AUDIT_FILE = "audit.log"

def audit(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(AUDIT_FILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")

# ----------------------- Sessioni Admin (in RAM) -----------------------

# Contiene gli ID Telegram degli admin attualmente loggati
# Admin sessions: { telegram_id: expiry_timestamp }
ADMIN_SESSIONS = {}

SESSION_LIFETIME = 1800  # 30 minuti

# Sessioni utente normale (non scadono finché non fa logout)
USER_SESSIONS = set()

def is_logged_admin(update: Update) -> bool:
    uid = update.effective_user.id
    now = time.time()

    if uid in ADMIN_SESSIONS:
        if ADMIN_SESSIONS[uid] > now:
            return True
        else:
            # sessione scaduta → rimuovi
            del ADMIN_SESSIONS[uid]
            return False
    return False

def is_logged_user(update: Update) -> bool:
    """True se utente normale è loggato (o admin)."""
    uid = update.effective_user.id
    if uid in USER_SESSIONS:
        return True
    return is_logged_admin(update)


async def require_user_login(update: Update) -> bool:
    """
    Blocca l'accesso ai comandi se non loggato.
    Restituisce True se l'utente può continuare.
    """
    if not (is_logged_user(update) or is_logged_admin(update)):
        await update.message.reply_text("Devi essere autenticato. Usa /login.")
        return False
    return True

# ----------------------- Geofence (placeholder) -----------------------

# Centro geofence (es. casa tua)
HOME_LAT = CFG.get("HOME_LAT", 40.795503)   # esempio Sassari
HOME_LON = CFG.get("HOME_LON", 8.574867)

# Raggio geofence in metri (es. 300m)
GEOFENCE_RADIUS_M = float(CFG.get("GEOFENCE_RADIUS_M", 300.0))


def _haversine_m(lat1, lon1, lat2, lon2):
    """Distanza approssimata in metri tra due coordinate."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371000.0  # raggio Terra in metri
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = atan2(sqrt(a), sqrt(1 - a)) * 2
    return R * c


def _is_inside_geofence(lat, lon):
    """True se (lat,lon) è all'interno del geofence definito."""
    d = _haversine_m(HOME_LAT, HOME_LON, lat, lon)
    return d <= GEOFENCE_RADIUS_M, d


# ----------------------- Logging ------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler()  # Assicura che i log vadano anche a console
    ]
)
logger = logging.getLogger("telegram-bot")

# ----------------------- Helper HTTP --------------------------


async def login_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Uso: /login <username> <password>")
        return

    username, password = context.args
    res = _post("/checkUser", {"username": username, "password": password})

    if res.get("status") != "ok":
        await update.message.reply_text("Credenziali non valide.")
        return

    uid = update.effective_user.id

    # richiede info ruolo utente
    role_info = _post("/getUserRole", {"username": username})
    role = role_info.get("role", "user")

    if role == "admin":
        expiry = time.time() + SESSION_LIFETIME
        ADMIN_SESSIONS[uid] = expiry
        await update.message.reply_text(
            f"Login admin effettuato come *{username}*\n"
            f"Sessione valida per {SESSION_LIFETIME//60} minuti.",
            parse_mode="Markdown"
        )
    else:
        USER_SESSIONS.add(uid)
        await update.message.reply_text(
            f"Login utente effettuato come *{username}*\n"
            f"Rimarrai autenticato finché non usi /logout.",
            parse_mode="Markdown"
        )


async def logout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Logout admin
    if uid in ADMIN_SESSIONS:
        del ADMIN_SESSIONS[uid]
        await update.message.reply_text("Logout admin effettuato.")
        return

    # Logout utente
    if uid in USER_SESSIONS:
        USER_SESSIONS.remove(uid)
        await update.message.reply_text("Logout utente effettuato.")
        return

    await update.message.reply_text("Non risulti loggato.")

def _get(path: str):
    try:
        headers = {"X-API-Key": API_KEY}
        resp = requests.get(APP_URL + path, headers=headers, timeout=5)

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}

        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _post(path: str, data=None):
    try:
        headers = {"X-API-Key": API_KEY}
        resp = requests.post(APP_URL + path, json=data or {}, headers=headers, timeout=5)

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}

        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ----------------------- Command Handlers ---------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "<b>Benvenuto nel sistema Smart Garage Door!</b>\n"
        "Questo bot ti permette di controllare e monitorare il prototipo IoT.\n\n"

        "<b>Autenticazione</b>\n"
        "• /login &lt;user&gt; &lt;pass&gt; - Effettua login\n"
        "• /changepass - Cambia password (utente o admin)\n"
        "• /logout - Chiudi la sessione\n\n"

        "<b>Comandi principali</b>\n"
        "• /on - Apri la porta\n"
        "• /off - Chiudi la porta\n"
        "• /status - Stato attuale del sistema\n\n"
        
        "<b>Sensori</b>\n"
        "• /pir - Stato sensore PIR (uscita)\n"
        "• /obstacle - Stato sensore ostacolo HC-SR04\n\n"

        "<b>Funzioni amministrative</b>\n\n"
        "      <b>Gestione utenti (admin)</b>\n"
        "       • /listusers - Visualizza gli utenti attivi\n"
        "       • /adduser &lt;user&gt; &lt;pass&gt; - Aggiungi utente\n"
        "       • /deluser &lt;user&gt; - Rimuovi utente\n\n"
        "      <b>Localizzazione e prossimità</b>\n"
        "       • /gps &lt;lat&gt; &lt;lon&gt; - Invia posizione manuale\n\n"
        "      <b>Funzioni amministrative</b>\n"
        "       • /adminstatus - Cruscotto diagnostico\n\n"

        "<b>Aiuto</b>\n"
        "• /help - Mostra questa lista\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")



async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_user_login(update): return
    res = _post("/on")
    if "error" in res:
        await update.message.reply_text(f"Errore apertura: {res['error']}")
    else:
        await update.message.reply_text("Porta in apertura...")

async def off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_user_login(update): return
    res = _post("/off")
    if "error" in res:
        await update.message.reply_text(f"Errore chiusura: {res['error']}")
    else:
        await update.message.reply_text("Porta in chiusura...")


async def changepass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # ===== ADMIN: cambia password a QUALSIASI utente =====
    if is_logged_admin(update):
        if len(context.args) != 2:
            await update.message.reply_text("Uso admin: /changepass <username> <newpass>")
            return

        username, newpass = context.args
        res = _post("/changePassword", {
            "username": username,
            "new_password": newpass,
            "admin_mode": True
        })

        if "error" in res:
            await update.message.reply_text(f"Errore cambio password admin: {res['error']}")
        else:
            await update.message.reply_text(
                f"Password aggiornata (admin) per *{username}*",
                parse_mode="Markdown"
            )
        return

    # ===== UTENTE NORMALE: può cambiare SOLO la sua password =====
    if not await require_user_login(update):
        return

    if len(context.args) != 2:
        await update.message.reply_text("Uso utente: /changepass <oldpass> <newpass>")
        return

    oldpass, newpass = context.args

    # Chiediamo lo username, perché Telegram NON lo conosce
    await update.message.reply_text("Per favore inserisci il tuo username:")
    context.user_data["pending_pwchange"] = (oldpass, newpass)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_pwchange" in context.user_data:
        username = update.message.text.strip()
        oldpass, newpass = context.user_data.pop("pending_pwchange")

        res = _post("/changePassword", {
            "username": username,
            "old_password": oldpass,
            "new_password": newpass,
            "admin_mode": False
        })

        if "error" in res:
            await update.message.reply_text(f"Errore cambio password: {res['error']}")
        else:
            await update.message.reply_text("Password aggiornata con successo!")
        return


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_user_login(update): return
    res = _get("/status")
    if "error" in res:
        await update.message.reply_text(f"Errore stato: {res['error']}")
        return

    door = "APERTA" if res.get("door") else "CHIUSA"
    gps = "NEL GEOFENCE" if res.get("gps_inside") else "FUORI AREA"
    msg = (
        f"*Stato attuale:*\n"
        f"• Porta: {door}\n"
        f"• Posizione GPS: {gps}\n"
        f"• Connessione MQTT: {'OK' if res.get('mqtt_connected') else 'OFF'}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")



# ----------------------- Gestione utenti ----------------------

async def list_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra tutti gli utenti registrati (solo admin)."""
    if not is_logged_admin(update):
        await update.message.reply_text("Solo admin possono usare questo comando.")
        return

    res = _get("/listUsers")
    if "error" in res:
        await update.message.reply_text(f"Errore: {res['error']}")
        return

    users = res.get("users", {})
    if not users:
        await update.message.reply_text("Nessun utente registrato.")
        return

    msg_lines = ["*Utenti registrati:*"]
    for uname, role in users.items():
        icon = "*" if role == "admin" else "•"
        msg_lines.append(f"{icon} {uname} – {role}")

    await update.message.reply_text("\n".join(msg_lines), parse_mode="Markdown")


async def add_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Aggiunge un nuovo utente (solo admin).
    Uso: /adduser <username> <password>
    """
    if not is_logged_admin(update):
        await update.message.reply_text("Devi essere admin. Usa /login prima.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Uso corretto: /adduser <username> <password>")
        return

    username, password = context.args
    res = _post("/addUser", {"username": username, "password": password})

    if "error" in res:
        await update.message.reply_text(f"Errore: {res['error']}")
    elif res.get("status") == "ok":
        await update.message.reply_text(f"Utente *{username}* aggiunto con successo!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Risposta: {res}")


async def del_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Rimuove un utente (solo admin).
    Uso: /deluser <username>
    """
    if not is_logged_admin(update):
        await update.message.reply_text("Comando riservato agli admin. Usa /login.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Uso corretto: /deluser <username>")
        return

    username = context.args[0]
    res = _post("/delUser", {"username": username})

    if "error" in res:
        await update.message.reply_text(f"Errore: {res['error']}")
    elif res.get("status") == "ok":
        await update.message.reply_text(f"Utente *{username}* rimosso con successo!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Risposta: {res}")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comando non riconosciuto. Digita /help per la lista comandi.")

# ----------------------- Notifiche periodiche -----------------

async def periodic_status(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 60s controlla lo stato e notifica eventuali cambiamenti."""
    res = _get("/status")
    if "error" in res:
        return
    door_state = "aperta" if res.get("door") else "chiusa"
    gps_inside = "dentro area" if res.get("gps_inside") else "fuori area"
    msg = f"Aggiornamento automatico:\nPorta {door_state}, veicolo {gps_inside}."
    try:
        await context.bot.send_message(chat_id=context.job.chat_id, text=msg)
    except Exception as e:
        logger.warning(f"Errore invio notifica: {e}")


async def gps_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando manuale: /gps <lat> <lon>
    - Calcola se sei dentro/fuori geofence
    - Invia a Flask: value=1 (dentro) / 0 (fuori) + lat/lon
    """
    if not is_logged_admin(update):
        await update.message.reply_text("Solo admin possono usare questo comando.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Uso corretto: /gps <lat> <lon>")
        return

    try:
        lat = float(context.args[0])
        lon = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Coordinate non valide.")
        return

    inside, dist = _is_inside_geofence(lat, lon)
    val = 1 if inside else 0

    payload = {"value": val, "lat": lat, "lon": lon}
    res = _post("/gps", payload)

    if "error" in res:
        await update.message.reply_text(f"Errore invio GPS: {res['error']}")
        return

    stato = "DENTRO il geofence" if inside else "FUORI dal geofence"
    await update.message.reply_text(
        f"Posizione inviata:\n"
        f"Lat={lat:.6f}\nLon={lon:.6f}\n"
        f"Distanza da casa ≈ {dist:.1f} m\n"
        f"Stato: {stato}"
    )


async def gps_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """L’utente invia la posizione con il pulsante Telegram."""

    # Utente non loggato → esci
    if not await require_user_login(update):
        return

    # --- FIX ROBUSTO ----
    msg = update.message
    if msg is None:
        logger.warning("gps_location: update.message è None")
        return

    if msg.location is None:
        logger.warning("gps_location: location mancante")
        return
    # ---------------------

    lat = msg.location.latitude
    lon = msg.location.longitude

    inside, dist = _is_inside_geofence(lat, lon)
    val = 1 if inside else 0

    payload = {"value": val, "lat": lat, "lon": lon}
    res = _post("/gps", payload)

    if "error" in res:
        await msg.reply_text(f"Errore invio GPS: {res['error']}")
        return

    stato = "DENTRO il geofence" if inside else "FUORI dal geofence"
    await msg.reply_text(
        f"Posizione ricevuta:\n"
        f"Lat={lat:.6f}\nLon={lon:.6f}\n"
        f"Distanza da casa ≈ {dist:.1f} m\n"
        f"Stato: {stato}"
    )


async def gps_live_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    edited = update.edited_message

    if edited is None or edited.location is None:
        logger.warning("gps_live_location: nessuna location nella live update")
        return

    lat = edited.location.latitude
    lon = edited.location.longitude

    inside, dist = _is_inside_geofence(lat, lon)
    val = 1 if inside else 0

    payload = {"value": val, "lat": lat, "lon": lon}
    res = _post("/gps", payload)

    stato = "DENTRO IL GEOFENCE" if inside else "FUORI DAL GEOFENCE"

    await edited.reply_text(
        f"[LIVE] Posizione aggiornata:\n"
        f"Lat: {lat:.6f}\n"
        f"Lon: {lon:.6f}\n"
        f"Distanza ≈ {dist:.1f} m\n"
        f"Stato: {stato}"
    )


async def pir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_user_login(update):
        return

    res = _get("/status")
    if "error" in res:
        await update.message.reply_text(f"Errore lettura stato PIR: {res['error']}")
        return

    motion = res.get("pir_motion", False)
    ts = res.get("pir_ts", 0)
    ts_fmt = datetime.fromtimestamp(ts).strftime("%H:%M:%S")

    stato = "Movimento rilevato" if motion else "Nessun movimento rilevato"

    msg = (
        f"*Stato PIR (aggiornato):*\n"
        f"• {stato}\n"
        f"• Ultimo aggiornamento: {ts_fmt}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def obstacle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_user_login(update):
        return

    res = _get("/status")
    if "error" in res:
        await update.message.reply_text(f"Errore lettura stato ostacolo: {res['error']}")
        return

    dist = res.get("obstacle_cm", None)
    blocked = res.get("obstacle_blocked", None)
    ts = res.get("obstacle_ts", 0)
    ts_fmt = datetime.fromtimestamp(ts).strftime("%H:%M:%S")

    desc = (
        "Distanza non disponibile."
        if dist is None else
        f"Distanza ostacolo: {dist:.1f} cm"
    )

    if blocked is True:
        stato = "Apertura BLOCCATA per ostacolo."
    elif blocked is False:
        stato = "Nessun ostacolo critico rilevato."
    else:
        stato = "Stato blocco non specificato."

    msg = (
        f"*Sensore Ostacolo (aggiornato):*\n"
        f"• {desc}\n"
        f"• {stato}\n"
        f"• Ultimo aggiornamento: {ts_fmt}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def adminstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Piccolo cruscotto diagnostico:
    - stato porta
    - GPS
    - MQTT
    - ultimi eventi (compatti)
    Utile per demo al professore e capitolo validazione.
    """
    if not is_logged_admin(update):
        await update.message.reply_text("Solo admin. Usa /login.")
        return
    status = _get("/status")
    events = _get("/events?n=5")

    if "error" in status:
        await update.message.reply_text(f"Errore stato: {status['error']}")
        return
    if isinstance(events, dict) and "error" in events:
        await update.message.reply_text(f"Errore eventi: {events['error']}")
        return

    door = "APERTA" if status.get("door") else "CHIUSA"
    gps = "NEL GEOFENCE" if status.get("gps_inside") else "FUORI AREA"
    mqtt = "OK" if status.get("mqtt_connected") else "OFF"

    lines = [
        "*Admin Status:*\n",
        f"• Porta: {door}",
        f"• GPS: {gps}",
        f"• MQTT: {mqtt}",
        "",
        "*Ultimi eventi:*",
    ]

    if events:
        for evt in events:
            ts = datetime.fromtimestamp(evt["ts"]).strftime("%H:%M:%S")
            kind = evt["kind"].replace("_", " ")
            data = evt["data"]
            lines.append(f"• [{ts}] {kind}: {data}")
    else:
        lines.append("Nessun evento disponibile.")

    await update.message.reply_text("\n".join(lines))


# ----------------------- Main Setup ---------------------------

def start_bot():
    """
    Avvia il bot Telegram. 
    Può essere chiamata da app.py per avviare il bot in un thread separato.
    """
    print("[Telegram Bot] start_bot() chiamata")
    logger.info("start_bot() chiamata")
    
    if not BOT_TOKEN:
        error_msg = "ERRORE: manca TELEGRAM_TOKEN in config.json"
        print(f"[Telegram Bot] {error_msg}")
        logger.error(error_msg)
        return

    print(f"[Telegram Bot] Token trovato, creo Application...")
    logger.info("Creazione Application Telegram bot...")
    
    try:
        bot_app = Application.builder().token(BOT_TOKEN).build()
    except Exception as e:
        error_msg = f"Errore nella creazione Application: {e}"
        print(f"[Telegram Bot] {error_msg}")
        logger.error(error_msg, exc_info=True)
        return

    # Comandi principali
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_cmd))

    bot_app.add_handler(CommandHandler("login", login_cmd))
    bot_app.add_handler(CommandHandler("logout", logout_cmd))

    bot_app.add_handler(CommandHandler("on", on_cmd))
    bot_app.add_handler(CommandHandler("off", off_cmd))
    bot_app.add_handler(CommandHandler("status", status_cmd))

    # Gestione utenti
    bot_app.add_handler(CommandHandler("adduser", add_user_cmd))
    bot_app.add_handler(CommandHandler("deluser", del_user_cmd))
    bot_app.add_handler(CommandHandler("listusers", list_users_cmd))
    bot_app.add_handler(CommandHandler("changepass", changepass_cmd))

    # GPS manuale
    bot_app.add_handler(CommandHandler("gps", gps_cmd))

    # LIVE LOCATION (edited_message)
    bot_app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, gps_live_location))

    # Sensori
    bot_app.add_handler(CommandHandler("pir", pir_cmd))
    bot_app.add_handler(CommandHandler("obstacle", obstacle_cmd))
    bot_app.add_handler(CommandHandler("adminstatus", adminstatus_cmd))

    # Testo normale
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # LOCATION singola
    bot_app.add_handler(MessageHandler(filters.LOCATION, gps_location))

    # Comandi sconosciuti
    bot_app.add_handler(MessageHandler(filters.COMMAND, unknown))

    print("[Telegram Bot] Avvio polling...")
    logger.info("Telegram bot avviato, avvio polling...")
    try:
        # Crea un nuovo event loop per questo thread (necessario quando si esegue in un thread separato)
        # In Python 3.10+, get_event_loop() fallisce se non c'è un loop, quindi dobbiamo crearne uno
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot_app.run_polling()
    except Exception as e:
        error_msg = f"Errore durante il polling del bot: {e}"
        print(f"[Telegram Bot] {error_msg}")
        logger.error(error_msg, exc_info=True)
        raise

def main():
    """Funzione main per compatibilità quando si esegue telegram_listener.py direttamente."""
    start_bot()

if __name__ == "__main__":
    main()
