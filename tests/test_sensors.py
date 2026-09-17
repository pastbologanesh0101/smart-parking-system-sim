from app.sensors import simulate_occupancy_event
from tests.conftest import seed_lot, seed_spot


def test_simulated_sensor_occupancy_update_changes_availability_counts(app, client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")

    before = client.get("/api/availability", query_string={"lot_id": lot["id"]}).get_json()
    assert before["count"] == 1

    # Force the simulated sensor to report this spot as occupied (rather
    # than relying on the 50/50 random flip, for a deterministic test).
    event = simulate_occupancy_event(app, spot_ids=[spot["id"]])
    assert event["spot_id"] == spot["id"]

    resp = client.post("/api/sensors/occupancy", json={"spot_id": spot["id"], "occupied": True})
    assert resp.get_json()["occupied"] is True

    after = client.get("/api/availability", query_string={"lot_id": lot["id"]}).get_json()
    assert after["count"] == 0

    # Now simulate it becoming vacant again via the real ingestion endpoint.
    client.post("/api/sensors/occupancy", json={"spot_id": spot["id"], "occupied": False})
    restored = client.get("/api/availability", query_string={"lot_id": lot["id"]}).get_json()
    assert restored["count"] == 1
