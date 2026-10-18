import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import seed
from conftest import auth


@pytest.fixture
def seeded(keys, tmp_path):
    settings = Settings(
        public_key_file=keys["public_path"],
        db_path=str(tmp_path / "car.db"),
        images_dir=str(tmp_path / "images"),
    )
    seed(settings)
    return settings


@pytest.fixture
def seeded_client(seeded):
    return TestClient(create_app(seeded))


def _dump(settings):
    conn = sqlite3.connect(settings.db_path)
    tables = ("cars", "images", "valuations", "reports")
    return {table: conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}


def _get(client, token, path):
    return client.get(path, headers=auth(token))


def test_each_seller_has_one_car_with_image_and_valuation(seeded_client, service_token):
    for owner in ("alice", "bob"):
        cars = _get(seeded_client, service_token(owner), "/cars").json()
        assert len(cars) == 1
        assert cars[0]["owner"] == owner
        assert len(cars[0]["images"]) == 1

        car_id = cars[0]["id"]
        valuations = _get(seeded_client, service_token(owner), f"/cars/{car_id}/valuations").json()
        assert [v["dealer"] for v in valuations] == ["dealer"]

        image = _get(seeded_client, service_token(owner), f"/cars/{car_id}/images/{cars[0]['images'][0]}")
        assert image.status_code == 200
        assert image.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_alice_cannot_reach_bobs_seeded_data(seeded_client, service_token):
    bob_car = _get(seeded_client, service_token("bob"), "/cars").json()[0]
    alice = service_token("alice")
    assert _get(seeded_client, alice, f"/cars/{bob_car['id']}").status_code == 404
    assert _get(seeded_client, alice, f"/cars/{bob_car['id']}/valuations").status_code == 404
    assert _get(seeded_client, alice, f"/cars/{bob_car['id']}/images/{bob_car['images'][0]}").status_code == 404


def test_dealer_sees_both_seeded_cars(seeded_client, service_token):
    cars = _get(seeded_client, service_token("dealer"), "/cars").json()
    assert {car["owner"] for car in cars} == {"alice", "bob"}


def test_seed_is_deterministic(seeded):
    first = _dump(seeded)
    images = sorted(p.name for p in Path(seeded.images_dir).iterdir())
    seed(seeded)
    assert _dump(seeded) == first
    assert sorted(p.name for p in Path(seeded.images_dir).iterdir()) == images


def test_seed_resets_existing_data(seeded, seeded_client, service_token):
    body = {"make": "Extra", "model": "X", "year": 2020, "mileage": 1}
    assert seeded_client.post("/cars", json=body, headers=auth(service_token("alice"))).status_code == 201
    seed(seeded)
    assert len(_dump(seeded)["cars"]) == 2
