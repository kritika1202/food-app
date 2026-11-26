from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from app.main import app

def test_order_security_and_idempotency():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        item = client.get("/api/menu_items").json()[0]
        headers = {"Idempotency-Key": "test-order"}
        body = {"lines": [{"item_id": item["id"], "quantity": 1}]}
        response = client.post("/api/orders", auth=("maya", "demo1234"), headers=headers, json=body)
        assert response.status_code == 201
        order = response.json()
        assert client.post("/api/orders", auth=("maya", "demo1234"), headers=headers, json=body).json()["id"] == order["id"]
        assert client.get(f"/api/orders/{order['id']}", auth=("arjun", "demo1234")).status_code == 404
        assert client.post("/api/menu_items", auth=("maya", "demo1234"), json=item).status_code == 403
        assert client.post(f"/api/orders/{order['id']}/cancel", auth=("maya", "demo1234")).status_code == 200
        assert client.post(f"/api/orders/{order['id']}/cancel", auth=("maya", "demo1234")).status_code == 409

def test_failed_orders_do_not_change_stock():
    with TestClient(app) as client:
        items = client.get("/api/menu_items").json()
        first, second = items[0], items[1]
        auth = ("maya", "demo1234")
        response = client.post("/api/orders", auth=auth, headers={"Idempotency-Key": "insufficient-stock"}, json={"lines": [{"item_id": first["id"], "quantity": 1}, {"item_id": second["id"], "quantity": 10}, {"item_id": second["id"], "quantity": 1}]})
        assert response.status_code == 422
        assert client.get(f"/api/menu_items/{first['id']}").json()["capacity"] == first["capacity"]
        response = client.post("/api/orders", auth=auth, headers={"Idempotency-Key": "changed-price"}, json={"lines": [{"item_id": first["id"], "quantity": 1, "expected_unit_price": "0.01"}]})
        assert response.status_code == 409
        assert client.get(f"/api/menu_items/{first['id']}").json()["capacity"] == first["capacity"]
        updated_second = {key: second[key] for key in ("title", "category", "description", "vegetarian", "price", "capacity")}
        updated_second["capacity"] = 0
        assert client.put(f"/api/menu_items/{second['id']}", auth=("admin", "demo1234"), json=updated_second).status_code == 200
        response = client.post("/api/orders", auth=auth, headers={"Idempotency-Key": "rollback-stock"}, json={"lines": [{"item_id": first["id"], "quantity": 1}, {"item_id": second["id"], "quantity": 1}]})
        assert response.status_code == 409
        assert client.get(f"/api/menu_items/{first['id']}").json()["capacity"] == first["capacity"]

def test_idempotency_key_rejects_different_order():
    with TestClient(app) as client:
        item = client.get("/api/menu_items").json()[0]
        headers = {"Idempotency-Key": "different-order"}
        auth = ("maya", "demo1234")
        assert client.post("/api/orders", auth=auth, headers=headers, json={"lines": [{"item_id": item["id"], "quantity": 1}]}).status_code == 201
        assert client.post("/api/orders", auth=auth, headers=headers, json={"lines": [{"item_id": item["id"], "quantity": 2}]}).status_code == 409

def test_concurrent_last_portion():
    with TestClient(app) as client:
        item = client.post("/api/menu_items", auth=("admin", "demo1234"), json={"title": "Last portion", "category": "Special", "description": "", "vegetarian": True, "price": "50.00", "capacity": 1}).json()
        barrier = Barrier(2)
        def place(username):
            barrier.wait()
            return client.post("/api/orders", auth=(username, "demo1234"), headers={"Idempotency-Key": f"last-{username}"}, json={"lines": [{"item_id": item["id"], "quantity": 1}]}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(place, ["maya", "arjun"]))
        assert sorted(statuses) == [201, 409]
        assert client.get(f"/api/menu_items/{item['id']}").json()["capacity"] == 0