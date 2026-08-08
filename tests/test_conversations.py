from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message


def test_health_reports_database_ok(db_client: TestClient, api_prefix: str) -> None:
    response = db_client.get(f"{api_prefix}/health")

    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_create_conversation(db_client: TestClient, api_prefix: str) -> None:
    response = db_client.post(f"{api_prefix}/conversations", json={"title": "first"})

    assert response.status_code == 201

    body = response.json()
    assert body["title"] == "first"
    assert body["id"]
    assert body["created_at"]


def test_conversation_round_trip(db_client: TestClient, api_prefix: str) -> None:
    created = db_client.post(f"{api_prefix}/conversations", json={"title": "chat"}).json()
    cid = created["id"]

    added = db_client.post(
        f"{api_prefix}/conversations/{cid}/messages",
        json={"role": "user", "content": "hello"},
    )
    assert added.status_code == 201
    assert added.json()["role"] == "user"

    listed = db_client.get(f"{api_prefix}/conversations/{cid}/messages")
    assert listed.status_code == 200
    assert [m["content"] for m in listed.json()] == ["hello"]

    detail = db_client.get(f"{api_prefix}/conversations/{cid}")
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 1


def test_unknown_conversation_returns_404(db_client: TestClient, api_prefix: str) -> None:
    response = db_client.get(f"{api_prefix}/conversations/{uuid4()}")

    assert response.status_code == 404


def test_message_role_is_validated(db_client: TestClient, api_prefix: str) -> None:
    created = db_client.post(f"{api_prefix}/conversations", json={"title": "chat"}).json()

    response = db_client.post(
        f"{api_prefix}/conversations/{created['id']}/messages",
        json={"role": "wizard", "content": "hi"},
    )

    assert response.status_code == 422


async def test_deleting_a_conversation_cascades_to_messages(
    db_client: TestClient, api_prefix: str, db_session: AsyncSession
) -> None:
    created = db_client.post(f"{api_prefix}/conversations", json={"title": "chat"}).json()
    cid = created["id"]
    db_client.post(
        f"{api_prefix}/conversations/{cid}/messages",
        json={"role": "user", "content": "hello"},
    )

    assert db_client.delete(f"{api_prefix}/conversations/{cid}").status_code == 204

    remaining = await db_session.execute(select(func.count()).select_from(Message))
    assert remaining.scalar_one() == 0
