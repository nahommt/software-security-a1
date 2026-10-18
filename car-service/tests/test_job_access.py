from conftest import auth


def _report(client, token, car_id, content="Report"):
    return client.post(f"/cars/{car_id}/reports", json={"content": content}, headers=auth(token))


def test_job_reads_its_car_and_valuations_and_stores_report(client, as_user, make_car, job_token):
    car = make_car("alice")
    as_user("dealer", "POST", f"/cars/{car['id']}/valuations", json={"price": 85000})
    token = job_token("alice", car["id"], job_id="job-1")

    assert client.get(f"/cars/{car['id']}", headers=auth(token)).status_code == 200
    assert len(client.get(f"/cars/{car['id']}/valuations", headers=auth(token)).json()) == 1

    response = _report(client, token, car["id"])
    assert response.status_code == 201
    assert response.json()["job_id"] == "job-1"

    report_id = response.json()["id"]
    assert as_user("alice", "GET", f"/reports/{report_id}").status_code == 200
    assert as_user("bob", "GET", f"/reports/{report_id}").status_code == 404
    assert [r["id"] for r in as_user("alice", "GET", f"/cars/{car['id']}/reports").json()] == [report_id]


def test_job_cannot_read_car_outside_job(client, make_car, job_token):
    job_car = make_car("alice")
    other_car = make_car("alice")
    token = job_token("alice", job_car["id"])
    assert client.get(f"/cars/{other_car['id']}", headers=auth(token)).status_code == 404
    assert client.get(f"/cars/{other_car['id']}/valuations", headers=auth(token)).status_code == 404
    assert _report(client, token, other_car["id"]).status_code == 404


def test_job_bound_to_car_not_owned_by_subject_denied(client, make_car, job_token):
    bob_car = make_car("bob")
    token = job_token("alice", bob_car["id"])
    assert client.get(f"/cars/{bob_car['id']}", headers=auth(token)).status_code == 404
    assert _report(client, token, bob_car["id"]).status_code == 404


def test_job_cannot_list_cars(client, make_car, job_token):
    car = make_car("alice")
    assert client.get("/cars", headers=auth(job_token("alice", car["id"]))).status_code == 403


def test_job_cannot_create_car_or_valuation(client, make_car, job_token):
    car = make_car("alice")
    token = job_token("alice", car["id"], scope="cars:create valuations:create")
    body = {"make": "A", "model": "B", "year": 2015, "mileage": 1}
    assert client.post("/cars", json=body, headers=auth(token)).status_code == 403
    assert client.post(f"/cars/{car['id']}/valuations", json={"price": 1}, headers=auth(token)).status_code == 403


def test_job_cannot_read_reports(client, make_car, job_token):
    car = make_car("alice")
    token = job_token("alice", car["id"], scope="reports:read")
    assert client.get(f"/cars/{car['id']}/reports", headers=auth(token)).status_code == 403


def test_job_without_scope_denied(client, make_car, job_token):
    car = make_car("alice")
    token = job_token("alice", car["id"], scope="cars:read")
    assert _report(client, token, car["id"]).status_code == 403


def test_one_report_per_job(client, make_car, job_token):
    car = make_car("alice")
    token = job_token("alice", car["id"], job_id="job-2")
    assert _report(client, token, car["id"]).status_code == 201
    assert _report(client, token, car["id"]).status_code == 409
