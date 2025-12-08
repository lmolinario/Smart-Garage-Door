# ==============================================================
# Smart Garage Door - Application Layer (Flask + MQTT)
# File: app.py
# Author: Lello Molinario, Matteo Tuzi
# Version: 1.0 - Oct 2025
# ==============================================================


'''Note rapide

Topic MQTT usati:

home/garage/cmd → comandi (da Flask al NodeMCU)

home/garage/door → stato porta (dal NodeMCU a Flask)

home/garage/gps → eventi geofence (dal NodeMCU o dal modulo GPS a Flask)

Logging: file software/server.log (rotazione automatica).

Sicurezza opzionale: se imposti API_KEY in config.json, i comandi /on, /off, /gps richiederanno l’header X-API-Key.

/events: utile per la demo e per il Cap. 5.6–5.8 (puoi mostrare uno snapshot nel report).'''


import os
import json
import time
import logging
from logging.handlers import RotatingFileHandler
from collections import deque
from threading import Lock

from flask import Flask, request, jsonify, abort
import paho.mqtt.client as mqtt

import hashlib
import time

# Utilità per hash password
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

# Dizionario utenti con password HASHATE
USERS = {
    "admin": hash_pw("admin123"),
    "lello": hash_pw("123456"),
}


# ----------------------- Config -------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE_DIR, "config.json")

# Carica config.json (fallback a env var se non presente)
if os.path.exists(CFG_PATH):
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        CFG = json.load(f)
else:
    CFG = {
        "MQTT_BROKER": os.getenv("MQTT_BROKER", "test.mosquitto.org"),
        "MQTT_PORT": int(os.getenv("MQTT_PORT", 1883)),
        "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", ""),
        "API_KEY": os.getenv("API_KEY", ""),  # opzionale
    }

MQTT_BROKER = CFG.get("MQTT_BROKER", "test.mosquitto.org")
MQTT_PORT = int(CFG.get("MQTT_PORT", 1883))
API_KEY = CFG.get("API_KEY", "")  # se impostata, serve header X-API-Key

TOPIC_CMD = "home/garage/cmd"
TOPIC_DOOR = "home/garage/door"
TOPIC_GPS = "home/garage/user_location"
TOPIC_PIR = "home/garage/pir"
TOPIC_OBSTACLE = "home/garage/obstacle"

DEVICE_ID = 123


