/*
 * ============================================================
 *  Smart Garage Door – Perception Layer (SERVO + DEBUG EXTENDED)
 *  File: controller_arduino.ino
 *  Author: Lello Molinario, Matteo Tuzi
 *  University of Cagliari – IoT & Digital Twins Lab
 *  Version: 1.6 – January 2026
 * ============================================================
 *  Requisiti implementati:
 *   FR4 – Chiusura automatica
 *   FR5a – Automazione in uscita (PIR)
 *   FR5b – Automazione arrivo utente (GPS)
 *   FR7 – Comando locale manuale
 *   FR8 – Rilevazione ostacolo (safety)
 *   NFR5 – Funzionamento offline
 * ============================================================
 */

#include <SoftwareSerial.h>
#include <Servo.h>

// ---------------- Pin mapping ----------------
#define RX_PIN 10  // Arduino RICEVE qui filo verde
#define TX_PIN 11  // Arduino TRASMETTE qui filo verde


#define PIR_PIN 4
#define SERVO_PIN 5
#define TRIG_PIN 6
#define ECHO_PIN 7
#define BUTTON_PIN 8
#define LED_PIN 9

// ---------------- Config Servo ----------------
Servo garageServo;
const int ANGLE_OPEN = 90;
const int ANGLE_CLOSED = 0;

// ---------------- Variabili globali ----------------
SoftwareSerial commSerial(RX_PIN, TX_PIN);

bool doorOpen = false;
bool userNearHome = false;  // FR5b: utente dentro al geofence

unsigned long tic = 0;
const unsigned long AUTO_CLOSE_TIME = 45000;  // 45 s

// ---------------- Funzione misura distanza ----------------
long measureDistanceCM() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  long distance = duration / 58;
  return distance > 400 ? 400 : distance;
}

// ---------------- Log con timestamp ----------------
void logTS(String msg) {
  Serial.print("[");
  Serial.print(millis());
  Serial.print(" ms] ");
  Serial.println(msg);
}

// ---------------- Funzioni porta ----------------
void openDoor() {
  logTS("Apertura lenta porta...");

  for (int pos = ANGLE_CLOSED; pos <= ANGLE_OPEN; pos++) {
    garageServo.write(pos);

    // LED lampeggia durante movimento
    digitalWrite(LED_PIN, (pos % 20 < 10) ? HIGH : LOW);
    delay(15);
  }

  digitalWrite(LED_PIN, HIGH);  // LED fisso = porta aperta
  commSerial.write((byte)0x01);
  doorOpen = true;
  tic = millis();

  logTS("Porta APERTA (slow motion + LED fisso).");
}

void closeDoor() {
  logTS("Chiusura lenta porta...");

  for (int pos = ANGLE_OPEN; pos >= ANGLE_CLOSED; pos--) {
    garageServo.write(pos);

    // LED lampeggia durante chiusura
    digitalWrite(LED_PIN, (pos % 20 < 10) ? HIGH : LOW);
    delay(15);
  }

  digitalWrite(LED_PIN, LOW);  // LED spento = porta chiusa
  commSerial.write((byte)0x00);
  doorOpen = false;

  logTS("Porta CHIUSA (slow motion + LED OFF).");
}

// ---------------- Setup ----------------
void setup() {
  Serial.begin(9600);
  commSerial.begin(9600);

  pinMode(PIR_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);

  garageServo.attach(SERVO_PIN);
  garageServo.write(ANGLE_CLOSED);

  logTS("====================================");
  logTS(" Smart Garage Door – FINAL FR5a + FR5b");
  logTS(" DEBUG EXTENDED + SERVO MODE");
  logTS("====================================\n");
}

// ---------------- Loop ----------------
void loop() {

  int pirState = digitalRead(PIR_PIN);
  int buttonState = digitalRead(BUTTON_PIN);
  long distance = measureDistanceCM();

  // --- DEBUG sensori ogni 500ms ---
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 500) {
    Serial.print("[");
    Serial.print(millis());
    Serial.print(" ms] PIR=");
    Serial.print(pirState ? "HIGH" : "LOW");
    Serial.print(" | DIST=");
    Serial.print(distance);
    Serial.print(" cm | userNearHome=");
    Serial.println(userNearHome ? "TRUE" : "FALSE");

    lastDebug = millis();
  }

  // =======================================================
  // FR5a + FR5b → Apertura automatica
  // PIR rileva movimento SOLO se userNearHome == TRUE
  // =======================================================
  if (pirState == HIGH && userNearHome && !doorOpen) {
    logTS("[AUTO] Apertura porta (PIR + GPS OK).");
    openDoor();
    delay(300);
  }

  // =======================================================
  // FR7 – Comando manuale
  // =======================================================
  if (buttonState == LOW) {
    logTS("[MANUALE] Pulsante premuto: toggle porta.");
    if (doorOpen) closeDoor();
    else openDoor();
    delay(300);
  }

  // =======================================================
  // FR5b – Comandi GPS dal NodeMCU
  // =======================================================
  if (commSerial.available()) {
    byte cmd = commSerial.read();
        // Ignora tutto ciò che non è un comando valido
    if (cmd > 0x03) return;
    if (cmd == 0x01) {  // apertura remota
      logTS("[REMOTE] Apertura remota.");
      openDoor();
      Serial.println("DOOR: OPEN");   // <--- necessario per lo script Python
    } else if (cmd == 0x00) {  // chiusura remota
      logTS("[REMOTE] Chiusura remota.");
      closeDoor();
      Serial.println("DOOR: CLOSED"); // <--- necessario per lo script Python
    } else if (cmd == 0x02) {  // utente dentro geofence
      userNearHome = true;
      logTS("[GPS] Utente dentro geofence → userNearHome=TRUE");
    } else if (cmd == 0x03) {  // utente fuori geofence
      userNearHome = false;
      logTS("[GPS] Utente fuori geofence → userNearHome=FALSE");
    }
  }

  // =======================================================
  // FR4 + FR8 – Chiusura automatica + safety ostacolo
  // =======================================================
  if (doorOpen && (millis() - tic > AUTO_CLOSE_TIME) && pirState == LOW) {

    if (distance < 10) {
      logTS("[SAFETY] Ostacolo sotto porta → riapertura.");
      openDoor();
    } else {
      logTS("[TIMER] Timeout → chiusura automatica.");
      closeDoor();
    }
  }

  delay(100);
}
