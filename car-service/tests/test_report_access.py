from conftest import auth


def _make_report(client, make_car, job_token, owner):
    car = make_car(owner)
    token = job_token(owner, car["id"], job_id=f"job-{owner}")
    response = client.post(f"/cars/{car['id']}/reports", json={"content": "Report body"}, headers=auth(token))
    assert response.status_code == 201
    return car, response.json()["id"]


def test_seller_reads_own_report(as_user, make_car, client, job_token):
    car, report_id = _make_report(client, make_car, job_token, "alice")
    response = as_user("alice", "GET", f"/reports/{report_id}")
    assert response.status_code == 200
    assert response.json()["car_id"] == car["id"]


def test_seller_cannot_read_other_sellers_report(as_user, make_car, client, job_token):
    _, report_id = _make_report(client, make_car, job_token, "bob")
    assert as_user("alice", "GET", f"/reports/{report_id}").status_code == 404


def test_missing_report_and_foreign_report_look_the_same(as_user, make_car, client, job_token):
    _, report_id = _make_report(client, make_car, job_token, "bob")
    foreign = as_user("alice", "GET", f"/reports/{report_id}")
    missing = as_user("alice", "GET", "/reports/9999")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_seller_cannot_list_other_sellers_reports(as_user, make_car, client, job_token):
    bob_car, _ = _make_report(client, make_car, job_token, "bob")
    assert as_user("alice", "GET", f"/cars/{bob_car['id']}/reports").status_code == 404
