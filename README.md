# Smart Garage Door – IoT System



<p align="center">
  <img src="images/smart.png" width="45%" alt="Telegram Bot Screenshot">
</p>


**Smart Garage Door** è un progetto IoT sviluppato nell’ambito del corso *Internet of Things and Digital Twins* (Master’s Degree in Computer Engineering, Cybersecurity and Artificial Intelligence – Università di Cagliari).  
L’obiettivo è realizzare un sistema intelligente per il controllo remoto e automatizzato di una porta da garage, basato su architettura **a tre livelli IoT** (Perception – Network – Application).

---


# Risorse del Progetto


---

## Simulazione Hardware (Tinkercad)

Modello funzionante del cablaggio Arduino + NodeMCU + sensori.

**[https://www.tinkercad.com/things/f9Zs6mc1zuk-smart-garage-door-iot-molinario-tuzi?sharecode=inUBEnqjk6C_21CV93_0aW_xciNNOMU7G4732abxZ9Q](https://www.tinkercad.com/things/f9Zs6mc1zuk-smart-garage-door-iot-molinario-tuzi?sharecode=inUBEnqjk6C_21CV93_0aW_xciNNOMU7G4732abxZ9Q)**

---

## Telegram Bot – Interfaccia Utente

Versione web del bot Telegram usato per il controllo del sistema.

**[https://web.telegram.org/a/#8594959211](https://web.telegram.org/a/#8594959211)**

---




---

## Architettura generale

Il sistema è composto da cinque macro-componenti interoperabili:

| Livello | Componente | Descrizione                                                           |
|----------|-------------|-----------------------------------------------------------------------|
| **Perception Layer** | Arduino UNO | Gestisce sensori (PIR, HC-SR04) e attuatori (servo).                  |
| **Network Layer** | NodeMCU ESP8266 | Connette il sistema alla rete Wi-Fi, comunica via MQTT con il server. |
| **Proximity Module** | GPS DIYmalls 16E | Abilita l’automazione di prossimità (geofencing).                     |
| **Application Layer** | Server Flask (Python) | Gestisce API, autenticazione e log degli eventi.                      |
| **User Interface** | Bot Telegram | Permette controllo e monitoraggio remoto dell’impianto.               |

---
<p align="center">
  <img src="docs/images/integration_flow.png" width="80%" alt="System Architecture Diagram">
</p>


---

##  Funzionalità principali

| Requisito | Descrizione | Stato |
|------------|--------------|--------|
| **FR1** | Apertura/chiusura remota via Telegram o Web API |  Implementato |
| **FR2** | Stato porta in tempo reale |  MQTT + Flask |
| **FR3** | Notifiche automatiche all’utente |  Telegram Bot |
| **FR4** | Chiusura automatica dopo inattività |  Arduino timer |
| **FR5a** | Automazione in uscita (movimento interno) |  PIR sensor |
| **FR5b** | Automazione in ingresso (geofence GPS) |  Implementato |
| **FR6** | Multiutenza e autenticazione |  Flask sessions |
| **FR7** | Comando locale manuale |  Pulsante |
| **FR8** | Rilevazione ostacolo |  HC-SR04 |
| **NFR9** | Consumo e costo contenuti |  < €80 |

---

##  Struttura del progetto

```

SmartGarageDoor/
│
├── hardware/              # Firmware Arduino / NodeMCU
│   ├── controller_arduino.ino
│   ├── controller_nodemcu.ino
│   ├── gps_module.ino
│   ├── wiring_diagram.tex
│   └── pinout_table.csv
│
├── software/              # Server Flask + Telegram Bot
│   ├── app.py
│   ├── telegram_listener.py
│   ├── timer.py
│   ├── config.json
│   └── requirements.txt
│
├── docs/                  # Documentazione e immagini per la tesi
│   └── images/
│       ├── hardware_connections.png
│       └── integration_flow.png
│
├── .gitignore
├── LICENSE
└── README.md

````

---

## Installazione e configurazione

### Requisiti hardware
- Arduino UNO  
- NodeMCU ESP8266  
- Sensore PIR HC-SR501  
- Modulo Servo 5 V  
- Sensore a ultrasuoni HC-SR04  
- Modulo GPS 
- Breadboard, cavetti Dupont, alimentazione 5 V  

### 🔸 Requisiti software
- **Arduino IDE** (>=2.0) con librerie:  
  `SoftwareSerial`, `PubSubClient`, `ArduinoJson`, `ESP8266WiFi`, `TinyGPSPlus`
- **Python 3.11+**
- Librerie Python: `flask`, `requests`, `paho-mqtt`, `python-telegram-bot`

---

##  Setup rapido

1. **Clona il repository**
   ```bash
   git clone https://github.com/<tuo-utente>/SmartGarageDoor.git
   cd SmartGarageDoor


2. **Configura l’ambiente Python**

   ```bash
   cd software
   python -m venv .venv
   source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
   pip install -r requirements.txt
   ```

3. **Imposta le credenziali**
   Modifica `software/config.json`:

   ```json
   {
       "WIFI_SSID": "YourNetwork",
       "WIFI_PASS": "YourPassword",
       "MQTT_BROKER": "test.mosquitto.org",
       "MQTT_PORT": 1883,
       "TELEGRAM_TOKEN": "xxxxxxxxx:xxxxxxxxx"
   }
   ```

4. **Avvia il server Flask**

   ```bash
   python app.py
   ```

5. **Esegui il bot Telegram**

   ```bash
   python telegram_listener.py
   ```

6. **Collega e carica i firmware**

   * `controller_arduino.ino` su Arduino UNO
   * `controller_nodemcu.ino` su NodeMCU ESP8266

   > Dubbi su quale sketch usare? Consulta la [guida di selezione dei firmware](hardware/FIRMWARE_GUIDE.md) per confrontare le quattro varianti disponibili e scegliere quella più adatta al tuo scenario (produzione, laboratorio o setup modulare).

---






# Interazione tramite Telegram Bot

Questa sezione descrive tutti i comandi disponibili nel bot Telegram utilizzato dal sistema **Smart Garage Door**, con esempi e funzioni di amministrazione.

---

##  Elenco completo dei comandi



| Comando                | Descrizione                                    |
| ---------------------- | ---------------------------------------------- |
| `/start`               | Avvia il bot e mostra il messaggio iniziale    |
| `/help`                | Mostra la lista dei comandi disponibili        |
| `/login <user> <pass>` | Effettua il login                              |
| `/logout`              | Chiude la sessione utente                      |
| `/status`              | Mostra lo stato del sistema (porta, GPS, MQTT) |
| `/on`                  | Apre la porta                                  |
| `/off`                 | Chiude la porta                                |
| `/pir`      | Stato del sensore PIR          |
| `/obstacle` | Stato sensore ostacolo HC-SR04 |
| `/listusers`                   | Mostra tutti gli utenti registrati |
| `/adduser <user> <pass>`       | Aggiunge un nuovo utente           |
| `/deluser <user>`              | Rimuove un utente                  |
| `/changepass <user> <newpass>` | Admin: cambia password a un utente |
| `/changepass <old> <new>`      | Utente: cambia la propria password |
| `/gps <lat> <lon>`         | Invia coordinate manuali al sistema (admin)                                    |
| *(Live Location Telegram)* | L’invio di posizione in diretta aggiorna automaticamente lo stato del geofence |
| `/adminstatus` | Cruscotto diagnostico completo: porta, GPS, MQTT, ultimi eventi |

---

<p align="center">
  <img src="docs/images/telegram_bot.png" width="45%" alt="Telegram Bot Screenshot">
</p>

---

##  Metriche e validazione

* **Tempo medio di risposta:** 0.8 s (porta) / 0.4 s (notifica)
* **Precisione sensori PIR/HC-SR04:** > 97 %
* **Tolleranza geofence simulato:** ± 1 %
* **Costo complessivo prototipo:** ≈ € 80

---

##  Autori

* **Lello Molinario e Matteo Tuzi** – Implementazione e documentazione (Università di Cagliari, Co-sviluppo hardware e testing
* **Prof. Michele Nitti** – Supervisione accademica

---

## Licenza

Questo progetto è distribuito con licenza **MIT**, in linea con le policy open-source del corso.
Vedi il file [LICENSE](LICENSE) per i dettagli.

---

##  Riferimenti

* [1] MQTT Specification v3.1.1 – OASIS Standard (2014)
* [2] TinyGPSPlus Library – Mikal Hart (GitHub)
* [3] Flask Framework – Pallets Project (Python 3.11)
* [4] ESP8266 Arduino Core Documentation

---

### “From design to implementation: connecting hardware, network and application in a unified IoT prototype.”

# 🚪 Smart Garage Door – IoT System

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Arduino%20%7C%20ESP8266-lightgrey.svg)]()
[![Made with ❤️ at UniCA](https://img.shields.io/badge/Made%20with%20%E2%9D%A4%EF%B8%8F-UniCA-red.svg)]()
