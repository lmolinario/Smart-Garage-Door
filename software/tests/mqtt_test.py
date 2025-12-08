#!/usr/bin/env python3
"""
MQTT Test Utility for Smart Garage Door
---------------------------------------
Simula il comportamento del NodeMCU pubblicando messaggi MQTT
verso il broker e monitora tutte le risposte, salvandole in un file di log.
"""

import time
import json
import random
import logging
import paho.mqtt.client as mqtt
from datetime import datetime

# ===================== CONFIGURAZIONE =====================
BROKER = "test.mosquitto.org"
PORT = 1883
TOPIC_CMD = "home/garage/cmd"
TOPIC_GPS = "home/garage/gps"
TOPIC_DOOR = "home/garage/door"
TOPIC_ALL = "home/garage/#"

DEVICE_ID = 123456
CLIENT_ID = f"mqtt_tester_{random.randint(0, 9999)}"

LOG_FILE = f"mqtt_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ===================== LOGGER =============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("mqtt_test")

# ===========================================================

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connesso al broker MQTT {BROKER}:{PORT}")
        client.subscribe(TOPIC_ALL)
        logger.info(f"Sottoscritto al topic wildcard: {TOPIC_ALL}")
    else:
        logger.error(f"Connessione fallita con codice {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        logger.info(f"[RX] Topic: {msg.topic} | Payload: {payload}")
    except Exception as e:
        logger.error(f"Impossibile decodificare messaggio: {e}")

def publish_cmd(client, value: int):
    """Simula la pressione del pulsante remoto (ON/OFF)."""
    message = json.dumps({"device_id": DEVICE_ID, "value": value})
    client.publish(TOPIC_CMD, message)
    logger.info(f"[TX] Comando pubblicato su {TOPIC_CMD}: {message}")

def publish_gps(client, inside: bool):
    """Simula l’ingresso/uscita dal geofence GPS."""
    value = 1 if inside else 0
    message = json.dumps({"device_id": DEVICE_ID, "value": value})
    client.publish(TOPIC_GPS, message)
    logger.info(f"[TX] Stato GPS pubblicato su {TOPIC_GPS}: {message}")

# ===========================================================

if __name__ == "__main__":
    client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv311)
    client.on_connect = on_connect
    client.on_message = on_message

    logger.info("Avvio simulatore MQTT...")
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    try:
        while True:
            print("\n[MENU] Seleziona un test:")
            print("1.  Apri porta (cmd=1)")
            print("2.  Chiudi porta (cmd=0)")
            print("3.  Simula ingresso (GPS → dentro geofence)")
            print("4.  Simula uscita (GPS → fuori geofence)")
            print("5.  Ascolta solo (logging continuo)")
            print("6.  Esci\n")

            choice = input("Scelta: ").strip()
            if choice == "1":
                publish_cmd(client, 1)
            elif choice == "2":
                publish_cmd(client, 0)
            elif choice == "3":
                publish_gps(client, True)
            elif choice == "4":
                publish_gps(client, False)
            elif choice == "5":
                logger.info("Modalità monitoraggio continuo attiva. Premi CTRL+C per uscire.")
                while True:
                    time.sleep(1)
            elif choice == "6":
                break
            else:
                print("[!] Scelta non valida")

            time.sleep(2)

    except KeyboardInterrupt:
        logger.info("Interruzione manuale.")
    finally:
        client.loop_stop()
        client.disconnect()
        logger.info(f"Disconnesso dal broker MQTT. Log salvato in: {LOG_FILE}")
