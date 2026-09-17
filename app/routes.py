from datetime import datetime

from flask import Blueprint, jsonify, request

from .extensions import db
from .models import Lot, RatePlan, Reservation, Spot
from .services import (
    ReservationError,
    average_duration_per_spot_type,
    cancel_reservation,
    check_in,
    check_out,
    create_reservation,
    get_available_spots,
    peak_occupancy_hour,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _parse_dt(value):
    if value is None:
        return None
    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# Lots & spots
# ---------------------------------------------------------------------------


@api_bp.post("/lots")
def create_lot():
    data = request.get_json(force=True) or {}
    name = data.get("name")
    total_spots = data.get("total_spots", 0)
    if not name:
        return jsonify({"error": "name is required"}), 400

    lot = Lot(name=name, total_spots=total_spots)
    db.session.add(lot)
    db.session.commit()
    return jsonify(lot.to_dict()), 201


@api_bp.get("/lots")
def list_lots():
    return jsonify([lot.to_dict() for lot in Lot.query.all()])


@api_bp.post("/lots/<int:lot_id>/spots")
def create_spot(lot_id):
    lot = Lot.query.get_or_404(lot_id)
    data = request.get_json(force=True) or {}
    spot_number = data.get("spot_number")
    spot_type = data.get("spot_type", "standard")

    if not spot_number:
        return jsonify({"error": "spot_number is required"}), 400
    if spot_type not in ("standard", "handicap", "ev_charging"):
        return jsonify({"error": "invalid spot_type"}), 400

    spot = Spot(lot_id=lot.id, spot_number=spot_number, spot_type=spot_type)
    db.session.add(spot)
    db.session.commit()
    return jsonify(spot.to_dict()), 201


@api_bp.get("/spots")
def list_spots():
    lot_id = request.args.get("lot_id", type=int)
    query = Spot.query
    if lot_id is not None:
        query = query.filter_by(lot_id=lot_id)
    return jsonify([s.to_dict() for s in query.all()])


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


@api_bp.get("/availability")
def availability():
    """Query real-time availability.

    Query params:
      lot_id           optional int
      spot_type        optional str: standard | handicap | ev_charging
      include_all_types  optional bool ("true"/"false"); if true, spot_type
                          is ignored and every type is included.

    IMPORTANT filtering guarantee: passing spot_type=standard will NEVER
    return handicap or ev_charging spots, unless include_all_types=true is
    also passed.
    """
    lot_id = request.args.get("lot_id", type=int)
    spot_type = request.args.get("spot_type")
    include_all_types = request.args.get("include_all_types", "false").lower() == "true"

    spots = get_available_spots(lot_id=lot_id, spot_type=spot_type, include_all_types=include_all_types)
    return jsonify({
        "count": len(spots),
        "spots": [s.to_dict() for s in spots],
    })


# ---------------------------------------------------------------------------
# Rate plans
# ---------------------------------------------------------------------------


@api_bp.post("/rate-plans")
def create_rate_plan():
    data = request.get_json(force=True) or {}
    spot_type = data.get("spot_type")
    price_per_hour = data.get("price_per_hour")
    if spot_type not in ("standard", "handicap", "ev_charging") or price_per_hour is None:
        return jsonify({"error": "spot_type and price_per_hour are required"}), 400

    plan = RatePlan.query.filter_by(spot_type=spot_type).first()
    if plan is None:
        plan = RatePlan(spot_type=spot_type, price_per_hour=price_per_hour)
        db.session.add(plan)
    else:
        plan.price_per_hour = price_per_hour
    db.session.commit()
    return jsonify(plan.to_dict()), 201


@api_bp.get("/rate-plans")
def list_rate_plans():
    return jsonify([p.to_dict() for p in RatePlan.query.all()])


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------


@api_bp.post("/reservations")
def make_reservation():
    data = request.get_json(force=True) or {}
    spot_id = data.get("spot_id")
    license_plate = data.get("license_plate")
    start_time = _parse_dt(data.get("start_time"))
    end_time = _parse_dt(data.get("end_time"))
    accessibility_confirmed = bool(data.get("accessibility_confirmed", False))

    if not all([spot_id, license_plate, start_time, end_time]):
        return jsonify({"error": "spot_id, license_plate, start_time, end_time are required"}), 400

    spot = Spot.query.get(spot_id)
    if spot is None:
        return jsonify({"error": "spot not found"}), 404

    try:
        reservation = create_reservation(
            spot, license_plate, start_time, end_time,
            accessibility_confirmed=accessibility_confirmed,
        )
    except ReservationError as exc:
        return jsonify({"error": str(exc)}), 409

    return jsonify(reservation.to_dict()), 201


@api_bp.post("/reservations/<int:reservation_id>/cancel")
def cancel_reservation_route(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    reservation = cancel_reservation(reservation)
    return jsonify(reservation.to_dict())


@api_bp.get("/reservations")
def list_reservations():
    spot_id = request.args.get("spot_id", type=int)
    query = Reservation.query
    if spot_id is not None:
        query = query.filter_by(spot_id=spot_id)
    return jsonify([r.to_dict() for r in query.all()])


@api_bp.post("/reservations/<int:reservation_id>/check-in")
def check_in_route(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    data = request.get_json(silent=True) or {}
    at = _parse_dt(data.get("at")) or datetime.utcnow()
    reservation = check_in(reservation, at)
    return jsonify(reservation.to_dict())


@api_bp.post("/reservations/<int:reservation_id>/check-out")
def check_out_route(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    data = request.get_json(silent=True) or {}
    at = _parse_dt(data.get("at")) or datetime.utcnow()

    plan = RatePlan.query.filter_by(spot_type=reservation.spot.spot_type).first()
    if plan is None:
        return jsonify({"error": f"no rate plan configured for spot_type={reservation.spot.spot_type}"}), 400

    try:
        reservation = check_out(reservation, at, plan.price_per_hour)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    return jsonify(reservation.to_dict())


# ---------------------------------------------------------------------------
# Simulated sensor ingestion
# ---------------------------------------------------------------------------


@api_bp.post("/sensors/occupancy")
def sensor_occupancy():
    """Ingestion endpoint for occupancy events. In production this would be
    called by real hardware sensors; in this project it is called by the
    simulated sensor client in app/sensors.py. The backend logic here is
    identical either way -- it has no idea whether the caller is real
    hardware or a simulator, which is exactly the point of the simulation."""
    data = request.get_json(force=True) or {}
    spot_id = data.get("spot_id")
    occupied = data.get("occupied")

    if spot_id is None or occupied is None:
        return jsonify({"error": "spot_id and occupied are required"}), 400

    spot = Spot.query.get(spot_id)
    if spot is None:
        return jsonify({"error": "spot not found"}), 404

    spot.occupied = bool(occupied)
    db.session.commit()
    return jsonify(spot.to_dict())


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@api_bp.get("/analytics/peak-hour")
def analytics_peak_hour():
    lot_id = request.args.get("lot_id", type=int)
    query = Reservation.query
    if lot_id is not None:
        query = query.join(Spot).filter(Spot.lot_id == lot_id)
    reservations = query.all()
    hour = peak_occupancy_hour(reservations)
    return jsonify({"peak_hour": hour})


@api_bp.get("/analytics/average-duration")
def analytics_average_duration():
    lot_id = request.args.get("lot_id", type=int)
    query = db.session.query(Spot.spot_type, Reservation.checked_in_at, Reservation.checked_out_at).join(
        Reservation, Reservation.spot_id == Spot.id
    )
    if lot_id is not None:
        query = query.filter(Spot.lot_id == lot_id)
    rows = query.all()
    result = average_duration_per_spot_type(rows)
    return jsonify(result)
