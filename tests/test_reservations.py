from tests.conftest import seed_lot, seed_spot


def test_reservation_with_no_conflict_succeeds(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")

    resp = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
        },
    )

    assert resp.status_code == 201
    assert resp.get_json()["status"] == "active"


def test_reservation_overlapping_same_spot_rejected(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")

    first = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
        },
    )
    assert first.status_code == 201

    # Overlaps [10:00, 12:00) by starting at 11:00.
    second = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "XYZ-999",
            "start_time": "2026-01-01T11:00:00",
            "end_time": "2026-01-01T13:00:00",
        },
    )

    assert second.status_code == 409
    assert "overlap" in second.get_json()["error"].lower()


def test_back_to_back_reservations_on_same_spot_are_not_conflicts(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")

    first = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
        },
    )
    # Starts exactly when the first one ends -- allowed.
    second = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "XYZ-999",
            "start_time": "2026-01-01T12:00:00",
            "end_time": "2026-01-01T13:00:00",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201


def test_reservation_different_spot_same_time_succeeds(client):
    lot = seed_lot(client)
    spot_a = seed_spot(client, lot["id"], "A1", "standard")
    spot_b = seed_spot(client, lot["id"], "A2", "standard")

    first = client.post(
        "/api/reservations",
        json={
            "spot_id": spot_a["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
        },
    )
    second = client.post(
        "/api/reservations",
        json={
            "spot_id": spot_b["id"],
            "license_plate": "XYZ-999",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201


def test_reservation_on_handicap_spot_requires_accessibility_confirmation(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "H1", "handicap")

    rejected = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
        },
    )
    assert rejected.status_code == 409

    accepted = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
            "accessibility_confirmed": True,
        },
    )
    assert accepted.status_code == 201


def test_reservation_rejects_invalid_time_window(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")

    resp = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T12:00:00",
            "end_time": "2026-01-01T10:00:00",
        },
    )

    assert resp.status_code == 409


def test_cancelling_a_reservation_frees_the_spot_for_a_new_reservation(client):
    lot = seed_lot(client)
    spot = seed_spot(client, lot["id"], "A1", "standard")

    first = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "ABC-123",
            "start_time": "2026-01-01T10:00:00",
            "end_time": "2026-01-01T12:00:00",
        },
    ).get_json()

    # Before cancelling, an overlapping reservation is rejected.
    blocked = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "XYZ-999",
            "start_time": "2026-01-01T10:30:00",
            "end_time": "2026-01-01T11:30:00",
        },
    )
    assert blocked.status_code == 409

    cancel_resp = client.post(f"/api/reservations/{first['id']}/cancel")
    assert cancel_resp.get_json()["status"] == "cancelled"

    # After cancelling, the same overlapping window succeeds.
    allowed = client.post(
        "/api/reservations",
        json={
            "spot_id": spot["id"],
            "license_plate": "XYZ-999",
            "start_time": "2026-01-01T10:30:00",
            "end_time": "2026-01-01T11:30:00",
        },
    )
    assert allowed.status_code == 201
