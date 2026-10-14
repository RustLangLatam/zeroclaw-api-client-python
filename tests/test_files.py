from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.files import FilesAPI

from .conftest import Gateway, body, reply


async def test_browses_shared_files_and_uploads_images(gateway: Gateway, client: Client) -> None:
    def browse(request: httpx.Request) -> httpx.Response:
        # An empty path is left out: the root.
        assert "path" not in request.url.params
        return reply({"path": "", "entries": [{"name": "x", "kind": "dir"}]})(request)

    def mkdir(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"path": "x"}
        return reply({"created": "x"})(request)

    def rmdir(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"path": "x"}
        return reply({"removed": "x"})(request)

    def upload(request: httpx.Request) -> httpx.Response:
        assert request.url.params["agent"] == "helper"
        assert request.headers["Content-Type"] == "application/octet-stream"
        assert request.content == b"\x89PNG"
        return reply({"path": "/w/webui_1.png", "marker": "[IMAGE:/w/webui_1.png]"})(request)

    gateway.on("GET", "/api/browse", browse)
    gateway.on("POST", "/api/browse/mkdir", mkdir)
    gateway.on("DELETE", "/api/browse/rmdir", rmdir)
    gateway.on("POST", "/api/upload", upload)

    files = FilesAPI(client)
    listing = await files.list()
    assert listing.entries[0].kind == "dir"
    assert listing.entries[0].size is None
    await files.make_dir("x")
    await files.remove_dir("x")
    uploaded = await files.upload_image("helper", b"\x89PNG")
    assert uploaded.marker == "[IMAGE:/w/webui_1.png]"
