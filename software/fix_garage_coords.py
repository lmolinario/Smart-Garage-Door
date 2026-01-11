#!/usr/bin/env python3
"""
Script per aggiornare le coordinate garage nel NodeMCU via MQTT
"""
import paho.mqtt.client as mqtt
import json
import time
import os

# Carica configurazione da config.json
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r") as f:
    CFG = json.load(f)

MQTT_BROKER = CFG.get("MQTT_BROKER", "test.mosquitto.org")
MQTT_PORT = CFG.get("MQTT_PORT", 1883)
TOPIC = "home/garage/update_location"

# Coordinate garage da config.json
GARAGE_LAT = CFG.get("HOME_LAT", 39.221900)
GARAGE_LON = CFG.get("HOME_LON", 9.105843)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connesso a MQTT broker")
        
        # Pubblica coordinate garage
        payload = {
            "lat": GARAGE_LAT,
            "lon": GARAGE_LON
        }
        
        result = client.publish(TOPIC, json.dumps(payload))
        if result.rc == 0:
            print(f"Coordinate garage aggiornate:")
            print(f"   Lat: {GARAGE_LAT}")
            print(f"   Lon: {GARAGE_LON}")
            print(f"   Topic: {TOPIC}")
            print(f"\nIMPORTANTE: Le coordinate sono state aggiornate nell'EEPROM del NodeMCU")
            print(f"   Ora riavvia il NodeMCU o aspetta il prossimo ciclo di geofence")
        else:
            print(f"Errore nell'invio")
    else:
        print(f"Connessione fallita: rc={rc}")

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    
    print(f"Connessione a {MQTT_BROKER}:{MQTT_PORT}...")
    print(f"Aggiornamento coordinate garage a: {GARAGE_LAT}, {GARAGE_LON}")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    
    # Attendi che il messaggio venga inviato
    time.sleep(2)
    client.loop_stop()
    client.disconnect()
    print("Script completato")

if __name__ == "__main__":
    main()


