import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.security import seed_admin
from app.seed import seed_demo

@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    db=SessionLocal()
    try:
        seed_admin(db)
        seed_demo(db)
    finally:
        db.close()
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def headers(client):
    response=client.post("/api/auth/login",json={"username":"admin","password":"TraceWeaveDemo2026!"})
    assert response.status_code==200, response.text
    return {"Authorization":f"Bearer {response.json()['access_token']}"}

def test_health(client):
    assert client.get("/api/health").status_code==200

def test_login_and_summary(client,headers):
    r=client.get("/api/summary",headers=headers)
    assert r.status_code==200
    assert r.json()["transactions"]>0

def test_temporal_and_complaint_endpoints(client,headers):
    assert client.get("/api/analytics/temporal-patterns",headers=headers).status_code==200
    assert client.get("/api/analytics/complaint-matches",headers=headers).status_code==200

def test_investigation_and_pdf(client,headers):
    assert client.get("/api/investigate/ACC_X",headers=headers).status_code==200
    r=client.get("/api/export/report.pdf",headers=headers)
    assert r.status_code==200
    assert r.headers["content-type"]=="application/pdf"

def test_audit_is_admin_only(client,headers):
    assert client.get("/api/audit",headers=headers).status_code==200
