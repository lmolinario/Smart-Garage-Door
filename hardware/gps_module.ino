/*
 * ============================================================
 *  Smart Garage Door – Proximity Automation Module
 *  File: gps_module.ino
 *  Author: Lello Molinario, Matteo Tuzi
 *  University of Cagliari – IoT & Digital Twins Lab
 *  Version: 1.6 – January 2026
 * ============================================================
 *  Descrizione:
 *  Questo modulo gestisce l'automazione di prossimità (FR5b) tramite
 *  il ricevitore GPS NEO-6M. Calcola la distanza tra la posizione
 *  corrente e quella del garage, pubblicando eventi MQTT:
 *
 *   - "Entrata" nel geofence → apertura automatica
 *   - "Uscita" dal geofence → chiusura automatica
 *
 *  Requisiti coperti:
 *   FR5b – Automazione in ingresso (geofence)
 *   FR3 – Pubblicazione automatica stato (MQTT)
 *   NFR9 – Riduzione traffico dati
 * ============================================================
  Spiegazione tecnica
Funzione	Descrizione
TinyGPSPlus::distanceBetween()	Calcola la distanza (in metri) tra coordinate attuali e coordinate del garage.
isInside	Flag booleano per evitare pubblicazioni ripetute inutili.
thresholdDistance	Raggio del geofence (default 20 m).
mqttClient.publish(topic_gps, …)	Pubblica eventi di entrata/uscita sul broker MQTT.
gpsSerial	Porta seriale software dedicata alla comunicazione col modulo NEO-6M (pin D3 ↔ TX, D4 ↔ RX).
Connessioni hardware NodeMCU ↔ GPS NEO-6M
GPS Pin	NodeMCU Pin	Descrizione
VCC	3.3 V	Alimentazione GPS
GND	GND	Massa
TX	D3	Trasmette dati GPS → ESP8266
RX	D4	Riceve comandi (opzionale)
PPS	—	(non usato)
Integrazione con il progetto

Pubblica eventi MQTT compatibili con controller_nodemcu.ino, topic home/garage/gps.

Requisiti

Librerie necessarie (Arduino IDE → Library Manager):

TinyGPSPlus
ESP8266WiFi
PubSubClient
ArduinoJson
SoftwareSerial


Baud rate GPS: 9600 bps

Coordinate del garage da inserire manualmente (homeLat, homeLon)
 */

#include <SoftwareSerial.h>
#include <TinyGPSPlus.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ---------------- Configurazione Wi-Fi ----------------
const char* ssid     = "YOUR_WIFI_SSID";       // <-- modifica
const char* password = "YOUR_WIFI_PASSWORD";   // <-- modifica

// ---------------- Broker MQTT ----------------
const char* mqtt_server = "test.mosquitto.org";
const int   mqtt_port   = 1883;
const char* topic_gps   = "home/garage/gps";

// ---------------- Pin mapping GPS ----------------
#define GPS_RX D3   // Riceve dal GPS TX
#define GPS_TX D4   // Invia al GPS RX
SoftwareSerial gpsSerial(GPS_RX, GPS_TX); // NodeMCU ↔ GPS NEO-6M

TinyGPSPlus gps;

// ---------------- Variabili di configurazione ----------------
WiFiClient espClient;
PubSubClient mqttClient(espClient);

bool isInside = false;
unsigned long lastMsg = 0;
const unsigned long GPS_UPDATE_INTERVAL = 5000; // 5 s
const double homeLat = 39.237300;  // ← Inserisci coordinate garage
const double homeLon = 9.102300;
const double thresholdDistance = 20.0; // m

// ---------------- Funzioni di connessione ----------------
void setup_wifi() {
  Serial.print("Connessione a "); Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWi-Fi connesso. IP: " + WiFi.localIP().toString());
}

void reconnect_mqtt() {
  while (!mqttClient.connected()) {
    Serial.print("Connessione MQTT...");
    String clientId = "GPS-" + String(ESP.getChipId());
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println(" connesso!");
    } else {
      Serial.print(" fallita (rc=");
      Serial.print(mqttClient.state());
      Serial.println("), ritento tra 5 s.");
      delay(5000);
    }
  }
}

// ---------------- Setup ----------------
void setup() {
  Serial.begin(9600);
  gpsSerial.begin(9600);
  delay(100);

  setup_wifi();
  mqttClient.setServer(mqtt_server, mqtt_port);
  Serial.println("Smart Garage Door – GPS Module avviato.");
}

// ---------------- Loop principale ----------------
void loop() {
  if (!mqttClient.connected()) reconnect_mqtt();
  mqttClient.loop();

  // Aggiorna dati GPS
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // Verifica se ci sono nuove coordinate valide
  if (gps.location.isUpdated()) {
    double latitude = gps.location.lat();
    double longitude = gps.location.lng();

    double distance = TinyGPSPlus::distanceBetween(latitude, longitude, homeLat, homeLon);
    Serial.print("Lat: "); Serial.print(latitude, 6);
    Serial.print("  Lon: "); Serial.print(longitude, 6);
    Serial.print("  Distanza: "); Serial.print(distance, 2); Serial.println(" m");

    // --- Logica geofence (FR5b)
    if (distance <= thresholdDistance && !isInside) {
      Serial.println("→ Entrata nel geofence: apertura porta.");
      mqttClient.publish(topic_gps, "{\"device_id\":123,\"value\":1}");
      isInside = true;
    }
    else if (distance > thresholdDistance && isInside) {
      Serial.println("→ Uscita dal geofence: chiusura porta.");
      mqttClient.publish(topic_gps, "{\"device_id\":123,\"value\":0}");
      isInside = false;
    }
  }

  // Pubblica heartbeat periodico ogni 5 s
  if (millis() - lastMsg > GPS_UPDATE_INTERVAL) {
    lastMsg = millis();
    StaticJsonDocument<64> doc;
    doc["device_id"] = 123;
    doc["lat"] = gps.location.lat();
    doc["lon"] = gps.location.lng();
    doc["inside"] = isInside;
    char buffer[64];
    size_t len = serializeJson(doc, buffer);
    mqttClient.publish("home/garage/gps/status", buffer, len);
  }

  delay(500);
}
