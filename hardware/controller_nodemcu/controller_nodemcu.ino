/*
 * ============================================================
 *  Smart Garage Door – Network Layer (Garage Fixed GPS + MQTT + Geofence)
 *  File: controller_nodemcu_final_v1.6.ino
 *  Authors: Lello Molinario, Matteo Tuzi
 *  Version: 1.6 – January 2026
 *
 *  Funzionalità:
 *   - Connessione Wi-Fi con lista di SSID (fallback)
 *   - Pubblicazione posizione fissa del garage (lat, lon)
 *   - Aggiornamento coordinate garage via MQTT (update_location)
 *   - Salvataggio coordinate in EEPROM (persistenti)
 *   - Ricezione comandi apertura/chiusura (FR1, FR2, FR3)
 *   - Pubblicazione stato porta (aperta/chiusa)
 *   - Heartbeat periodico di stato (topic: home/garage/status)
 *   - Geofence utente (FR5b) via posizione MQTT (user_location) → invio 0x02 / 0x03 ad Arduino
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <SoftwareSerial.h>
#include <EEPROM.h>
#include <ESP8266WebServer.h>

ESP8266WebServer server(80);

#define EEPROM_SIZE 32

// ---------------- Wi-Fi: lista reti (primary + backup) ----------------
const char* ssid_list[] = {
  "SOSSU",          // Rete principale
  "iPhone di Matteo"    // Eventuale hotspot di backup (personalizzala)
};

const char* pass_list[] = {
  "18KMdispiaggi@", // password rete principale
  "tuzi1234" // password rete backup
};

const uint8_t WIFI_COUNT = sizeof(ssid_list) / sizeof(ssid_list[0]);

// ---------------- Broker MQTT ----------------
const char* mqtt_server = "test.mosquitto.org";
const int   mqtt_port   = 1883;

const char* topic_cmd             = "home/garage/cmd";              // comandi apertura/chiusura
const char* topic_door            = "home/garage/door";             // stato porta
const char* topic_gps             = "home/garage/location";         // posizione garage (lat, lon)
const char* topic_update_location = "home/garage/update_location";  // aggiorna lat/lon garage
const char* topic_status          = "home/garage/status";           // heartbeat di stato
const char* topic_user_location   = "home/garage/user_location";    // posizione utente (lat, lon)

// ---------------- Pin mapping verso Arduino ----------------
#define RX_PIN D2   // NodeMCU RICEVE qui (collegato a TX Arduino = pin 10)
#define TX_PIN D1   // NodeMCU TRASMETTE qui (collegato a RX Arduino = pin 11)
SoftwareSerial commSerial(RX_PIN, TX_PIN);


// ---------------- Variabili globali ----------------
WiFiClient espClient;
PubSubClient mqttClient(espClient);

bool  doorOpen = false;
float garageLat = 0.0;
float garageLon = 0.0;

unsigned long lastHeartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 30000; // 30 s

unsigned long lastMqttActivity = 0;
const unsigned long MQTT_WATCHDOG_MS = 300000;  // 5 min

// ---------------- GEOFENCE CONFIG (FR5b) ----------------
float userLat = 0.0;
float userLon = 0.0;

bool userInside = false;     // stato corrente del geofence
unsigned long lastGeoCheck = 0;
const unsigned long GEO_INTERVAL = 5000;  // ogni 5 secondi

const float GEOFENCE_RADIUS = 15.0;  // metri (raggio geofence)

// =========================================================
// EEPROM: salvataggio coordinate garage
// =========================================================
void saveGarageLocation(float lat, float lon) {
  Serial.println(F("Salvataggio coordinate garage in EEPROM..."));

  EEPROM.put(0, lat);
  EEPROM.put(4, lon);
  uint8_t valid = 1;
  EEPROM.put(8, valid);
  EEPROM.commit();

  Serial.println(F("Coordinate salvate in EEPROM."));
}

// =========================================================
// EEPROM: lettura coordinate garage
// =========================================================
bool loadGarageLocation(float &lat, float &lon) {
  uint8_t valid;
  EEPROM.get(8, valid);

  if (valid != 1) {
    Serial.println(F("Nessuna coordinata valida in EEPROM."));
    return false;
  }

  EEPROM.get(0, lat);
  EEPROM.get(4, lon);

  Serial.println(F("Coordinate garage caricate da EEPROM:"));
  Serial.print(F("   LAT = ")); Serial.println(lat, 6);
  Serial.print(F("   LON = ")); Serial.println(lon, 6);

  return true;
}

// =========================================================
// Pubblicazione posizione garage su MQTT
// =========================================================
void publishGarageLocation() {
  StaticJsonDocument<128> gpsDoc;

  gpsDoc["device_id"] = ESP.getChipId();
  gpsDoc["lat"]       = garageLat;
  gpsDoc["lon"]       = garageLon;

  char buffer[128];
  size_t len = serializeJson(gpsDoc, buffer);
  mqttClient.publish(topic_gps, buffer, len);

  Serial.println(F("Posizione garage inviata al server MQTT."));
}

// =========================================================
// Pubblicazione heartbeat di stato
// =========================================================
void publishStatus() {
  if (!mqttClient.connected()) return;

  StaticJsonDocument<192> stDoc;

  stDoc["device_id"] = ESP.getChipId();
  stDoc["online"]    = true;
  stDoc["door_open"] = doorOpen ? 1 : 0;
  stDoc["rssi"]      = WiFi.RSSI();
  stDoc["uptime_ms"] = millis();
  stDoc["lat"]       = garageLat;
  stDoc["lon"]       = garageLon;

  char buffer[192];
  size_t len = serializeJson(stDoc, buffer);
  mqttClient.publish(topic_status, buffer, len);

  Serial.println(F("Heartbeat stato pubblicato su MQTT."));
}

// =========================================================
// Wi-Fi: connessione con fallback su più reti
// =========================================================
void setup_wifi() {
  Serial.println(F("Avvio connessione Wi-Fi..."));

  for (uint8_t i = 0; i < WIFI_COUNT; i++) {
    Serial.print(F("Tentativo rete: "));
    Serial.println(ssid_list[i]);

    WiFi.begin(ssid_list[i], pass_list[i]);

    uint8_t retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 20) {
      delay(500);
      Serial.print(".");
      retries++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
      Serial.print(F("Wi-Fi connesso a: "));
      Serial.println(ssid_list[i]);
      Serial.print(F("   IP: "));
      Serial.println(WiFi.localIP());
      return;
    }

    Serial.println(F("Connessione fallita, provo la prossima rete..."));
  }

  Serial.println(F("Nessuna rete Wi-Fi disponibile. Attendo 10 secondi e riavvio..."));
  delay(10000);
  ESP.restart();
}

// =========================================================
// Calcolo distanza Haversine in metri
// =========================================================
double haversine(double lat1, double lon1, double lat2, double lon2) {
  double R = 6371000; // raggio Terra in metri
  double dLat = radians(lat2 - lat1);
  double dLon = radians(lon2 - lon1);

  lat1 = radians(lat1);
  lat2 = radians(lat2);

  double a = sin(dLat / 2) * sin(dLat / 2) +
             sin(dLon / 2) * sin(dLon / 2) * cos(lat1) * cos(lat2);

  double c = 2 * atan2(sqrt(a), sqrt(1 - a));
  return R * c;
}

// =========================================================
// Controllo geofence (FR5b) – invia 0x02 / 0x03 ad Arduino
// =========================================================
void updateGeofence() {
  if (millis() - lastGeoCheck < GEO_INTERVAL) return;
  lastGeoCheck = millis();

  if (userLat == 0.0 && userLon == 0.0) {
    Serial.println(F("Nessuna posizione utente ancora ricevuta."));
    return;
  }

  double dist = haversine(userLat, userLon, garageLat, garageLon);

  Serial.print(F("Distanza utente → garage: "));
  Serial.print(dist);
  Serial.println(F(" m"));

  // Utente entra nel geofence
  if (!userInside && dist <= GEOFENCE_RADIUS) {
    userInside = true;
    Serial.println(F("[GEOFENCE] Utente ENTRATO nel geofence → invio 0x02"));
    commSerial.write((byte)0x02);  // Arduino: userNearHome = true
  }
  // Utente esce dal geofence (con hysteresis di 20 m)
  else if (userInside && dist > GEOFENCE_RADIUS + 20) {
    userInside = false;
    Serial.println(F("[GEOFENCE] Utente USCITO dal geofence → invio 0x03"));
    commSerial.write((byte)0x03);  // Arduino: userNearHome = false
  }
}

// =========================================================
// MQTT: callback
// =========================================================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  lastMqttActivity = millis();

  // Copia payload in String sicura
  String msg;
  msg.reserve(length);
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }

  Serial.print(F("[MQTT RX] "));
  Serial.print(topic);
  Serial.print(F(" → "));
  Serial.println(msg);

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, msg);
  if (err) {
    Serial.print(F("Errore JSON: "));
    Serial.println(err.c_str());
    return;
  }

  // Comandi apertura/chiusura
  if (strcmp(topic, topic_cmd) == 0) {
    int value = doc["value"] | -1;
    if (value == 1) {
      Serial.println(F("[MQTT] Apertura porta (cmd=1)"));
      commSerial.write((byte)0x01);
    } else if (value == 0) {
      Serial.println(F("[MQTT] Chiusura porta (cmd=0)"));
      commSerial.write((byte)0x00);
    }
  }

  // Aggiornamento coordinate garage
  else if (strcmp(topic, topic_update_location) == 0) {
    float newLat = doc["lat"] | 0.0;
    float newLon = doc["lon"] | 0.0;

    if (newLat == 0.0 && newLon == 0.0) {
      Serial.println(F("Coordinate ricevute non valide (0,0). Ignoro."));
      return;
    }

    Serial.println(F("[UPDATE] Nuove coordinate garage ricevute via MQTT."));
    garageLat = newLat;
    garageLon = newLon;
    saveGarageLocation(garageLat, garageLon);
    publishGarageLocation();
  }

  // Aggiornamento posizione utente per geofence (FR5b)
  else if (strcmp(topic, topic_user_location) == 0) {
    userLat = doc["lat"] | 0.0;
    userLon = doc["lon"] | 0.0;

    Serial.println(F("[MQTT] Nuova posizione utente ricevuta."));
    Serial.print(F("   LAT=")); Serial.println(userLat, 6);
    Serial.print(F("   LON=")); Serial.println(userLon, 6);
  }
}

// =========================================================
// MQTT: gestione riconnessione
// =========================================================
void reconnect_mqtt() {
  while (!mqttClient.connected()) {
    Serial.print(F("Connessione MQTT... "));
    String clientId = "GarageNode-" + String(ESP.getChipId());

    if (mqttClient.connect(clientId.c_str())) {
      Serial.println(F("OK!"));

      mqttClient.subscribe(topic_cmd);
      mqttClient.subscribe(topic_update_location);
      mqttClient.subscribe(topic_user_location);

      publishGarageLocation();
      publishStatus();
      lastMqttActivity = millis();
    } else {
      Serial.print(F("Fallita (rc="));
      Serial.print(mqttClient.state());
      Serial.println(F("). Riprovo tra 5 secondi..."));
      delay(5000);
    }
  }
}

// =========================================================
// SETUP
// =========================================================
void setup() {
  Serial.begin(9600);
  commSerial.begin(9600);

  Serial.println(F("\n===================================="));
  Serial.println(F(" Smart Garage Door – NodeMCU FINAL  "));
  Serial.println(F(" Version 1.6 – Geofence + MQTT      "));
  Serial.println(F("===================================="));

  EEPROM.begin(EEPROM_SIZE);

  // Carica coordinate da EEPROM o usa default
  if (!loadGarageLocation(garageLat, garageLon)) {
    garageLat = 40.79550345107391;  // Sorso
    garageLon = 8.57486692260615;
    Serial.println(F("Uso coordinate manuali predefinite."));
    saveGarageLocation(garageLat, garageLon);
  }

  Serial.println(F("DEBUG COORDINATE GARAGE"));
  Serial.print(F("LAT_GARAGE = ")); Serial.println(garageLat, 6);
  Serial.print(F("LON_GARAGE = ")); Serial.println(garageLon, 6);
  Serial.println(F("------------------------------------"));


  setup_wifi();

  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(mqttCallback);

  reconnect_mqtt();
  // =========================================================
  // HTTP SERVER (FR1–FR3)
  // =========================================================

  // Apertura porta (cmd=1)
  server.on("/apri", []() {
    commSerial.write((byte)0x01);  // invio comando ad Arduino
    server.send(200, "text/plain", "OK: door opening");
    Serial.println(F("[HTTP] Comando APERTURA ricevuto"));
  });

  // Chiusura porta (cmd=0)
  server.on("/chiudi", []() {
    commSerial.write((byte)0x00);  // invio comando ad Arduino
    server.send(200, "text/plain", "OK: door closing");
    Serial.println(F("[HTTP] Comando CHIUSURA ricevuto"));
  });

  // Stato porta (ritorna JSON)
  server.on("/status", []() {
    StaticJsonDocument<64> doc;
    doc["door"] = doorOpen ? 1 : 0;

    char buffer[64];
    size_t len = serializeJson(doc, buffer);
    server.send(200, "application/json", buffer);
  });

  // 404 Not Found
  server.onNotFound([]() {
    server.send(404, "text/plain", "404 Not Found");
  });

  // Avvio server HTTP
  server.begin();
  Serial.println(F("HTTP server avviato sulla porta 80"));

}

// =========================================================
// LOOP
// =========================================================
void loop() {

  if (!mqttClient.connected()) {
    reconnect_mqtt();
  }

  mqttClient.loop();

  // Watchdog MQTT: se nessuna attività da troppo → tenta recovery
  if (millis() - lastMqttActivity > MQTT_WATCHDOG_MS) {
    Serial.println(F("MQTT watchdog: nessuna attività da 5 minuti → reconnect."));
    lastMqttActivity = millis();
    mqttClient.disconnect();
    reconnect_mqtt();
  }

  // Heartbeat periodico
  if (millis() - lastHeartbeat > HEARTBEAT_INTERVAL) {
    publishStatus();
    lastHeartbeat = millis();
  }

  // Stato porta da Arduino
  if (commSerial.available()) {
    byte state = commSerial.read();
    doorOpen = (state == 0x01);

    StaticJsonDocument<64> doc;
    doc["device_id"] = ESP.getChipId();
    doc["value"]     = doorOpen ? 1 : 0;

    char buffer[64];
    size_t len = serializeJson(doc, buffer);
    mqttClient.publish(topic_door, buffer, len);

    Serial.print(F("Porta: "));
    Serial.println(doorOpen ? F("APERTA") : F("CHIUSA"));
  }

  // Geofence FR5b – aggiorna stato userNearHome su Arduino
  updateGeofence();
  
  server.handleClient();

  delay(50);
}
