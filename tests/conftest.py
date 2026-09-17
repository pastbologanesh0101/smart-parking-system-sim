import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    app = create_app(testing=True)
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def seed_lot(client, name="Downtown Garage", total_spots=3):
    resp = client.post("/api/lots", json={"name": name, "total_spots": total_spots})
    return resp.get_json()


def seed_spot(client, lot_id, spot_number, spot_type="standard"):
    resp = client.post(
        f"/api/lots/{lot_id}/spots",
        json={"spot_number": spot_number, "spot_type": spot_type},
    )
    return resp.get_json()


def seed_rate_plan(client, spot_type, price_per_hour):
    resp = client.post(
        "/api/rate-plans",
        json={"spot_type": spot_type, "price_per_hour": price_per_hour},
    )
    return resp.get_json()
