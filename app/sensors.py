"""
SIMULATED occupancy sensor client.

There is no real hardware involved anywhere in this file or this project.
This module stands in for a fleet of physical ultrasonic/inductive-loop
occupancy sensors that would normally live in each parking spot. In real
life those sensors would push a HTTP POST to an ingestion endpoint every
time a car arrives or leaves; here we generate that same event shape in
software, either:

  * on demand (call `simulate_occupancy_event` directly, e.g. from tests), or
  * on a background loop (`run_simulation_loop`) that behaves like a sensor
    fleet reporting in at a random interval.

Either way, the events are POSTed to the real `/api/sensors/occupancy`
ingestion endpoint on the real Flask backend, which updates the real
database exactly as it would for a genuine hardware sensor.
"""
import random
import time

import requests


def random_occupancy_event(spot_ids):
    """Build one simulated sensor reading: a random spot flips occupancy."""
    spot_id = random.choice(spot_ids)
    occupied = random.random() < 0.5
    return {"spot_id": spot_id, "occupied": occupied}


def simulate_occupancy_event(app, spot_ids=None):
    """Directly apply one simulated occupancy change inside the given Flask
    app's context, without going over HTTP. Useful for tests and for the
    CLI demo script. Returns the event dict that was applied."""
    from .extensions import db
    from .models import Spot

    with app.app_context():
        if spot_ids is None:
            spot_ids = [s.id for s in Spot.query.all()]
        if not spot_ids:
            return None
        event = random_occupancy_event(spot_ids)
        spot = Spot.query.get(event["spot_id"])
        spot.occupied = event["occupied"]
        db.session.commit()
        return event


def run_simulation_loop(base_url="http://127.0.0.1:5000", spot_ids=None,
                         min_interval_seconds=2, max_interval_seconds=8, iterations=None):
    """Background loop that behaves like a fleet of real sensors reporting
    in periodically. POSTs simulated readings to the real ingestion
    endpoint over HTTP. `iterations=None` runs forever; pass a number for a
    bounded demo run.

    This is a convenience script for manual/local demos -- it is NOT used
    by the automated test suite (tests call `simulate_occupancy_event`
    directly, which is deterministic and doesn't need a running server).
    """
    count = 0
    while iterations is None or count < iterations:
        if spot_ids:
            event = random_occupancy_event(spot_ids)
            try:
                requests.post(f"{base_url}/api/sensors/occupancy", json=event, timeout=5)
            except requests.RequestException as exc:  # pragma: no cover - demo path
                print(f"[sensor-sim] failed to report event {event}: {exc}")
        count += 1
        time.sleep(random.uniform(min_interval_seconds, max_interval_seconds))
