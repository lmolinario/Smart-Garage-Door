"""Test di integrazione leggeri per l'app Flask del garage smart."""

import json
import os
import sys
import copy
from types import SimpleNamespace

import pytest
from werkzeug.exceptions import HTTPException

# Assicura che i test possano importare il modulo app.py
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(CURRENT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Disabilita la connessione MQTT reale durante i test
os.environ.setdefault("ENABLE_MQTT", "0")

import app  # noqa: E402  pylint: disable=wrong-import-position


@pytest.fixture(autouse=True)
def reset_state():
    """Ripristina stato, API key e file utenti dopo ogni test."""
    original_api_key = app.API_KEY
    original_users = copy.deepcopy(app.USERS)
    users_path = app.USERS_PATH
    users_file = None
    if os.path.exists(users_path):
        with open(users_path, "r", encoding="utf-8") as f:
            users_file = f.read()

    app.reset_app_state()
    yield

    app.API_KEY = original_api_key
    app.USERS = original_users
    if users_file is not None:
        with open(users_path, "w", encoding="utf-8") as f:
            f.write(users_file)
    elif os.path.exists(users_path):
        os.remove(users_path)
    app.reset_app_state()


@pytest.fixture
def client():
    """Restituisce un client di test Flask pronto all'uso."""
    return app.app.test_client()


@pytest.mark.integration
def test_status_endpoint_reports_current_state(client):
    """Verifica che /status rifletta lo stato interno dell'applicazione."""
    with app._state_lock:  # pylint: disable=protected-access
        app._last_state.update(  # pylint: disable=protected-access
            {
                "door": 1,
                "door_ts": 42.0,
                "gps_inside": True,
                "gps_ts": 84.0,
                "mqtt_connected": True,
            }
        )

    response = client.get("/status")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["door"] == 1
    assert payload["gps_inside"] is True
    assert payload["mqtt_connected"] is True


@pytest.mark.integration
def test_on_endpoint_requires_api_key_when_configured(client, monkeypatch):
    """Gli endpoint protetti devono rifiutare richieste senza API key."""
    app.API_KEY = "segretissima"
    recorded = {}

    def fake_publish(topic, message, qos=0, retain=False):  # noqa: D401
        recorded.update({
            "topic": topic,
            "message": message,
            "qos": qos,
            "retain": retain,
        })
        return None

    monkeypatch.setattr(app, "mqttc", SimpleNamespace(publish=fake_publish))

    unauthorized = client.post("/on")
    assert unauthorized.status_code == 401

    authorized = client.post("/on", headers={"X-API-Key": "segretissima"})
    assert authorized.status_code == 200
    assert json.loads(recorded["message"]) == {
        "device_id": app.DEVICE_ID,
        "value": 1,
    }

    with app._state_lock:  # pylint: disable=protected-access
        assert app._events[0]["kind"] == "cmd_publish"  # pylint: disable=protected-access


@pytest.mark.integration
def test_gps_event_updates_state_and_publishes(client, monkeypatch):
    """/gps deve accettare il payload e aggiornare lo stato interno."""
    app.API_KEY = ""  # bypass autenticazione
    published = {}

    def fake_publish(topic, message, qos=0, retain=False):
        published["topic"] = topic
        published["message"] = message
        return None

    monkeypatch.setattr(app, "mqttc", SimpleNamespace(publish=fake_publish))

    response = client.post("/gps", json={"value": 1, "lat": 45.0, "lon": 9.0})
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"

    payload = json.loads(published["message"])
    assert payload["value"] == 1
    assert payload["lat"] == 45.0
    assert payload["lon"] == 9.0

    with app._state_lock:  # pylint: disable=protected-access
        assert app._last_state["gps_inside"] is True  # pylint: disable=protected-access
        assert app._events[0]["kind"] == "gps_ingest"  # pylint: disable=protected-access


@pytest.mark.unit
def test_publish_cmd_records_event(monkeypatch):
    """La funzione helper publish_cmd deve inviare su MQTT e loggare l'evento."""
    published = {}

    def fake_publish(topic, message, qos=0, retain=False):
        published["topic"] = topic
        published["message"] = message
        published["qos"] = qos
        published["retain"] = retain
        return None

    monkeypatch.setattr(app, "mqttc", SimpleNamespace(publish=fake_publish))

    with app._state_lock:  # pylint: disable=protected-access
        app._events.clear()  # pylint: disable=protected-access

    app.publish_cmd(0)

    payload = json.loads(published["message"])
    assert published["topic"] == app.TOPIC_CMD
    assert payload == {"device_id": app.DEVICE_ID, "value": 0}
    assert published["retain"] is False

    with app._state_lock:  # pylint: disable=protected-access
        assert app._events[0]["kind"] == "cmd_publish"  # pylint: disable=protected-access


def test_on_message_updates_motion_and_obstacle():
    """La logica MQTT deve aggiornare correttamente PIR e distanza ostacolo."""
    app.reset_app_state()

    pir_msg = SimpleNamespace(payload=b"1", topic=app.TOPIC_PIR)
    obstacle_payload = json.dumps({"distance_cm": 12, "blocked": True}).encode()
    obstacle_msg = SimpleNamespace(payload=obstacle_payload, topic=app.TOPIC_OBSTACLE)

    app.on_message(app.mqttc, None, pir_msg)
    app.on_message(app.mqttc, None, obstacle_msg)

    with app._state_lock:  # pylint: disable=protected-access
        assert app._last_state["pir_motion"] is True  # pylint: disable=protected-access
        assert app._last_state["obstacle_blocked"] is True  # pylint: disable=protected-access
        assert app._last_state["obstacle_cm"] == 12  # pylint: disable=protected-access
        kinds = [evt["kind"] for evt in app._events]  # pylint: disable=protected-access
        assert "pir_update" in kinds and "obstacle_update" in kinds


def test_add_and_delete_user_flow_with_api_key(client):
    """Verifica il ciclo completo di aggiunta e rimozione utente in modalità admin."""
    app.API_KEY = "ABC123456"

    new_user = {"username": "tester", "password": "pwd123"}
    headers = {"X-API-Key": app.API_KEY}

    created = client.post("/addUser", json=new_user, headers=headers)
    assert created.status_code == 200

    listed = client.get("/listUsers", headers=headers)
    assert listed.status_code == 200
    assert listed.get_json()["users"].get("tester") == "user"

    deleted = client.post("/delUser", json={"username": "tester"}, headers=headers)
    assert deleted.status_code == 200


def test_change_password_admin_mode_updates_hash(client):
    """La modalità admin deve permettere cambio password e salvataggio su file."""
    app.API_KEY = "ABC123456"
    headers = {"X-API-Key": app.API_KEY}

    payload = {
        "username": "admin",
        "new_password": "nuova_password",
        "admin_mode": True,
    }

    response = client.post("/changePassword", json=payload, headers=headers)
    assert response.status_code == 200

    check = client.post(
        "/checkUser",
        json={"username": "admin", "password": "nuova_password"},
    )
    assert check.status_code == 200
    assert check.get_json()["status"] == "ok"
