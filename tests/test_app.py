import pytest
from datetime import date
from app import create_app
from models import db


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "GEMINI_API_KEY": "",
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as c:
        yield c


def register(c, email="a@x.com"):
    return c.post("/register", data={"email": email, "password": "password123", "full_name": "A"},
                  follow_redirects=True)


def seed(c):
    register(c)
    c.post("/income", data={"source": "Job", "amount": "50000"})
    c.post("/expenses", data={"category_id": 1, "amount": "12000", "description": "rent"})
    c.post("/expenses", data={"category_id": 2, "amount": "6000"})


# --- Authentication ---
def test_protected_route_redirects(client):
    assert client.get("/dashboard").status_code == 302


def test_register_login_logout(client):
    assert b"Hi" in register(client).data
    client.post("/logout")
    assert client.get("/dashboard").status_code == 302
    r = client.post("/login", data={"email": "a@x.com", "password": "password123"}, follow_redirects=True)
    assert b"Dashboard" in r.data


def test_bad_login_and_weak_password(client):
    assert b"Invalid" in client.post("/login", data={"email": "n@x.com", "password": "x"}).data
    r = client.post("/register", data={"email": "b@x.com", "password": "short"})
    assert b"at least 8" in r.data


# --- Income / expenses ---
def test_income_and_expense_validation(client):
    register(client)
    r = client.post("/income", data={"source": "J", "amount": "-5"}, follow_redirects=True)
    assert b"greater than 0" in r.data
    client.post("/income", data={"source": "Job", "amount": "1000"})
    assert b"1,000.00" in client.get("/income").data


def test_dashboard_summary_and_api(client):
    seed(client)
    d = client.get("/api/dashboard-data").get_json()["summary"]
    assert d["income"] == 50000 and d["expenses"] == 18000 and d["savings"] == 32000
    assert d["health_score"] > 0


# --- Budget + AI fallback ---
def test_budget_generation_rule_based(client):
    seed(client)
    client.post("/budget/generate")
    d = client.get("/api/dashboard-data").get_json()["summary"]
    total = sum(c["limit"] or 0 for c in d["categories"])
    assert 0 < total <= 50000 * 0.8 + 1  # respects the 20% savings goal


def test_ai_insights_endpoint(client):
    seed(client)
    j = client.post("/api/insights", json={"kind": "analysis"}).get_json()
    assert j["text"] and j["source"] == "rule"
    assert client.post("/api/insights", json={"kind": "bogus"}).status_code == 400


# --- Reports, savings ---
def test_monthly_report(client):
    seed(client)
    r = client.post("/reports/generate", follow_redirects=True)
    assert b"Next month goal" in r.data and b"Report" in r.data


def test_savings_goal_progress(client):
    register(client)
    client.post("/savings", data={"name": "Fund", "target": "1000"})
    client.post("/savings/1/add", data={"amount": "250"})
    assert b"25.0%" in client.get("/savings").data


# --- Security: data isolation ---
def test_users_cannot_touch_others_data(client):
    seed(client)
    client.post("/logout")
    register(client, "b@x.com")
    assert client.post("/expenses/1/delete").status_code == 404
    assert client.get("/api/dashboard-data").get_json()["summary"]["income"] == 0
