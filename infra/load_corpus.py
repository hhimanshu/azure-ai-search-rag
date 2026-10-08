"""Uploads the five driver's manuals to Blob Storage, one folder per state. Run by infra/deploy.sh; safe to run again."""

import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from pypdf import PdfReader, PdfWriter

from config import load_config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

STATE_FILES = {
    "california": "california-driver-handbook.pdf",
    "florida": "florida-driver-handbook.pdf",
    "new-jersey": "newjersey-driver-manual.pdf",
    "virginia": "virginia-drivers-manual.pdf",
    "wisconsin": "wisconsin-motorists-handbook.pdf",
}

MAX_INDEXER_DOC_BYTES = 14 * 1024 * 1024  # 14 MB: a safety margin under the indexer's 16 MB limit on Basic tier
ROLE_WAIT_SECONDS = 600
ROLE_POLL_SECONDS = 15


def split_oversized_pdf(path):
    """Yield (part_name, bytes): the file as is if it fits, else page-range halves under the limit."""
    reader = PdfReader(path)
    n = len(reader.pages)

    def render(first, last):
        writer = PdfWriter()
        for p in reader.pages[first:last + 1]:
            writer.add_page(p)
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    if path.stat().st_size <= MAX_INDEXER_DOC_BYTES:
        yield path.name, path.read_bytes()
        return

    ranges = []

    def split_range(first, last):
        data = render(first, last)
        if len(data) <= MAX_INDEXER_DOC_BYTES or first == last:
            ranges.append((first, last, data))
            return
        mid = (first + last) // 2
        split_range(first, mid)
        split_range(mid + 1, last)

    split_range(0, n - 1)
    ranges.sort()
    for i, (_, _, data) in enumerate(ranges, start=1):
        yield f"{path.stem}-part{i:02d}.pdf", data


def wait_for_blob_access(container_client):
    """A new role assignment can take a few minutes to work, so retry 403 errors for a while."""
    deadline = time.time() + ROLE_WAIT_SECONDS
    while True:
        try:
            container_client.get_container_properties()
            return
        except HttpResponseError as e:
            if e.status_code != 403 or time.time() > deadline:
                raise
            print(f"Waiting for the Blob Storage role to take effect ({e.status_code})...", flush=True)
            time.sleep(ROLE_POLL_SECONDS)


def main():
    config = load_config()
    container_client = BlobServiceClient(
        config.storage_account_url, credential=DefaultAzureCredential()
    ).get_container_client(config.storage_container_name)

    wait_for_blob_access(container_client)

    missing_files = [name for name in STATE_FILES.values() if not (DATA_DIR / name).exists()]
    if missing_files:
        print(f"MISSING in {DATA_DIR}: {', '.join(missing_files)}. Run data/download.sh first.", file=sys.stderr)
        return 1

    for state, filename in STATE_FILES.items():
        for part_name, part_bytes in split_oversized_pdf(DATA_DIR / filename):
            blob_client = container_client.get_blob_client(f"{state}/{part_name}")
            if blob_client.exists():
                print(f"Already uploaded: {state}/{part_name}")
                continue
            blob_client.upload_blob(part_bytes, overwrite=False)
            print(f"Uploaded: {state}/{part_name} ({len(part_bytes) / 1024 / 1024:.1f} MB)")

    uploaded = sorted(b.name for b in container_client.list_blobs())
    missing_states = set(STATE_FILES) - {name.split("/")[0] for name in uploaded}
    if missing_states:
        print(f"No blobs uploaded for: {sorted(missing_states)}", file=sys.stderr)
        return 1
    print(f"{len(uploaded)} blob(s) in '{config.storage_container_name}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