def _as_bool(value) -> bool:
    """Utility per interpretare valori booleani provenienti da config/env."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

USERS_PATH = os.path.join(BASE_DIR, "users.json")
if os.path.exists(USERS_PATH):
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        USERS = json.load(f)
else:
    USERS = {"admin": {"password": "admin123", "role": "admin", "api_key": "ABC123"}}


# ----------------------- Logging ------------------------------

LOG_PATH = os.path.join(BASE_DIR, "server.log")

logger = logging.getLogger("garage")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3)
fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
handler.setFormatter(fmt)
logger.addHandler(handler)

# Stampa anche a console
console = logging.StreamHandler()
console.setFormatter(fmt)
logger.addHandler(console)

# ----------------------- App state ----------------------------

app = Flask(__name__)

_state_lock = Lock()
_DEFAULT_STATE = {
    "door": 0,
    "door_ts": 0.0,
    "gps_inside": False,
    "gps_ts": 0.0,
    "pir_motion": False,
    "pir_ts": 0.0,
    "obstacle_cm": None,
    "obstacle_blocked": False,
    "obstacle_ts": 0.0,
    "mqtt_connected": False,
}

_last_state = dict(_DEFAULT_STATE)

_events = deque(maxlen=200)  # piccoli eventi per /events

def _push_event(kind: str, data: dict):
    """Registra un piccolo evento nella coda condivisa ed emette un log."""
    evt = {"ts": time.time(), "kind": kind, "data": data}
    _events.appendleft(evt)
    logger.info(f"EVENT {kind}: {data}")


# ----------------------- MQTT setup ---------------------------

mqttc = mqtt.Client()

# Consente di disabilitare la connessione MQTT durante i test o in ambienti offline.
ENABLE_MQTT = _as_bool(CFG.get("ENABLE_MQTT", os.getenv("ENABLE_MQTT", "1")))

def on_connect(client, userdata, flags, rc):
    ok = rc == 0
    with _state_lock:
        _last_state["mqtt_connected"] = ok
    if ok:
        logger.info(f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(TOPIC_DOOR)
        client.subscribe(TOPIC_GPS)
        client.subscribe(TOPIC_PIR)          # ← NEW
        client.subscribe(TOPIC_OBSTACLE)     # ← NEW
    else:
        logger.error(f"MQTT connection failed rc={rc}")


def on_message(client, userdata, msg):
    payload = msg.payload.decode(errors="ignore").strip()
    topic = msg.topic

    # Prova JSON o raw
    value = None
    try:
        obj = json.loads(payload)
        value = obj.get("value", None)
    except:
        if payload.isdigit():
            value = int(payload)

    with _state_lock:

        # --------------------
        # Porta
        # --------------------
        if topic == TOPIC_DOOR and value in (0, 1):
            _last_state["door"] = value
            _last_state["door_ts"] = time.time()
            _push_event("door_update", {"value": value, "raw": payload})

        # --------------------
        # GPS
        # --------------------
        elif topic == TOPIC_GPS and value in (0, 1):
            inside = bool(value)
            _last_state["gps_inside"] = inside
            _last_state["gps_ts"] = time.time()
            _push_event("gps_update", {"inside": inside, "raw": payload})

        # --------------------
        # PIR (FR5a)
        # --------------------
        elif topic == TOPIC_PIR and value in (0, 1):
            motion = bool(value)
            _last_state["pir_motion"] = motion
            _last_state["pir_ts"] = time.time()
            _push_event("pir_update", {"motion": motion, "raw": payload})

        # --------------------
        # Ostacolo (FR8)
        # --------------------
        elif topic == TOPIC_OBSTACLE:
            dist = None
            blocked = None

            try:
                obj = json.loads(payload)
                if "distance_cm" in obj:
                    dist = float(obj["distance_cm"])
                if "blocked" in obj:
                    blocked = bool(obj["blocked"])
                if "value" in obj:
                    dist = float(obj["value"])
            except:
                # fallback tipo "23"
                try:
                    dist = float(payload)
                except:
                    pass

            if dist is not None:
                _last_state["obstacle_cm"] = dist
                if blocked is None:
                    blocked = dist < 20
                _last_state["obstacle_blocked"] = blocked
                _last_state["obstacle_ts"] = time.time()
                _push_event(
                    "obstacle_update",
                    {"distance_cm": dist, "blocked": blocked, "raw": payload}
                )

mqttc.on_connect = on_connect
mqttc.on_message = on_message

if ENABLE_MQTT:
    mqttc.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
    mqttc.loop_start()
else:
    logger.warning("MQTT disabilitato: variabile ENABLE_MQTT impostata a false")


# ------------------- Helpers & Security -----------------------

from functools import wraps
from flask import request, abort

def require_api_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if API_KEY:  # se definita
            key = request.headers.get("X-API-Key", "")
            if key != API_KEY:
                abort(401, description="Invalid API key")
        return f(*args, **kwargs)
    return wrapper



def publish_cmd(value: int):
    """
    Pubblica un comando apertura/chiusura sul topic MQTT.
    value: 1 = apri, 0 = chiudi
    """
    payload = json.dumps({"device_id": DEVICE_ID, "value": int(value)})
    mqttc.publish(TOPIC_CMD, payload, qos=0, retain=False)
    _push_event("cmd_publish", {"value": int(value)})

def authenticate_user(username, password):
    """Verifica credenziali username/password."""
    user = USERS.get(username)
    if not user:
        abort(401, description="Unknown user")
    if user["password"] != hash_pw(password):
        abort(401, description="Invalid credentials")
    return user


def require_user_or_api_key():
    """
    Autenticazione flessibile:
    - se header X-API-Key è presente → lo usa;
    - altrimenti richiede basic auth (username/password).
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        for u, v in USERS.items():
            if v.get("api_key") == api_key:
                return u
        abort(401, description="Invalid API key")

    auth = request.authorization
    if not auth:
        abort(401, description="Missing credentials")
    user = authenticate_user(auth.username, auth.password)
    return auth.username


def require_admin(user):
    """Assicura che l’utente sia admin."""
    if USERS.get(user, {}).get("role") != "admin":
        abort(403, description="Admin privilege required")


def reset_app_state():
    """Ripristina lo stato e gli eventi interni (usata nei test automatizzati)."""
    with _state_lock:
        _last_state.update(_DEFAULT_STATE)
        _events.clear()

@app.route("/listUsers", methods=["GET"])
def list_users():
    """Restituisce lista di tutti gli utenti (solo admin)."""
    user = require_user_or_api_key()
    require_admin(user)

    users_short = {name: info.get("role", "user") for name, info in USERS.items()}
    return jsonify({"status": "ok", "users": users_short})


# ------------------------- Routes -----------------------------

@app.route("/health")
def health():
    with _state_lock:
        s = dict(_last_state)
    return jsonify({"status": "ok", **s})

@app.route("/status")
def status():
    with _state_lock:
        s = dict(_last_state)
    return jsonify({
        "door": s["door"],
        "door_ts": s["door_ts"],
        "gps_inside": s["gps_inside"],
        "gps_ts": s["gps_ts"],
        "pir_motion": s["pir_motion"],
        "pir_ts": s["pir_ts"],
        "obstacle_cm": s["obstacle_cm"],
        "obstacle_blocked": s["obstacle_blocked"],
        "obstacle_ts": s["obstacle_ts"],
        "mqtt_connected": s["mqtt_connected"],
    })


@app.route("/on", methods=["GET", "POST"])
@require_api_key
def open_door():

    publish_cmd(1)
    return jsonify({"status": "sent", "cmd": "open"})

@app.route("/off", methods=["GET", "POST"])
@require_api_key
def close_door():
    publish_cmd(0)
    return jsonify({"status": "sent", "cmd": "close"})

