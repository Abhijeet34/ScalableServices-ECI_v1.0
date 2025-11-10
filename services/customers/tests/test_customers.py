from fastapi.testclient import TestClient
from app.main import app

def test_list_customers_empty():
    client = TestClient(app)
    resp = client.get('/customers/')
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
