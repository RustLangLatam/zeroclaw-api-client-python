from __future__ import annotations

import pytest

from zeroclaw_client import Client, InvalidURLError

from .conftest import TOKEN, Gateway


@pytest.mark.parametrize(
    ("segments", "path"),
    [
        (["api", "cron"], "/api/cron"),
        (["api", "cron", "a/b?c d"], "/api/cron/a%2Fb%3Fc%20d"),
        (["api", "memory", "key#1%"], "/api/memory/key%231%25"),
        (["api", "x", "a:b@c"], "/api/x/a:b@c"),
        (["api", "x", "ñ"], "/api/x/%C3%B1"),
    ],
)
def test_url_vectors(segments: list[str], path: str) -> None:
    assert Client("http://gw:1")._url(segments) == "http://gw:1" + path


@pytest.mark.parametrize(
    ("base", "want"),
    [
        ("http://127.0.0.1:42617", "http://127.0.0.1:42617"),
        ("http://127.0.0.1:42617/", "http://127.0.0.1:42617"),
        ("https://gw.example/zeroclaw/", "https://gw.example/zeroclaw"),
        ("https://gw.example/zeroclaw?x=1#f", "https://gw.example/zeroclaw"),
    ],
)
def test_base_url_vectors(base: str, want: str) -> None:
    assert Client(base).base_url == want


@pytest.mark.parametrize(
    "base", ["", "gateway", "127.0.0.1:42617", "ftp://gw", "http://", "/api", "http:///x"]
)
def test_invalid_base_urls_are_refused(base: str) -> None:
    with pytest.raises(InvalidURLError):
        Client(base)


def test_segments_are_encoded_under_the_base_path() -> None:
    client = Client("https://gw.example/zero claw/")
    assert client._url(["api", "a b"]) == "https://gw.example/zero claw/api/a%20b"


def test_formatting_hides_the_token() -> None:
    client = Client("http://gw:1", token=TOKEN)
    for text in (repr(client), str(client), f"{client!r}"):
        assert TOKEN not in text
    assert "authenticated=True" in repr(client)


async def test_unset_parameters_are_left_out(gateway: Gateway, client: Client) -> None:
    gateway.on("GET", "/api/cron/j1/runs", {"runs": []})
    await client.cron.runs("j1")
    assert gateway.requests[-1].url.query == b""


async def test_with_token_keeps_the_gateway(gateway: Gateway, client: Client) -> None:
    gateway.on("GET", "/api/cron", {"jobs": []}, public=True)
    other = client.with_token("zc_other")
    assert other.base_url == client.base_url
    await other.cron.list()
    assert gateway.requests[-1].headers["Authorization"] == "Bearer zc_other"
    await client.with_token(None).cron.list()
    assert "Authorization" not in gateway.requests[-1].headers
    assert repr(client.with_token(None)).endswith("authenticated=False)")


async def test_requests_identify_the_client(gateway: Gateway, client: Client) -> None:
    gateway.on("GET", "/api/cron", {"jobs": []})
    await client.cron.list()
    assert gateway.requests[-1].headers["User-Agent"].startswith("zeroclaw-api-client-python/")
