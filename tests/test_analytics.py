from tests.conftest import seed_lot, seed_rate_plan, seed_spot


def _reserve_checkin_checkout(client, spot_id, plate, start, end, checkin_at, checkout_at):
    reservation = client.post(
        "/api/reservations",
        json={
            "spot_id": spot_id,
            "license_plate": plate,
            "start_time": start,
            "end_time": end,
        },
    ).get_json()
    client.post(f"/api/reservations/{reservation['id']}/check-in", json={"at": checkin_at})
    client.post(f"/api/reservations/{reservation['id']}/check-out", json={"at": checkout_at})
    return reservation


def test_peak_occupancy_hour_computed_correctly_against_crafted_data(client):
    lot = seed_lot(client)
    s1 = seed_spot(client, lot["id"], "S1", "standard")
    s2 = seed_spot(client, lot["id"], "S2", "standard")
    s3 = seed_spot(client, lot["id"], "S3", "standard")
    s4 = seed_spot(client, lot["id"], "S4", "ev_charging")
    for spot_type in ("standard", "ev_charging"):
        seed_rate_plan(client, spot_type, 5.0)

    # Three separate spots all occupied for part of hour 14 (2pm) -> busiest hour.
    _reserve_checkin_checkout(
        client, s1["id"], "P1", "2026-01-01T14:00:00", "2026-01-01T15:00:00",
        "2026-01-01T14:10:00", "2026-01-01T14:50:00",
    )
    _reserve_checkin_checkout(
        client, s2["id"], "P2", "2026-01-01T14:00:00", "2026-01-01T15:00:00",
        "2026-01-01T14:05:00", "2026-01-01T14:55:00",
    )
    _reserve_checkin_checkout(
        client, s3["id"], "P3", "2026-01-01T14:00:00", "2026-01-01T15:00:00",
        "2026-01-01T14:20:00", "2026-01-01T14:40:00",
    )
    # One spot occupied only during hour 9 -- much less busy.
    _reserve_checkin_checkout(
        client, s4["id"], "P4", "2026-01-01T09:00:00", "2026-01-01T10:00:00",
        "2026-01-01T09:00:00", "2026-01-01T09:30:00",
    )

    resp = client.get("/api/analytics/peak-hour", query_string={"lot_id": lot["id"]})
    assert resp.get_json()["peak_hour"] == 14


def test_average_duration_per_spot_type_computed_correctly(client):
    lot = seed_lot(client)
    s1 = seed_spot(client, lot["id"], "S1", "standard")
    s2 = seed_spot(client, lot["id"], "S2", "standard")
    s3 = seed_spot(client, lot["id"], "S3", "standard")
    s4 = seed_spot(client, lot["id"], "S4", "ev_charging")
    for spot_type in ("standard", "ev_charging"):
        seed_rate_plan(client, spot_type, 5.0)

    # standard durations: 40min, 50min, 20min -> average = 11/18 h ~= 0.6111h
    _reserve_checkin_checkout(
        client, s1["id"], "P1", "2026-01-01T14:00:00", "2026-01-01T15:00:00",
        "2026-01-01T14:00:00", "2026-01-01T14:40:00",
    )
    _reserve_checkin_checkout(
        client, s2["id"], "P2", "2026-01-01T14:00:00", "2026-01-01T15:00:00",
        "2026-01-01T14:00:00", "2026-01-01T14:50:00",
    )
    _reserve_checkin_checkout(
        client, s3["id"], "P3", "2026-01-01T14:00:00", "2026-01-01T15:00:00",
        "2026-01-01T14:00:00", "2026-01-01T14:20:00",
    )
    # ev_charging duration: exactly 30 minutes -> average = 0.5h
    _reserve_checkin_checkout(
        client, s4["id"], "P4", "2026-01-01T09:00:00", "2026-01-01T10:00:00",
        "2026-01-01T09:00:00", "2026-01-01T09:30:00",
    )

    resp = client.get("/api/analytics/average-duration", query_string={"lot_id": lot["id"]})
    body = resp.get_json()

    assert body["standard"] == 0.6111
    assert body["ev_charging"] == 0.5
