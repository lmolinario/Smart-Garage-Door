"""
============================================================
 Smart Garage Door – Performance Monitor
 File: performance_monitor.py
 Author: Lello Molinario, Matteo Tuzi
 Version: 3.1 – December 2025
============================================================
"""

import serial
import requests
import time
import statistics
import matplotlib.pyplot as plt
import os
from datetime import datetime

# ==========================================================
# CONFIGURAZIONE
# ==========================================================
NODEMCU_IP = "http://172.20.10.2"
# Su Windows: COM1, COM2, COM3, etc. (su Linux: /dev/ttyACM0, /dev/ttyUSB0, etc.)
SERIAL_PORT = "COM5"  # Cambia questo se Arduino è su un'altra porta
BAUD_RATE = 9600
TIMEOUT_HTTP = 5
TIMEOUT_SERIAL = 10
N_TESTS = 10
MAX_WAIT = 15        # massimo tempo di attesa per un feedback

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ==========================================================
# FUNZIONE DI TEST CONNESSIONE
# ==========================================================
def test_connection():
    """
    Testa la connettività HTTP al NodeMCU prima di iniziare i test.
    Ritorna True se connesso, False altrimenti.
    """
    print(f"\nTest connessione NodeMCU ({NODEMCU_IP})...")
    try:
        # Test con endpoint /status che esiste sul NodeMCU
        response = requests.get(f"{NODEMCU_IP}/status", timeout=TIMEOUT_HTTP)
        print(f"Connessione OK (status: {response.status_code})")
        return True
    except requests.exceptions.ConnectTimeout:
        print(f"TIMEOUT: Impossibile raggiungere {NODEMCU_IP}")
        print(f"\nPOSSIBILI SOLUZIONI:")
        print(f"   1. Verifica che il NodeMCU sia acceso e connesso al WiFi")
        print(f"   2. Controlla che l'IP sia corretto (attualmente: {NODEMCU_IP})")
        print(f"   3. Verifica di essere sulla stessa rete WiFi del NodeMCU")
        print(f"   4. Controlla il router per trovare l'IP assegnato al NodeMCU")
        print(f"   5. Assicurati che il NodeMCU esponga un server HTTP (non solo MQTT)")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"ERRORE CONNESSIONE: {e}")
        print(f"\nPOSSIBILI SOLUZIONI:")
        print(f"   1. Verifica che il NodeMCU sia acceso e connesso")
        print(f"   2. Controlla che l'IP {NODEMCU_IP} sia corretto")
        print(f"   3. Verifica di essere sulla stessa rete WiFi")
        return False
    except Exception as e:
        print(f"ERRORE: {e}")
        return False

# ==========================================================
# APERTURA SERIAL (UNA VOLTA SOLA)
# ==========================================================
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
print(f"Porta seriale aperta: {SERIAL_PORT}")

# Pulizia iniziale del buffer (Arduino potrebbe aver già inviato dati)
time.sleep(0.5)  # Attesa breve per stabilizzazione
ser.reset_input_buffer()
# Scarta eventuali dati residui
while ser.in_waiting > 0:
    ser.read(ser.in_waiting)
print("Buffer seriale pulito")

def clear_serial_buffer():
    """Pulisce completamente il buffer seriale leggendo tutti i dati disponibili."""
    ser.reset_input_buffer()
    time.sleep(0.1)  # Breve attesa per permettere a nuovi dati di arrivare
    # Leggi e scarta tutto ciò che è nel buffer
    discarded = 0
    start_clear = time.time()
    while time.time() - start_clear < 0.5:  # Max 500ms per pulire
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            discarded += len(data)
        else:
            break
    if discarded > 0:
        print(f"  (scartati {discarded} byte dal buffer)")

def measure_command(cmd_url, expected_feedback):
    """
    Invia una richiesta HTTP → attende feedback seriale.
    Ritorna (latenza_http, tempo_totale) o (None, None) su errore.
    """
    # Pulisci completamente il buffer prima di inviare il comando
    clear_serial_buffer()

    print(f"Richiesta HTTP: {cmd_url}")
    start_total = time.time()

    # ----- HTTP -----
    start_http = time.time()
    try:
        requests.get(cmd_url, timeout=TIMEOUT_HTTP)
        latency_http = time.time() - start_http
    except requests.exceptions.ConnectTimeout:
        print(f"TIMEOUT HTTP: Impossibile raggiungere {cmd_url}")
        return None, None
    except requests.exceptions.ConnectionError as e:
        print(f"ERRORE CONNESSIONE HTTP: {e}")
        return None, None
    except Exception as e:
        print(f"Errore HTTP: {e}")
        return None, None

    # ----- SERIAL: attesa feedback -----
    while True:
        if time.time() - start_total > MAX_WAIT:
            print("TIMEOUT: feedback non ricevuto")
            return None, None

        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue

        print(f"Serial: {line}")

        if expected_feedback in line:
            delay_total = time.time() - start_total
            print(f"{expected_feedback} in {delay_total:.3f}s (latenza HTTP: {latency_http:.3f}s)")
            return latency_http, delay_total


# ==========================================================
# LOOP DI TEST
# ==========================================================
results = []
print("\nAvvio test prestazioni Smart Garage Door...\n")
time.sleep(2)
# Test connessione iniziale
if not test_connection():
    print("\nERRORE: Impossibile connettersi al NodeMCU")
    print("   Lo script verrà terminato. Risolvi il problema di connettività e riprova.")
    ser.close()
    exit(1)

