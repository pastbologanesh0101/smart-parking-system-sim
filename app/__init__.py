"""
Smart Parking System - Flask app factory.

IMPORTANT HONESTY NOTE: the "sensors" in this project are simulated in
software (see app/sensors.py). There is no real hardware anywhere in this
codebase. Everything else -- the Flask backend, the SQLite-backed data
model, availability queries, reservation overlap checking, check-in /
check-out billing, and analytics -- is fully real and runs against a real
database.
"""
import os

from flask import Flask

from .extensions import db


def create_app(testing: bool = False, db_path: str | None = None) -> Flask:
    app = Flask(__name__)

    if testing:
        # In-memory SQLite for fast, isolated unit tests.
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True
    else:
        instance_dir = os.path.join(app.root_path, "..", "instance")
        os.makedirs(instance_dir, exist_ok=True)
        default_path = os.path.join(instance_dir, "parking.db")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path or default_path}"

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    from . import models  # noqa: F401  (register models on the metadata)
    from .routes import api_bp

    app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()

    @app.get("/")
    def index():
        return {
            "service": "Smart Parking System",
            "note": "Occupancy sensors are simulated in software. Backend, "
            "reservations, and billing are real.",
            "docs": "See README.md for the full API reference.",
        }

    return app
