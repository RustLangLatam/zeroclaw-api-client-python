"""The shared directory (``<install>/shared/``) and image uploads.

Gateway handlers: ``crates/zeroclaw-gateway/src/api_browse.rs`` and
``api_upload.rs``. Per-agent workspaces are in :class:`AgentAPI`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["FileContent", "FileEntry", "FileListing", "FilesAPI", "Upload"]


class FileEntry(Model):
    """A directory entry."""

    #: The entry's name.
    name: str
    #: ``dir`` or ``file``.
    kind: str
    #: The size of a file.
    size: int | None = None
    #: Whether it may not be changed.
    protected: bool = False


class FileListing(Model):
    """A directory's entries."""

    #: The directory.
    path: str
    #: The directories first, then the files, alphabetically.
    entries: list[FileEntry]


class FileContent(Model):
    """A file's content."""

    #: The file.
    path: str
    #: Its size in bytes.
    size: int
    #: Whether it is text.
    is_text: bool
    #: The content, in ``encoding``.
    content: str
    #: ``utf8`` or ``base64``.
    encoding: str


class Upload(Model):
    """A stored upload."""

    #: Where it was stored.
    path: str
    #: ``[IMAGE:<path>]``, to put in a message.
    marker: str


class FilesAPI:
    """The shared-directory and upload endpoints, from :attr:`Client.files`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def list(self, path: str | None = None) -> FileListing:
        """Return a shared-area directory, its root when ``path`` is empty (GET /api/browse)."""
        return await self._c._call(
            "GET", ["api", "browse"], FileListing, query={"path": path or None}
        )

    async def make_dir(self, path: str) -> None:
        """Create a directory (POST /api/browse/mkdir)."""
        await self._c._request("POST", ["api", "browse", "mkdir"], json_body={"path": path})

    async def remove_dir(self, path: str) -> None:
        """Remove a directory and its contents (DELETE /api/browse/rmdir)."""
        await self._c._request("DELETE", ["api", "browse", "rmdir"], json_body={"path": path})

    async def upload_image(self, agent: str, image: bytes) -> Upload:
        """Store an image in ``agent``'s workspace (POST /api/upload).

        PNG, JPEG, GIF or WebP, told by its bytes. Returns the marker that
        attaches it to a chat message.
        """
        return await self._c._call(
            "POST",
            ["api", "upload"],
            Upload,
            query={"agent": agent or None},
            content=image,
            headers={"Content-Type": "application/octet-stream"},
        )
