import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.logging_config import LoggerNameFilter
from app.middleware import REQUEST_ID_HEADER

ACCESS_LOGGER = "app.request"


class ListHandler(logging.Handler):
    """Collects formatted records in memory."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def access_log(client: TestClient) -> Iterator[list[str]]:
    """Lines emitted by the request-logging middleware.

    Attached after `client` so it survives the `setup_logging()` call made
    during app startup. `app.request` is not named in the logging config, so
    handlers added directly to it are left in place.
    """
    handler = ListHandler()
    logger = logging.getLogger(ACCESS_LOGGER)
    logger.addHandler(handler)
    try:
        yield handler.lines
    finally:
        logger.removeHandler(handler)


def test_request_is_logged_with_status_and_duration(
    client: TestClient, api_prefix: str, access_log: list[str]
) -> None:
    client.get(f"{api_prefix}/health")

    assert access_log, "the middleware logged nothing"
    assert f"GET {api_prefix}/health -> 200" in access_log[-1]
    assert "ms" in access_log[-1]


def test_one_line_per_request(
    client: TestClient, api_prefix: str, access_log: list[str]
) -> None:
    for _ in range(3):
        client.get(f"{api_prefix}/health")

    assert len(access_log) == 3


def test_response_carries_a_request_id(client: TestClient, api_prefix: str) -> None:
    response = client.get(f"{api_prefix}/health")

    assert response.headers.get(REQUEST_ID_HEADER)


def test_inbound_request_id_is_reused(
    client: TestClient, api_prefix: str, access_log: list[str]
) -> None:
    response = client.get(f"{api_prefix}/health", headers={REQUEST_ID_HEADER: "caller-123"})

    assert response.headers[REQUEST_ID_HEADER] == "caller-123"
    assert "caller-123" in access_log[-1]


def test_client_error_logs_at_warning(
    client: TestClient, api_prefix: str, access_log: list[str]
) -> None:
    client.get(f"{api_prefix}/nope")

    assert access_log[-1].startswith("WARNING")
    assert "-> 404" in access_log[-1]


def test_uvicorn_access_log_is_silenced_by_default(client: TestClient) -> None:
    # It would otherwise duplicate every line the middleware emits.
    assert logging.getLogger("uvicorn.access").level == logging.WARNING


def test_uvicorn_error_logger_displays_as_uvicorn() -> None:
    """`uvicorn.error` carries INFO lifecycle lines, and reads like a failure."""
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Started server process [123]",
        args=(),
        exc_info=None,
    )

    assert LoggerNameFilter().filter(record) is True
    assert record.name == "uvicorn"


def test_other_logger_names_are_left_alone() -> None:
    record = logging.LogRecord(
        name="app.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="x",
        args=(),
        exc_info=None,
    )

    LoggerNameFilter().filter(record)

    assert record.name == "app.request"
