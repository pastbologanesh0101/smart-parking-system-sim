"""
Data models for the Smart Parking System.

SPOT_TYPES: standard, handicap, ev_charging
RESERVATION statuses: active, completed, cancelled
"""
from datetime import datetime

from .extensions import db

SPOT_TYPES = ("standard", "handicap", "ev_charging")
RESERVATION_STATUSES = ("active", "completed", "cancelled")


class Lot(db.Model):
    __tablename__ = "lots"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    total_spots = db.Column(db.Integer, nullable=False, default=0)

    spots = db.relationship("Spot", backref="lot", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "total_spots": self.total_spots}


class Spot(db.Model):
    __tablename__ = "spots"
    __table_args__ = (
        db.UniqueConstraint("lot_id", "spot_number", name="uq_lot_spot_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey("lots.id"), nullable=False)
    spot_number = db.Column(db.String(20), nullable=False)
    spot_type = db.Column(db.String(20), nullable=False, default="standard")
    occupied = db.Column(db.Boolean, nullable=False, default=False)

    reservations = db.relationship(
        "Reservation", backref="spot", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "lot_id": self.lot_id,
            "spot_number": self.spot_number,
            "spot_type": self.spot_type,
            "occupied": self.occupied,
        }


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey("spots.id"), nullable=False)
    license_plate = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")

    # Billing / check-in-out tracking (populated on check-in / check-out).
    checked_in_at = db.Column(db.DateTime, nullable=True)
    checked_out_at = db.Column(db.DateTime, nullable=True)
    bill_amount = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "spot_id": self.spot_id,
            "license_plate": self.license_plate,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "status": self.status,
            "checked_in_at": self.checked_in_at.isoformat() if self.checked_in_at else None,
            "checked_out_at": self.checked_out_at.isoformat() if self.checked_out_at else None,
            "bill_amount": self.bill_amount,
        }


class RatePlan(db.Model):
    __tablename__ = "rate_plans"

    id = db.Column(db.Integer, primary_key=True)
    spot_type = db.Column(db.String(20), nullable=False, unique=True)
    price_per_hour = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "spot_type": self.spot_type,
            "price_per_hour": self.price_per_hour,
        }
