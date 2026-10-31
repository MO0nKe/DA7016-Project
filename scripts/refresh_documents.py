"""Lay stored documents out again after an ingest change, and translate them again into their languages.

    uv run scripts/refresh_documents.py                    # every document, backend on http://localhost:8000
    uv run scripts/refresh_documents.py 5e15d85357c3 ...   # just these
    uv run scripts/refresh_documents.py --url http://localhost:8000 --backup data/refresh-backup

Ingest runs once per file (the id is a hash of the PDF), so ingest fixes never reach documents already in the
library. This deletes each document and uploads its PDF again (same id, so its folder is put back and reading
positions survive), lets the upload's structure review run (about $0.01 a page on OpenRouter), and translates it
again into each language Bodhan had translated it into. Unchanged text comes from the request cache, so it's free.

Prompt edits are lost; the script lists them first. A language that only had prompt-edited sections (no Bodhan
translation) isn't translated in full: its edits are listed as lost. Each PDF and its doc.json are copied to
--backup first.
"""

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def wait(client, doc_id, job_id=None):
    """Until that job ends, or (no job id) until the document has no running job (its structure review)."""
    url = f"/api/jobs/{job_id}" if job_id else f"/api/documents/{doc_id}/job"
    while (job := client.get(url).json()) and job["status"] == "running":
        print(f"    {job['kind']} {job['done']}/{job['total']}", end="\r", flush=True)
        time.sleep(3)
    return job


def refresh(client, doc_id, folder, backup):
    """Back up a document, delete and re-upload it, put it back in its folder and re-translate it into its languages."""
    doc = client.get(f"/api/documents/{doc_id}").raise_for_status().json()
    translations = [
        (b["id"], lang, t) for p in doc["pages"] for b in p["blocks"] for lang, t in b["translations"].items()
    ]
    langs = sorted({lang for _, lang, t in translations if not (t["edits"] and t["edits"][0].get("created"))})
    edited = [
        (bid, lang)
        for bid, lang, t in translations  # the heading pass's own revisions are redone on translation
        if any(not e["instruction"].startswith("This heading was machine-translated") for e in t["edits"])
    ]
    print(
        f"{doc_id} {doc['filename']}: translate into {langs or 'nothing'}"
        + (f"; {len(edited)} prompt edits lost: {edited}" if edited else "")
    )

    pdf = client.get(f"/api/documents/{doc_id}/source.pdf").raise_for_status().content
    backup.mkdir(parents=True, exist_ok=True)
    (backup / f"{doc_id}.pdf").write_bytes(pdf)
    (backup / f"{doc_id}.json").write_text(json.dumps(doc, ensure_ascii=False))  # its edits, should they be wanted
    client.delete(f"/api/documents/{doc_id}").raise_for_status()
    new = (
        client.post("/api/documents", files={"file": (doc["filename"], pdf, "application/pdf")})
        .raise_for_status()
        .json()
    )
    assert new["id"] == doc_id, f"re-upload got id {new['id']}"
    if folder:
        client.put(f"/api/documents/{doc_id}/folder", json={"folder_id": folder}).raise_for_status()
    wait(client, doc_id)
    if langs:
        started = client.post(f"/api/documents/{doc_id}/translate", json={"langs": langs}).raise_for_status().json()
        job = wait(client, doc_id, started["id"])
        print(f"    {job['status']}: {job['done']} translated, {job['failed']} failed" + " " * 20)


def main():
    """Refresh the given documents, or every document in the library."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="*", help="document ids (default: all)")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--backup", type=Path, default=ROOT / "data" / "refresh-backup")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=120) as client:
        placement = client.get("/api/library").raise_for_status().json()["placement"]
        ids = args.ids or [d["id"] for d in client.get("/api/documents").raise_for_status().json()]
        for doc_id in ids:
            refresh(client, doc_id, placement.get(doc_id), args.backup)


if __name__ == "__main__":
    main()
