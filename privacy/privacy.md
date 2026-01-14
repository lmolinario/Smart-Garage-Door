# Privacy Policy – Smart Garage Door Bot

## 1. Scope and Purpose

The **@SmartGarageDoor2026Bot** is an academic prototype developed within the course  
*Internet of Things and Digital Twins* at the **University of Cagliari**.

The bot is designed exclusively for **educational and experimental purposes** and is not intended
for commercial deployment or large-scale public use.

---

## 2. Data Processing Overview

The system processes a **minimal and strictly necessary subset of data** in order to provide
its core functionalities (remote control, automation, and monitoring of a garage door).

No data are collected for analytics, profiling, marketing, or tracking purposes.

---

## 3. Types of Data Processed

The following data may be processed:

### 3.1 Telegram User Identifiers
- Telegram user ID and username are used **only for authentication and authorization**.
- Credentials are stored locally in a lightweight user database (`users.json`) on the application server.
- Passwords are stored in **hashed form** and are never transmitted or stored in plaintext.

### 3.2 Command and Event Data
- Commands sent via Telegram (e.g., `/on`, `/off`, `/status`) are processed in real time.
- System events (door state changes, sensor triggers) may be temporarily logged for debugging
  and traceability purposes.

### 3.3 Location Data (GPS)
- Location data are used **exclusively to evaluate geofencing conditions** for automation in entry (FR5b).
- GPS coordinates are **not stored as historical traces**, nor associated with user movement profiles.
- Location data are processed transiently and discarded after the geofence decision is made.

---

## 4. Data Storage and Retention

- All data are stored **locally** on the system hosting the application server.
- No cloud services, third-party analytics platforms, or external databases are used.
- Event logs are retained only for a limited and configurable time window and may be manually cleared.
- No backups of personal data are created outside the local system.

---

## 5. Data Sharing and Third Parties

- No personal data are shared with third parties.
- The bot communicates only with:
  - local IoT devices (Arduino / ESP8266),
  - the Telegram Bot API for message delivery.
- Telegram communication is protected by **TLS**, as provided by the Telegram infrastructure.

---

## 6. Security Measures

The system implements basic but effective security measures consistent with an academic IoT prototype:

- Role-based access control (user / administrator).
- Password hashing for stored credentials.
- Separation between local safety logic (Arduino) and network logic (ESP8266 / server).
- No exposure of sensitive endpoints without authentication.

---

## 7. User Rights and Transparency

Given the academic and non-commercial nature of the project:

- Users may request removal of their credentials from the local database at any time.
- Users can inspect the full source code of the system via the public GitHub repository.
- No automated decision-making with legal or significant personal impact is performed.

---

## 8. Compliance Statement

This project is developed in accordance with:
- data minimization principles,
- privacy-by-design guidelines,
- recommendations for IoT systems in academic environments.

It is **not classified as a production system** and is not subject to GDPR compliance obligations
applicable to commercial services, but it follows GDPR-inspired best practices where applicable.

---

## 9. Contact Information

For questions regarding this privacy policy or the system architecture, please contact the
project maintainers via the official GitHub repository or academic channels of the University of Cagliari.

---

_Last updated: January 2026_
