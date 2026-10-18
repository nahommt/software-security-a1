import os
import struct
import uuid
import zlib

from app.config import Settings
from app.db import CarStore

SEED_NAMESPACE = uuid.UUID("5b0f6c8e-3a52-4c1e-9d7a-2f4e8c1b6a90")
SEED_TIMESTAMP = "2026-01-15T12:00:00+00:00"

SEED_CARS = [
    {
        "owner": "alice",
        "car": {
            "make": "Volvo",
            "model": "V70",
            "year": 2015,
            "mileage": 120000,
            "description": "Synthetic seed car for alice.",
        },
        "color": (200, 30, 30),
        "valuation": {"price": 85000, "comment": "Synthetic valuation for alice's car."},
    },
    {
        "owner": "bob",
        "car": {
            "make": "Audi",
            "model": "A4",
            "year": 2018,
            "mileage": 90000,
            "description": "Synthetic seed car for bob.",
        },
        "color": (30, 30, 200),
        "valuation": {"price": 140000, "comment": "Synthetic valuation for bob's car."},
    },
]
SEED_DEALER = "dealer"


def _chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def solid_png(color, size=8):
    row = b"\x00" + bytes(color) * size
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(row * size, 9))
        + _chunk(b"IEND", b"")
    )


def seed(settings):
    store = CarStore(settings.db_path)
    store.init_schema()
    store.reset()

    os.makedirs(settings.images_dir, exist_ok=True)
    for name in os.listdir(settings.images_dir):
        os.remove(os.path.join(settings.images_dir, name))

    for entry in SEED_CARS:
        car = store.create_car(owner=entry["owner"], **entry["car"])
        image_id = uuid.uuid5(SEED_NAMESPACE, f"{entry['owner']}-car-image").hex
        with open(os.path.join(settings.images_dir, image_id), "wb") as f:
            f.write(solid_png(entry["color"]))
        store.add_image(image_id, car["id"], "image/png")
        store.create_valuation(
            car["id"],
            SEED_DEALER,
            entry["valuation"]["price"],
            entry["valuation"]["comment"],
            timestamp=SEED_TIMESTAMP,
        )
        print(f"seeded car {car['id']} for {entry['owner']} with image {image_id} and one valuation")


def main():
    seed(Settings.from_env())


if __name__ == "__main__":
    main()
