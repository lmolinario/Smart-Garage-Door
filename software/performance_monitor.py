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
import csv
import statistics
import matplotlib.pyplot as plt
import os
from datetime import datetime

# ==========================================================
# CONFIGURAZIONE
# ==========================================================
NODEMCU_IP = "http://192.168.1.118"
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600
TIMEOUT_HTTP = 5
TIMEOUT_SERIAL = 10
N_TESTS = 10
MAX_WAIT = 15        # massimo tempo di attesa per un feedback

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ==========================================================
# APERTURA SERIAL (UNA VOLTA SOLA)
# ==========================================================
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
print(f"Porta seriale aperta: {SERIAL_PORT}")

def measure_command(cmd_url, expected_feedback):
    """
    Invia una richiesta HTTP → attende feedback seriale.
    Ritorna tempo di risposta o None su errore.
    """
    ser.reset_input_buffer()

    print(f"Richiesta HTTP: {cmd_url}")
    start = time.time()

    # ----- HTTP -----
    try:
        requests.get(cmd_url, timeout=TIMEOUT_HTTP)
    except Exception as e:
        print(f"Errore HTTP: {e}")
        return None

    # ----- SERIAL: attesa feedback -----
    while True:
        if time.time() - start > MAX_WAIT:
            print("TIMEOUT: feedback non ricevuto")
            return None

        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue

        print(f"Serial: {line}")

        if expected_feedback in line:
            delay = time.time() - start
            print(f"{expected_feedback} in {delay:.3f}s")
            return delay


# ==========================================================
# LOOP DI TEST
# ==========================================================
results = []
print("\nAvvio test prestazioni Smart Garage Door...\n")

for i in range(N_TESTS):
    print(f"\n---------------- Test {i+1}/{N_TESTS} ----------------")

    delay_open = measure_command(f"{NODEMCU_IP}/apri", "DOOR: OPEN")
    time.sleep(2)

    delay_close = measure_command(f"{NODEMCU_IP}/chiudi", "DOOR: CLOSED")
    time.sleep(3)

    if delay_open:
        results.append(("open", delay_open))
    if delay_close:
        results.append(("close", delay_close))


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

open_times = [v for c, v in results if c == "open"]
close_times = [v for c, v in results if c == "close"]

report = [compute_stats("open", open_times),
          compute_stats("close", close_times)]
report = [r for r in report if r]


# ==========================================================
# ESPORTAZIONE CSV
# ==========================================================
csv_path = os.path.join(OUTPUT_DIR, f"performance_{TIMESTAMP}.csv")

with open(csv_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["command", "count", "avg", "stdev"])
    writer.writeheader()
    writer.writerows(report)

print(f"\nCSV generato: {csv_path}")


# ==========================================================
# GRAFICO PNG
# ==========================================================
commands = [r["command"] for r in report]
averages = [r["avg"] for r in report]
errors = [r["stdev"] for r in report]

plt.figure(figsize=(6, 4))
plt.bar(commands, averages, yerr=errors, capsize=6)
plt.ylabel("Tempo medio (s)")
plt.title("Tempo medio di risposta – Smart Garage Door")
plt.grid(axis="y", linestyle="--", alpha=0.5)

for i, v in enumerate(averages):
    plt.text(i, v + 0.01, f"{v:.2f}s", ha='center')

chart_path = os.path.join(OUTPUT_DIR, f"chart_{TIMESTAMP}.png")
plt.tight_layout()
plt.savefig(chart_path, dpi=200)
plt.close()

print(f"Grafico salvato in: {chart_path}")


# ==========================================================
# RISULTATI FINALI
# ==========================================================
print("\n================ RISULTATI FINALI ================\n")
for r in report:
    print(f"▶ {r['command'].upper()} → media: {r['avg']}s | stdev: {r['stdev']} | n={r['count']}")

print("\nTest completato con successo.\n")
