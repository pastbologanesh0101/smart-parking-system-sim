from tests.conftest import seed_lot, seed_spot


def test_availability_filters_by_spot_type_excludes_others(client):
    lot = seed_lot(client)
    seed_spot(client, lot["id"], "A1", "standard")
    seed_spot(client, lot["id"], "A2", "handicap")
    seed_spot(client, lot["id"], "A3", "ev_charging")

    resp = client.get("/api/availability", query_string={"spot_type": "standard"})
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["count"] == 1
    assert all(s["spot_type"] == "standard" for s in body["spots"])
    # Explicitly assert handicap/ev spots never leak into a "standard" search.
    returned_types = {s["spot_type"] for s in body["spots"]}
    assert "handicap" not in returned_types
    assert "ev_charging" not in returned_types


def test_availability_include_all_types_returns_everything(client):
    lot = seed_lot(client)
    seed_spot(client, lot["id"], "A1", "standard")
    seed_spot(client, lot["id"], "A2", "handicap")
    seed_spot(client, lot["id"], "A3", "ev_charging")

    resp = client.get(
        "/api/availability",
        query_string={"spot_type": "standard", "include_all_types": "true"},
    )
    body = resp.get_json()

    assert body["count"] == 3


def test_availability_excludes_occupied_spots(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")

    client.post("/api/sensors/occupancy", json={"spot_id": spot["id"], "occupied": True})

    resp = client.get("/api/availability", query_string={"lot_id": lot["id"]})
    body = resp.get_json()

    assert body["count"] == 0
