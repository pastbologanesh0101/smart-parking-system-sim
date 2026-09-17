"""
Core business logic for the Smart Parking System: availability, reservation
overlap checking, billing, and analytics. Kept separate from routes.py so it
can be unit tested directly and reused by the CLI/sensor simulator.
"""
import math
from collections import defaultdict
from datetime import datetime

from .extensions import db
from .models import Reservation, Spot

# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def get_available_spots(lot_id=None, spot_type=None, include_all_types=False):
    """Return currently-unoccupied spots.

    Filtering rule (important): if `spot_type` is given and
    `include_all_types` is False, ONLY spots of exactly that type are
    returned. A search for "standard" spots must never include handicap or
    ev_charging spots -- callers must explicitly opt into `include_all_types`
    (or omit spot_type) to see every type.
    """
    query = Spot.query.filter_by(occupied=False)
    if lot_id is not None:
        query = query.filter_by(lot_id=lot_id)
    if spot_type is not None and not include_all_types:
        query = query.filter_by(spot_type=spot_type)
    return query.all()


# ---------------------------------------------------------------------------
# Reservation overlap logic
# ---------------------------------------------------------------------------


def ranges_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """Half-open interval overlap test: [start, end).

    Two reservations [s1, e1) and [s2, e2) overlap iff s1 < e2 and s2 < e1.
    A reservation ending exactly when another starts is NOT a conflict
    (back-to-back bookings are allowed).
    """
    return start_a < end_b and start_b < end_a


def has_conflicting_reservation(spot_id: int, start_time: datetime, end_time: datetime,
                                 exclude_reservation_id: int | None = None) -> bool:
    """True if `spot_id` already has an active reservation overlapping the
    given window. Cancelled/completed reservations never block a new one."""
    query = Reservation.query.filter_by(spot_id=spot_id, status="active")
    if exclude_reservation_id is not None:
        query = query.filter(Reservation.id != exclude_reservation_id)

    for existing in query.all():
        if ranges_overlap(start_time, end_time, existing.start_time, existing.end_time):
            return True
    return False


class ReservationError(ValueError):
    """Raised for any rejected reservation attempt (conflict, bad window,
    or a spot-type restriction)."""


def create_reservation(spot: Spot, license_plate: str, start_time: datetime,
                        end_time: datetime, accessibility_confirmed: bool = False) -> Reservation:
    """Create a new active reservation for `spot`, enforcing:

    1. start_time must be strictly before end_time.
    2. No overlap with another active reservation on the same spot.
    3. Handicap spots require `accessibility_confirmed=True`. This is a
       deliberate policy choice (documented in the README) so that
       accessibility spots aren't booked by accident/default -- the caller
       must explicitly confirm eligibility. EV-charging spots have no such
       restriction (any vehicle may charge).
    """
    if start_time >= end_time:
        raise ReservationError("start_time must be before end_time")

    if spot.spot_type == "handicap" and not accessibility_confirmed:
        raise ReservationError(
            "Reserving a handicap spot requires accessibility_confirmed=true"
        )

    if has_conflicting_reservation(spot.id, start_time, end_time):
        raise ReservationError("Spot is already reserved for an overlapping time window")

    reservation = Reservation(
        spot_id=spot.id,
        license_plate=license_plate,
        start_time=start_time,
        end_time=end_time,
        status="active",
    )
    db.session.add(reservation)
    db.session.commit()
    return reservation


def cancel_reservation(reservation: Reservation) -> Reservation:
    reservation.status = "cancelled"
    db.session.commit()
    return reservation


# ---------------------------------------------------------------------------
# Check-in / check-out / billing
# ---------------------------------------------------------------------------

# Billing rule (documented explicitly, also see README "Billing rules"):
#   * Minimum charge is 1 hour, even if the stay is shorter.
#   * Beyond the first hour, duration is rounded UP to the nearest 15
#     minutes (0.25 hour) -- i.e. any partial 15-minute block is billed in
#     full. This mirrors how many real parking garages round.
MINIMUM_BILLABLE_HOURS = 1.0
ROUNDING_INCREMENT_HOURS = 0.25


def compute_billed_hours(duration_hours: float) -> float:
    if duration_hours <= 0:
        return MINIMUM_BILLABLE_HOURS
    rounded = math.ceil(duration_hours / ROUNDING_INCREMENT_HOURS) * ROUNDING_INCREMENT_HOURS
    return max(MINIMUM_BILLABLE_HOURS, rounded)


def compute_bill(duration_hours: float, price_per_hour: float) -> float:
    billed_hours = compute_billed_hours(duration_hours)
    return round(billed_hours * price_per_hour, 2)


def check_in(reservation: Reservation, at: datetime) -> Reservation:
    reservation.checked_in_at = at
    reservation.spot.occupied = True
    db.session.commit()
    return reservation


def check_out(reservation: Reservation, at: datetime, price_per_hour: float) -> Reservation:
    if reservation.checked_in_at is None:
        raise ValueError("Cannot check out a reservation that was never checked in")

    duration_hours = (at - reservation.checked_in_at).total_seconds() / 3600.0
    reservation.checked_out_at = at
    reservation.bill_amount = compute_bill(duration_hours, price_per_hour)
    reservation.status = "completed"
    reservation.spot.occupied = False
    db.session.commit()
    return reservation


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def peak_occupancy_hour(reservations):
    """Given an iterable of Reservation-like objects with checked_in_at and
    checked_out_at, return the hour-of-day (0-23) during which the most
    concurrent occupancy occurred, using a simple sweep over hourly buckets
    spanning each reservation's checked-in window.

    Returns None if no reservations have both checked_in_at and
    checked_out_at set.
    """
    from datetime import timedelta

    hour_counts = defaultdict(int)
    have_data = False
    for r in reservations:
        if r.checked_in_at is None or r.checked_out_at is None:
            continue
        have_data = True
        cursor = r.checked_in_at.replace(minute=0, second=0, microsecond=0)
        while cursor < r.checked_out_at:
            hour_counts[cursor.hour] += 1
            cursor += timedelta(hours=1)

    if not have_data or not hour_counts:
        return None

    peak_hour = max(hour_counts, key=lambda h: (hour_counts[h], -h))
    return peak_hour


def average_duration_per_spot_type(reservations_with_spot_type):
    """Given an iterable of (spot_type, checked_in_at, checked_out_at)
    tuples, return {spot_type: average_duration_hours}."""
    totals = defaultdict(float)
    counts = defaultdict(int)
    for spot_type, checked_in_at, checked_out_at in reservations_with_spot_type:
        if checked_in_at is None or checked_out_at is None:
            continue
        duration = (checked_out_at - checked_in_at).total_seconds() / 3600.0
        totals[spot_type] += duration
        counts[spot_type] += 1

    return {
        spot_type: round(totals[spot_type] / counts[spot_type], 4)
        for spot_type in totals
        if counts[spot_type] > 0
    }
