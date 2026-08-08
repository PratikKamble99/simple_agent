from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient, api_prefix: str) -> None:
    response = client.get(f"{api_prefix}/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {
        "status",
        "app",
        "version",
        "environment",
        "database",
        "vector_store",
    }


def test_unknown_route_returns_404(client: TestClient, api_prefix: str) -> None:
    response = client.get(f"{api_prefix}/does-not-exist")

    assert response.status_code == 404


def test_openapi_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