for i in range(N_TESTS):
    print(f"\n---------------- Test {i+1}/{N_TESTS} ----------------")

    latency_open, delay_open = measure_command(f"{NODEMCU_IP}/apri", "DOOR: OPEN")
    time.sleep(2)

    latency_close, delay_close = measure_command(f"{NODEMCU_IP}/chiudi", "DOOR: CLOSED")
    time.sleep(3)

    if delay_open is not None:
        results.append(("open", delay_open, latency_open))
    if delay_close is not None:
        results.append(("close", delay_close, latency_close))


# ==========================================================
# ANALISI STATISTICA
# ==========================================================
def compute_stats(label, values):
    if not values:
        return None
    return {
        "command": label,
        "count": len(values),
        "avg": round(statistics.mean(values), 3),
        "stdev": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0
    }

open_times = [v for c, v, _ in results if c == "open"]
close_times = [v for c, v, _ in results if c == "close"]
open_latencies = [l for c, _, l in results if c == "open"]
close_latencies = [l for c, _, l in results if c == "close"]

report = [compute_stats("open", open_times),
          compute_stats("close", close_times)]
report = [r for r in report if r]

latency_report = [compute_stats("open", open_latencies),
                  compute_stats("close", close_latencies)]
latency_report = [r for r in latency_report if r]

# Chiusura porta seriale
ser.close()

# Verifica se ci sono risultati
if not report:
    print("\nATTENZIONE: Nessun dato raccolto!")
    print("   Tutte le richieste sono fallite. Verifica:")
    print("   - Connessione NodeMCU")
    print("   - Configurazione IP")
    print("   - Stato del sistema")
    exit(1)

# ==========================================================
# ESPORTAZIONE TABELLA PNG
# ==========================================================
def create_table_image(data, headers, title, output_path):
    """Crea un'immagine PNG di una tabella usando matplotlib."""
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.axis('tight')
    ax.axis('off')
    
    table = ax.table(cellText=data, colLabels=headers, cellLoc='center', loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.5)
    
    # Stile header
    for i in range(len(headers)):
        table[(0, i)].set_facecolor('#4CAF50')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # Stile celle dati (alternanza colori)
    for i in range(1, len(data) + 1):
        for j in range(len(headers)):
            if i % 2 == 0:
                table[(i, j)].set_facecolor('#f0f0f0')
            else:
                table[(i, j)].set_facecolor('white')
    
    plt.suptitle(title, fontsize=12, fontweight='bold', y=0.95)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close()

# Prepara dati per la tabella tempo totale
table_data = []
for r in report:
    table_data.append([
        r["command"].upper(),
        str(r["count"]),
        f"{r['avg']:.3f}",
        f"{r['stdev']:.3f}"
    ])

headers = ["Comando", "Count", "Media (s)", "Stdev (s)"]
table_path = os.path.join(OUTPUT_DIR, f"performance_table_{TIMESTAMP}.png")
create_table_image(table_data, headers, "TEMPO TOTALE (HTTP + movimento servo)", table_path)
print(f"\nTabella generata: {table_path}")

# Tabella per la latenza
if latency_report:
    latency_table_data = []
    for r in latency_report:
        latency_table_data.append([
            r["command"].upper(),
            str(r["count"]),
            f"{r['avg']:.3f}",
            f"{r['stdev']:.3f}"
        ])
    
    latency_table_path = os.path.join(OUTPUT_DIR, f"latency_table_{TIMESTAMP}.png")
    create_table_image(latency_table_data, headers, "LATENZA HTTP (solo richiesta/risposta)", latency_table_path)
    print(f"Tabella latenza generata: {latency_table_path}")


# ==========================================================
# GRAFICO PNG - Tempo totale
# ==========================================================
commands = [r["command"] for r in report]
averages = [r["avg"] for r in report]

plt.figure(figsize=(6, 4))
plt.bar(commands, averages)
plt.ylabel("Tempo medio (s)")
plt.title("Tempo medio di risposta – Smart Garage Door")
plt.grid(axis="y", linestyle="--", alpha=0.5)

for i, v in enumerate(averages):
    plt.text(i, v + 0.01, f"{v:.2f}s", ha='center')

chart_path = os.path.join(OUTPUT_DIR, f"chart_{TIMESTAMP}.png")
plt.tight_layout()
plt.savefig(chart_path, dpi=200)
plt.close()

print(f"Grafico tempo totale salvato in: {chart_path}")

# ==========================================================
# GRAFICO PNG - Latenza HTTP
# ==========================================================
if latency_report:
    latency_commands = [r["command"] for r in latency_report]
    latency_averages = [r["avg"] for r in latency_report]
    
    plt.figure(figsize=(6, 4))
    plt.bar(latency_commands, latency_averages)
    plt.ylabel("Latenza HTTP (s)")
    plt.title("Latenza HTTP media – Smart Garage Door")
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    
    for i, v in enumerate(latency_averages):
        plt.text(i, v + 0.001, f"{v:.3f}s", ha='center')
    
    latency_chart_path = os.path.join(OUTPUT_DIR, f"latency_{TIMESTAMP}.png")
    plt.tight_layout()
    plt.savefig(latency_chart_path, dpi=200)
    plt.close()
    
    print(f"Grafico latenza HTTP salvato in: {latency_chart_path}")


# ==========================================================
# RISULTATI FINALI
# ==========================================================
print("\n================ RISULTATI FINALI ================\n")
print("TEMPO TOTALE (HTTP + movimento servo):")
for r in report:
    print(f"{r['command'].upper()} -> media: {r['avg']}s | stdev: {r['stdev']} | n={r['count']}")

if latency_report:
    print("\nLATENZA HTTP (solo richiesta/re risposta):")
    for r in latency_report:
        print(f"{r['command'].upper()} -> media: {r['avg']}s | stdev: {r['stdev']} | n={r['count']}")

print("\nTest completato con successo.\n")
