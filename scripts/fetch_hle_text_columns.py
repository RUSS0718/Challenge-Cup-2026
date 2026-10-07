"""Fetch HLE text columns from ModelScope mirror via HTTP range requests.

Avoids downloading the 274MB full parquet (images included). Reads only the
text columns needed to build a math subset: id, question, answer, answer_type,
author_name, rationale, raw_subject, category.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request

import pyarrow.parquet as pq

URL = (
    "https://modelscope.cn/api/v1/datasets/AI-ModelScope/hle/repo"
    "?Revision=master&FilePath=data/test-00000-of-00001.parquet"
)
TEXT_COLUMNS = [
    "id", "question", "answer", "answer_type", "author_name",
    "rationale", "raw_subject", "category",
]


class HttpRangeFile(io.RawIOBase):
    """Minimal seekable read-only file over HTTP Range requests."""

    def __init__(self, url: str, block_size: int = 1 << 20) -> None:
        self.url = url
        self.block_size = block_size
        self._pos = 0
        self._cache_start = 0
        self._cache = b""
        self._size = self._fetch_size()

    def _fetch(self, start: int, end: int) -> bytes:
        req = urllib.request.Request(
            self.url, headers={"User-Agent": "Mozilla/5.0", "Range": f"bytes={start}-{end}"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()

    def _fetch_size(self) -> int:
        req = urllib.request.Request(
            self.url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_range = resp.headers.get("Content-Range", "")
        # Content-Range: bytes 0-0/123456
        return int(content_range.split("/")[-1])

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self._size - self._pos
        if size == 0 or self._pos >= self._size:
            return b""
        start = self._pos
        end = min(self._pos + size, self._size) - 1
        if not (self._cache_start <= start and end < self._cache_start + len(self._cache)):
            fetch_end = min(start + max(size, self.block_size), self._size) - 1
            self._cache = self._fetch(start, fetch_end)
            self._cache_start = start
        offset = start - self._cache_start
        chunk = self._cache[offset:offset + size]
        self._pos += len(chunk)
        return chunk

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            self._pos = self._size + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True


def main() -> None:
    out_path = "hle_text_columns.jsonl"
    f = HttpRangeFile(URL)
    print(f"parquet size: {f._size/1e6:.1f} MB", flush=True)
    pf = pq.ParquetFile(f)
    md = pf.metadata
    print(f"rows={md.num_rows} row_groups={md.num_row_groups}", flush=True)
    schema_names = pf.schema_arrow.names
    missing = [c for c in TEXT_COLUMNS if c not in schema_names]
    if missing:
        raise SystemExit(f"missing columns: {missing}; schema={schema_names}")
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for rg in range(md.num_row_groups):
            table = pf.read_row_group(rg, columns=TEXT_COLUMNS)
            cols = {name: table.column(name).to_pylist() for name in TEXT_COLUMNS}
            for i in range(table.num_rows):
                row = {name: cols[name][i] for name in TEXT_COLUMNS}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
            print(f"row_group {rg+1}/{md.num_row_groups} done, total={n}", flush=True)
    print(f"wrote {n} rows to {out_path}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