@app.route("/gps", methods=["POST"])
@require_api_key
def gps_event():
    """
    Endpoint per ricevere aggiornamenti GPS lato server (opzionale).
    Accetta JSON: {"value": 1|0, "lat": <float>, "lon": <float>}
    Re-pubblica su MQTT per uniformità del flusso dati.
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        abort(400, description="Invalid JSON")

    val = data.get("value", None)
    if val not in (0, 1, True, False):
        abort(422, description="Field 'value' must be 0/1 or boolean")

    payload = {
        "device_id": DEVICE_ID,
        "value": int(val),
    }
    # campi opzionali
    if "lat" in data: payload["lat"] = data["lat"]
    if "lon" in data: payload["lon"] = data["lon"]

    mqttc.publish("home/garage/user_location", json.dumps(payload))

    _push_event("gps_ingest", payload)

    # aggiorna stato interno
    with _state_lock:
        _last_state["gps_inside"] = bool(val)
        _last_state["gps_ts"] = time.time()

    return jsonify({"status": "ok"})


@app.route('/')
def index():
    return "<h2>Smart Garage Door API</h2><p>Server is running correctly.</p>"

@app.route("/changePassword", methods=["POST"])
def change_password():
    """
    Cambio password:
    - admin_mode=True  → il bot come admin può cambiare la password di chiunque
                         SENZA vecchia password (ma solo se ha API_KEY valida).
    - admin_mode=False → utente normale: deve fornire old_password corretta.
    """
    data = request.get_json(force=True)

    username   = data.get("username")
    old_pw     = data.get("old_password", "")
    new_pw     = data.get("new_password", "")
    admin_mode = bool(data.get("admin_mode", False))

    if not username or not new_pw:
        abort(400, description="Missing username or new_password")

    user = USERS.get(username)
    if not user:
        abort(404, description="User not found")

    # Controllo API key (tutte le chiamate dal bot passano da qui)
    api_key = request.headers.get("X-API-Key", "")

    if admin_mode:
        # Modalità admin: solo se l'API_KEY è valida
        if API_KEY and api_key == API_KEY:
            pass  # ok, admin via bot
        else:
            abort(403, description="Admin mode not allowed without valid API key")
    else:
        # Utente normale: deve fornire la vecchia password corretta
        if not old_pw:
            abort(400, description="Missing old_password")
        if user.get("password") != hash_pw(old_pw):
            abort(401, description="Old password incorrect")

    # Aggiorna password (sempre hashata)
    user["password"] = hash_pw(new_pw)

    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(USERS, f, indent=2)

    _push_event("password_changed", {"user": username})
    return jsonify({"status": "ok"})




@app.route("/events")
def events():
    """
    Restituisce gli ultimi eventi (door_update, gps_update, cmd_publish, ...)
    """
    n = max(1, min(int(request.args.get("n", 50)), 200))
    return jsonify(list(_events)[:n])

@app.route("/getUserRole", methods=["POST"])
def get_user_role():
    data = request.get_json(force=True)
    username = data.get("username", "")

    if username not in USERS:
        return jsonify({"role": "none"})

    return jsonify({"role": USERS[username].get("role", "user")})

@app.route("/addUser", methods=["POST"])
@require_api_key
def add_user():
    user = require_user_or_api_key()
    require_admin(user)

    data = request.get_json(force=True)
    name = data.get("username")
    password = data.get("password")

    if not name or not password:
        abort(400, description="Missing username or password")

    if name in USERS:
        abort(409, description="User already exists")

    USERS[name] = {
        "password": hash_pw(password),
        "role": "user",
        "api_key": ""
    }

    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(USERS, f, indent=2)

    _push_event("user_added", {"by": user, "name": name})
    return jsonify({"status": "ok"})

@app.route("/checkUser", methods=["POST"])
def check_user():
    data = request.get_json(force=True)

    username = data.get("username", "")
    password = data.get("password", "")
    pw_hash = hash_pw(password)

    user = USERS.get(username)
    if not user:
        return jsonify({"status": "error"})

    if user.get("password") == pw_hash:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "error"})

@app.route("/delUser", methods=["POST"])
def del_user():
    user = require_user_or_api_key()
    require_admin(user)

    data = request.get_json(force=True)
    name = data.get("username")
    if not name:
        abort(400, description="Missing username")

    if name not in USERS:
        abort(404, description="User not found")

    USERS.pop(name)
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(USERS, f, indent=2)
    _push_event("user_removed", {"by": user, "name": name})
    return jsonify({"status": "ok", "message": f"User {name} removed"})

# ------------------------- Main -------------------------------

if __name__ == "__main__":
    # Avvia Flask
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = bool(int(os.getenv("FLASK_DEBUG", "0")))

    logger.info(f"Starting Flask on http://{host}:{port}")
    try:
        app.run(host=host, port=port, debug=debug)
    finally:
        if ENABLE_MQTT:
            mqttc.loop_stop()
            mqttc.disconnect()
