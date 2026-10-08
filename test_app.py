import pytest
from fastapi.testclient import TestClient

import app as service

KEY = "test-key"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(service.API_KEY_ENV, KEY)
    return TestClient(service.app)


def get(client, tracking, key=KEY):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(f"/shipments/{tracking}", headers=headers)


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_in_transit_shipment(client):
    r = get(client, "TRK10002")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "In Transit"
    assert body["carrier"] == "FedEx"
    assert body["events"][-1]["description"] == "Arrived at facility"


def test_delivered_shipment_has_three_events(client):
    body = get(client, "TRK10001").json()
    assert body["status"] == "Delivered"
    assert len(body["events"]) == 3


def test_delayed_shipment(client):
    body = get(client, "TRK10008").json()
    assert body["status"] == "Delayed"
    assert "Weather" in body["events"][-1]["description"]


def test_lookup_is_case_and_whitespace_insensitive(client):
    assert get(client, " trk10002 ").status_code == 200


def test_unknown_tracking_returns_404(client):
    r = get(client, "TRK99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Shipment not found"


def test_fail_prefix_simulates_carrier_outage(client):
    r = get(client, "FAIL10007")
    assert r.status_code == 503


def test_missing_key_rejected(client):
    assert get(client, "TRK10002", key=None).status_code == 401


def test_wrong_key_rejected(client):
    assert get(client, "TRK10002", key="nope").status_code == 401


def test_server_without_configured_key_fails_closed(monkeypatch):
    monkeypatch.delenv(service.API_KEY_ENV, raising=False)
    c = TestClient(service.app)
    assert c.get("/shipments/TRK10002", headers={"X-API-Key": "anything"}).status_code == 500


@pytest.mark.parametrize("tracking", ["TRK10001", "TRK10004", "TRK10005", "TRK10009", "TRK10010", "TRK10012"])
def test_every_seeded_delivered_order_is_tracked(client, tracking):
    assert get(client, tracking).json()["status"] == "Delivered"
