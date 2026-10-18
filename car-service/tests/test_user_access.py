import pytest

from conftest import JPEG, PNG


def test_owner_is_taken_from_token(make_car):
    assert make_car("alice")["owner"] == "alice"


def test_owner_in_body_rejected(as_user):
    response = as_user(
        "alice",
        "POST",
        "/cars",
        json={"make": "Volvo", "model": "V70", "year": 2015, "mileage": 1, "owner": "bob"},
    )
    assert response.status_code == 422


def test_dealer_cannot_create_car(as_user):
    response = as_user("dealer", "POST", "/cars", json={"make": "A", "model": "B", "year": 2015, "mileage": 1})
    assert response.status_code == 403


def test_seller_lists_only_own_cars(as_user, make_car):
    alice_car = make_car("alice")
    make_car("bob")
    cars = as_user("alice", "GET", "/cars").json()
    assert [car["id"] for car in cars] == [alice_car["id"]]


def test_dealer_lists_all_cars(as_user, make_car):
    make_car("alice")
    make_car("bob")
    assert {car["owner"] for car in as_user("dealer", "GET", "/cars").json()} == {"alice", "bob"}


def test_filter_by_make_only_returns_own_cars(as_user, make_car):
    make_car("alice", make="Volvo")
    make_car("alice", make="Audi")
    make_car("bob", make="Volvo")
    cars = as_user("alice", "GET", "/cars", params={"make": "Volvo"}).json()
    assert [(car["owner"], car["make"]) for car in cars] == [("alice", "Volvo")]


@pytest.mark.parametrize("payload", ["' OR '1'='1", "Volvo' OR 1=1 --", "x\" OR \"\"=\""])
def test_sql_injection_in_make_filter_returns_no_foreign_cars(as_user, make_car, payload):
    make_car("bob")
    response = as_user("alice", "GET", "/cars", params={"make": payload})
    assert response.status_code == 200
    assert response.json() == []


def test_seller_reads_own_car(as_user, make_car):
    car = make_car("alice")
    assert as_user("alice", "GET", f"/cars/{car['id']}").status_code == 200


def test_seller_cannot_read_other_sellers_car(as_user, make_car):
    car = make_car("bob")
    assert as_user("alice", "GET", f"/cars/{car['id']}").status_code == 404


def test_dealer_reads_any_car(as_user, make_car):
    car = make_car("bob")
    assert as_user("dealer", "GET", f"/cars/{car['id']}").status_code == 200


def test_missing_car_and_foreign_car_look_the_same(as_user, make_car):
    car = make_car("bob")
    foreign = as_user("alice", "GET", f"/cars/{car['id']}")
    missing = as_user("alice", "GET", "/cars/9999")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_owner_uploads_and_reads_image(as_user, make_car):
    car = make_car("alice")
    upload = as_user(
        "alice", "POST", f"/cars/{car['id']}/images", content=PNG, headers={"Content-Type": "image/png"}
    )
    assert upload.status_code == 201
    image_id = upload.json()["id"]

    response = as_user("alice", "GET", f"/cars/{car['id']}/images/{image_id}")
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["Content-Type"] == "image/png"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert as_user("alice", "GET", f"/cars/{car['id']}").json()["images"] == [image_id]


def test_seller_cannot_upload_to_other_sellers_car(as_user, make_car):
    car = make_car("bob")
    response = as_user(
        "alice", "POST", f"/cars/{car['id']}/images", content=JPEG, headers={"Content-Type": "image/jpeg"}
    )
    assert response.status_code == 404


def test_dealer_cannot_upload_image(as_user, make_car):
    car = make_car("alice")
    response = as_user(
        "dealer", "POST", f"/cars/{car['id']}/images", content=JPEG, headers={"Content-Type": "image/jpeg"}
    )
    assert response.status_code == 403


def test_seller_cannot_read_other_sellers_image(as_user, make_car):
    car = make_car("bob")
    image_id = as_user(
        "bob", "POST", f"/cars/{car['id']}/images", content=PNG, headers={"Content-Type": "image/png"}
    ).json()["id"]
    assert as_user("alice", "GET", f"/cars/{car['id']}/images/{image_id}").status_code == 404


def test_image_cannot_be_read_through_another_car(as_user, make_car):
    bob_car = make_car("bob")
    alice_car = make_car("alice")
    image_id = as_user(
        "bob", "POST", f"/cars/{bob_car['id']}/images", content=PNG, headers={"Content-Type": "image/png"}
    ).json()["id"]
    assert as_user("alice", "GET", f"/cars/{alice_car['id']}/images/{image_id}").status_code == 404


@pytest.mark.parametrize("image_id", ["..%2F..%2Fetc%2Fpasswd", "%2E%2E", "%2E%2E%2Fcar.db", "abc"])
def test_image_id_must_be_server_generated_format(as_user, make_car, image_id):
    car = make_car("alice")
    response = as_user("alice", "GET", f"/cars/{car['id']}/images/{image_id}")
    assert response.status_code in (404, 422)


def test_image_with_wrong_type_rejected(as_user, make_car):
    car = make_car("alice")
    response = as_user(
        "alice", "POST", f"/cars/{car['id']}/images", content=b"<svg/>", headers={"Content-Type": "image/svg+xml"}
    )
    assert response.status_code == 415


def test_image_content_must_match_type(as_user, make_car):
    car = make_car("alice")
    response = as_user(
        "alice", "POST", f"/cars/{car['id']}/images", content=JPEG, headers={"Content-Type": "image/png"}
    )
    assert response.status_code == 415


def test_oversized_image_rejected(as_user, make_car):
    car = make_car("alice")
    response = as_user(
        "alice",
        "POST",
        f"/cars/{car['id']}/images",
        content=PNG + b"\x00" * (2 * 1024 * 1024),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 413


def test_dealer_creates_valuation_with_dealer_from_token(as_user, make_car):
    car = make_car("alice")
    response = as_user("dealer", "POST", f"/cars/{car['id']}/valuations", json={"price": 85000, "comment": "Fine"})
    assert response.status_code == 201
    assert response.json()["dealer"] == "dealer"


def test_dealer_in_valuation_body_rejected(as_user, make_car):
    car = make_car("alice")
    response = as_user(
        "dealer", "POST", f"/cars/{car['id']}/valuations", json={"price": 1, "dealer": "someone-else"}
    )
    assert response.status_code == 422


def test_seller_cannot_create_valuation(as_user, make_car):
    car = make_car("alice")
    response = as_user("alice", "POST", f"/cars/{car['id']}/valuations", json={"price": 1})
    assert response.status_code == 403


def test_seller_reads_valuations_of_own_car_only(as_user, make_car):
    car = make_car("alice")
    as_user("dealer", "POST", f"/cars/{car['id']}/valuations", json={"price": 85000})
    assert len(as_user("alice", "GET", f"/cars/{car['id']}/valuations").json()) == 1
    assert as_user("bob", "GET", f"/cars/{car['id']}/valuations").status_code == 404


def test_seller_cannot_create_report_directly(as_user, make_car, service_token, client):
    car = make_car("alice")
    token = service_token("alice", scope="reports:create")
    response = client.post(
        f"/cars/{car['id']}/reports", json={"content": "fake"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_dealer_cannot_read_reports(as_user, make_car, service_token, client):
    car = make_car("alice")
    token = service_token("dealer", scope="reports:read")
    response = client.get(f"/cars/{car['id']}/reports", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_no_update_or_delete_endpoints(as_user, make_car):
    car = make_car("alice")
    for method in ("PUT", "PATCH", "DELETE"):
        assert as_user("alice", method, f"/cars/{car['id']}").status_code == 405
