"""LocalDiskBackend — a StorageBackend implementation over the local filesystem.

genblaze ships no local/filesystem sink (verified: genblaze_core/storage/ has
only base.py + sink.py + transfer.py + helpers; genblaze_core/sinks/ has only
base.py + parquet.py). So rather than run sink-less — which would skip manifest
persistence entirely and leave asset URLs as unreachable file:// temp paths —
we implement the 6-method StorageBackend ABC and feed it to the *stock*
ObjectStorageSink.

That choice is deliberate: implementing BaseSink directly would be fewer lines
but would mean reimplementing asset download, SHA-256 hashing, key building and
manifest hash recomputation — i.e. everything in AssetTransfer that makes
Manifest.verify() pass. Going one layer lower reuses all of it, and makes the
switch to Backblaze B2 a single branch in factory.py.

The load-bearing method is get_durable_url(): it returns an /api/media/{key}
URL that the browser can actually load. AssetTransfer assigns that back onto
asset.url after upload (transfer.py:408), so it lands in the manifest and flows
through to AttemptContent.imageUrl with no frontend change. Asset.url has no
scheme validator, so a relative-to-host http URL is accepted.
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any
from urllib.parse import quote, unquote

from genblaze_core.storage.base import StorageBackend
from genblaze_core.storage.errors import StorageError
from genblaze_core.storage.types import FileEntry, ListPage


class LocalDiskBackend(StorageBackend):
    """Filesystem-backed object storage for local development and demos."""

    def __init__(self, root: Path | str, media_base_url: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._base = media_base_url.rstrip("/")

    # NOTE: deliberately no `public_url_base` attribute. ObjectStorageSink's
    # URLPolicy.AUTO check only warns for backends that declare one.

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        if not p.is_relative_to(self._root):
            raise StorageError(f"Key escapes storage root: {key!r}")
        return p

    # ---- required abstract methods -------------------------------------
    def put(
        self,
        key: str,
        data: bytes | IO[bytes],
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        extra_args: dict[str, Any] | None = None,
    ) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            p.write_bytes(data)
        else:
            with p.open("wb") as fh:
                shutil.copyfileobj(data, fh)
        if content_type:
            # Sidecar so GET /api/media can serve the right Content-Type
            # without re-sniffing. Kept out of the key namespace by suffix.
            p.with_name(p.name + ".ctype").write_text(content_type, encoding="utf-8")
        return key  # contract: return the KEY, not a URL

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"No such object: {key}") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        p = self._path(key)
        p.unlink(missing_ok=True)
        p.with_name(p.name + ".ctype").unlink(missing_ok=True)

    def get_url(self, key: str, *, expires_in: int = 3600) -> str:
        return self.get_durable_url(key)

    def get_durable_url(self, key: str) -> str:
        return f"{self._base}/{quote(key)}"

    # ---- useful overrides ----------------------------------------------
    def key_from_url(self, url: str) -> str | None:
        prefix = self._base + "/"
        if url.startswith(prefix):
            return unquote(url[len(prefix) :])
        return None

    def list(
        self,
        prefix: str = "",
        *,
        max_keys: int = 1000,
        continuation_token: str | None = None,
    ) -> ListPage:
        """Walk the tree under `prefix`. Backs the Library index-rebuild path.

        Single page: a local demo bucket never approaches max_keys, so
        next_token is always None.
        """
        entries: list[FileEntry] = []
        walk_root = self._root
        if prefix:
            candidate = self._path(prefix)
            walk_root = candidate if candidate.is_dir() else candidate.parent
        if not walk_root.is_dir():
            return ListPage(entries=(), next_token=None)

        for dirpath, _dirnames, filenames in os.walk(walk_root):
            for fn in sorted(filenames):
                if fn.endswith(".ctype"):
                    continue
                full = Path(dirpath) / fn
                key = str(full.relative_to(self._root))
                if prefix and not key.startswith(prefix):
                    continue
                st = full.stat()
                entries.append(
                    FileEntry(
                        key=key,
                        size=st.st_size,
                        last_modified=datetime.fromtimestamp(st.st_mtime, tz=UTC),
                        etag=f"{int(st.st_mtime)}-{st.st_size}",
                    )
                )
                if len(entries) >= max_keys:
                    return ListPage(entries=tuple(entries), next_token=None)
        return ListPage(entries=tuple(entries), next_token=None)

    def content_type_for(self, key: str) -> str | None:
        """Non-ABC helper used by GET /api/media."""
        side = self._path(key).with_name(self._path(key).name + ".ctype")
        if side.is_file():
            return side.read_text(encoding="utf-8").strip()
        return None
