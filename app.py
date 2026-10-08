"""
Shipping status service called by the Agentforce "Get Shipping Status" Apex action
through the Shipping_Service Named Credential.

Simulates a carrier tracking API. Tracking numbers line up with
scripts/apex/seed_orders.apex. Tracking numbers starting with FAIL
return 503 so the agent's fallback path can be tested end to end.
"""
from __future__ import annotations

import hmac
import os
from datetime import date, datetime, time, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

API_KEY_ENV = "SHIPPING_API_KEY"

app = FastAPI(title="Shipping Status Service", version="1.0.0")


class TrackingEvent(BaseModel):
    timestamp: str
    location: str
    description: str


class Shipment(BaseModel):
    tracking_number: str
    carrier: str
    status: str
    last_location: str
    estimated_delivery: str | None
    events: list[TrackingEvent]


def _ts(days_ago: int, hour: int) -> str:
    d = date.today() - timedelta(days=days_ago)
    return datetime.combine(d, time(hour, 0), tzinfo=timezone.utc).isoformat()


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def _delivered(tracking: str, carrier: str, city: str, delivered_days_ago: int) -> Shipment:
    return Shipment(
        tracking_number=tracking,
        carrier=carrier,
        status="Delivered",
        last_location=city,
        estimated_delivery=_iso(-delivered_days_ago),
        events=[
            TrackingEvent(timestamp=_ts(delivered_days_ago + 3, 9), location="Louisville, KY", description="Departed facility"),
            TrackingEvent(timestamp=_ts(delivered_days_ago, 7), location=city, description="Out for delivery"),
            TrackingEvent(timestamp=_ts(delivered_days_ago, 15), location=city, description="Delivered, left at front door"),
        ],
    )


def build_shipments() -> dict[str, Shipment]:
    """Rebuilt on startup so dates stay relative to today, matching the seed data."""
    shipments = [
        _delivered("TRK10001", "UPS", "Jersey City, NJ", 5),
        Shipment(
            tracking_number="TRK10002",
            carrier="FedEx",
            status="In Transit",
            last_location="Edison, NJ",
            estimated_delivery=_iso(2),
            events=[
                TrackingEvent(timestamp=_ts(2, 18), location="Memphis, TN", description="Picked up"),
                TrackingEvent(timestamp=_ts(0, 6), location="Edison, NJ", description="Arrived at facility"),
            ],
        ),
        _delivered("TRK10004", "UPS", "Hoboken, NJ", 45),
        _delivered("TRK10005", "USPS", "Newark, NJ", 10),
        Shipment(
            tracking_number="TRK10008",
            carrier="FedEx",
            status="Delayed",
            last_location="Harrisburg, PA",
            estimated_delivery=_iso(4),
            events=[
                TrackingEvent(timestamp=_ts(7, 12), location="Indianapolis, IN", description="Picked up"),
                TrackingEvent(timestamp=_ts(3, 10), location="Harrisburg, PA", description="Weather delay at facility"),
            ],
        ),
        _delivered("TRK10009", "USPS", "Brooklyn, NY", 29),
        _delivered("TRK10010", "UPS", "Queens, NY", 31),
        _delivered("TRK10012", "FedEx", "Jersey City, NJ", 3),
    ]
    return {s.tracking_number: s for s in shipments}


SHIPMENTS = build_shipments()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get(API_KEY_ENV)
    if not expected:
        raise HTTPException(status_code=500, detail="Server API key is not configured")
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/shipments/{tracking_number}", response_model=Shipment, dependencies=[Depends(require_api_key)])
def get_shipment(tracking_number: str) -> Shipment:
    key = tracking_number.strip().upper()
    if key.startswith("FAIL"):
        raise HTTPException(status_code=503, detail="Carrier upstream unavailable")
    shipment = SHIPMENTS.get(key)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment
