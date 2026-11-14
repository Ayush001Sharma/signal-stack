def test_create_company_and_validation(client):
    r = client.post("/api/companies", json={"name": "Acme", "website": "https://acme.example", "industry": "EdTech", "run_setup": False})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["domain"] == "acme.example" and body["status"] == "created"
    # schedule row created automatically
    s = client.get(f"/api/companies/{body['id']}/schedule").json()
    assert s["weekly_day_of_week"] == "mon" and s["timezone"]
    # duplicate domain rejected
    assert client.post("/api/companies", json={"name": "Acme 2", "website": "https://www.acme.example/", "run_setup": False}).status_code == 409
    # invalid url / short name rejected
    assert client.post("/api/companies", json={"name": "A", "website": "not a url", "run_setup": False}).status_code == 422
    assert client.get("/api/companies/999").status_code == 404
    assert [c["name"] for c in client.get("/api/companies").json()] == ["Acme"]


def test_update_and_delete_company(client):
    cid = client.post("/api/companies", json={"name": "Acme", "website": "https://acme.example", "run_setup": False}).json()["id"]
    r = client.patch(f"/api/companies/{cid}", json={"business_context": "B2B payroll for clinics"})
    assert r.json()["business_context"] == "B2B payroll for clinics" and r.json()["profile_version"] == 2
    assert client.delete(f"/api/companies/{cid}").status_code == 204
    assert client.get(f"/api/companies/{cid}").status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json()["database"] is True
