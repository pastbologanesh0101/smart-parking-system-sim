from tests.conftest import seed_lot, seed_rate_plan, seed_spot


def _make_reservation(client, spot_id, plate="ABC-123"):
    resp = client.post(
        "/api/reservations",
        json={
            "spot_id": spot_id,
            "license_plate": plate,
            "start_time": "2026-01-01T09:00:00",
            "end_time": "2026-01-01T18:00:00",
        },
    )
    return resp.get_json()


def test_checkin_marks_spot_occupied_and_starts_billing_clock(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")
    seed_rate_plan(client, "standard", 10.0)
    reservation = _make_reservation(client, spot["id"])

    resp = client.post(
        f"/api/reservations/{reservation['id']}/check-in",
        json={"at": "2026-01-01T09:00:00"},
    )
    body = resp.get_json()

    assert body["checked_in_at"] == "2026-01-01T09:00:00"
    assert body["bill_amount"] is None

    spots_resp = client.get("/api/spots", query_string={"lot_id": lot["id"]})
    spot_after = next(s for s in spots_resp.get_json() if s["id"] == spot["id"])
    assert spot_after["occupied"] is True


def test_checkout_computes_correct_bill_for_known_duration(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")
    seed_rate_plan(client, "standard", 10.0)
    reservation = _make_reservation(client, spot["id"])

    client.post(f"/api/reservations/{reservation['id']}/check-in", json={"at": "2026-01-01T09:00:00"})
    resp = client.post(
        f"/api/reservations/{reservation['id']}/check-out",
        json={"at": "2026-01-01T11:00:00"},  # exactly 2 hours
    )
    body = resp.get_json()

    assert body["status"] == "completed"
    assert body["bill_amount"] == 20.0  # 2h * $10/h, no rounding needed


def test_checkout_applies_minimum_charge_for_short_stay(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")
    seed_rate_plan(client, "standard", 10.0)
    reservation = _make_reservation(client, spot["id"])

    client.post(f"/api/reservations/{reservation['id']}/check-in", json={"at": "2026-01-01T09:00:00"})
    resp = client.post(
        f"/api/reservations/{reservation['id']}/check-out",
        json={"at": "2026-01-01T09:10:00"},  # only 10 minutes
    )
    body = resp.get_json()

    # Minimum billable duration is 1 hour, regardless of actual duration.
    assert body["bill_amount"] == 10.0


def test_checkout_rounds_partial_hours_up_to_nearest_quarter_hour(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")
    seed_rate_plan(client, "standard", 10.0)
    reservation = _make_reservation(client, spot["id"])

    client.post(f"/api/reservations/{reservation['id']}/check-in", json={"at": "2026-01-01T09:00:00"})
    resp = client.post(
        f"/api/reservations/{reservation['id']}/check-out",
        json={"at": "2026-01-01T10:10:00"},  # 1h10m -> rounds up to 1.25h
    )
    body = resp.get_json()

    assert body["bill_amount"] == 12.5  # 1.25h * $10/h

    # And check out also frees the spot.
    spots_resp = client.get("/api/spots", query_string={"lot_id": lot["id"]})
    spot_after = next(s for s in spots_resp.get_json() if s["id"] == spot["id"])
    assert spot_after["occupied"] is False


def test_checkout_without_prior_checkin_is_rejected(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")
    seed_rate_plan(client, "standard", 10.0)
    reservation = _make_reservation(client, spot["id"])

    resp = client.post(
        f"/api/reservations/{reservation['id']}/check-out",
        json={"at": "2026-01-01T11:00:00"},
    )

    assert resp.status_code == 409
