# Sart Garage Door – Firmware Guide
Questa cartella contiene gli sketch Arduino e ESP8266 utilizzati dal sistema **Smart Garage Door**.  
Ogni firmware svolge un ruolo specifico all’interno dell’architettura IoT, suddivisa in:

- **Perception Layer** → Arduino (sensori e attuatori locali)  
- **Connectivity Layer** → ESP8266 NodeMCU (Wi-Fi, MQTT, API Flask)  
- **Positioning Module** → Firmware GPS dedicato

La seguente tabella indica quando usare ciascun firmware, quali funzioni copre e in quali scenari è consigliato.

---

## 🧩 Panoramica dei Firmware

| Firmware | Dispositivo | Ruolo nel Sistema | Quando utilizzarlo                           | Vantaggi | Limitazioni |
|---------|-------------|-------------------|----------------------------------------------|----------|-------------|
| **controller_arduino.ino** | Arduino UNO | Gestione locale di sensori e attuatori: PIR, HC-SR04, servo, pulsante, LED. Funziona anche offline. | Sempre. È il controllo primario della porta. | Copre FR4 (chiusura automatica), FR5a (PIR), FR7 (pulsante), FR8 (ostacoli). Codice stabile e commentato. | Richiede un microcontrollore dedicato. |
| **controller_nodemcu.ino** | ESP8266 NodeMCU | Gateway Wi-Fi, MQTT, integrazione con server Flask, automazioni geofence. | Sempre. È il modulo di rete principale.      | Copre FR1-FR3 (apertura/chiusura/stato), supporta FR5b (geofence), logging chiaro, interoperabile con Telegram e dashboard. | Richiede configurazione Wi-Fi e broker MQTT. |
| **gps_module.ino** | ESP8266 NodeMCU (secondario) | Lettura e parsing di dati GPS NMEA tramite modulo GNSS esterno. Fornisce coordinate al sistema. | Quando è presente un modulo GPS fisico.                                      | Geofence basato su coordinate reali, modularità, indipendenza dalla logica principale. | Richiede un secondo ESP8266 o un pin UART dedicato. |


---

##  Come scegliere il firmware giusto

### ✔ Installazione reale completa  
Utilizzare sempre:
- `controller_arduino.ino` → gestione sensori/attuatori
- `controller_nodemcu.ino` → connettività, MQTT, logica geofence
- `gps_module.ino` → ** modulo GPS fisico** (qualsiasi modello compatibile NMEA)

Il modulo GPS fornisce:
- la posizione del punto fisso (garage/casa)  
- il raggio di geofence calcolato dalla NodeMCU principale  
- un riferimento affidabile per FR5b (automazione arrivo utente)

---

## Firmware GPS: compatibilità
Il file `gps_module.ino` è progettato per leggere **qualsiasi modulo GPS/GNSS che trasmette stringhe NMEA** tramite seriale UART.

---

##  Configurazione prima del caricamento
Aggiornare:
1. **SSID e password Wi-Fi** → NodeMCU  
2. **Indirizzo del broker MQTT**  
3. **Token o endpoint Flask (se usato)**  
4. **Soglia geofence (in metri)** → NodeMCU  
5. **Velocità seriale del modulo GPS** (di default 9600 baud)  

Non è necessaria alcuna configurazione specifica sul firmware Arduino.

---

##  Flusso dei dati a livello firmware

```

[Arduino] ← sensori (PIR, HC-SR04)
↓
[Arduino] → stato porta → NodeMCU
↑                       ↓
servo / pulsante    comandi da MQTT/Flask

[GPS Module] → coordinate → NodeMCU → logica geofence

```

---

##  Debug e sviluppo
Ogni firmware include log testuali per facilitare:

- diagnostica rete (NodeMCU)
- stato porta / movimento sensori (Arduino)
- validazione fix GPS e qualità segnale (GPS module)


---
