# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "python-dotenv"]
# ///
"""One tiny real call per external API, recorded to fixtures/recorded/.

Spends credits. Run each check once:
    uv run scripts/smoke_test.py --dry-run          # show requests, send nothing
    uv run scripts/smoke_test.py                    # all four checks
    uv run scripts/smoke_test.py --only translate   # just one
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "fixtures" / "recorded"
SAMPLE_PAGE = ROOT / "fixtures" / "inputs" / "sample_page.png"

BODHAN_BASE_URL = "https://api.bodhan.ai"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Free models were rate-limited upstream on 2026-10-20; this one costs fractions of a cent.
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash-lite"

# Response headers worth keeping; everything else is noise.
KEEP_HEADERS = ("x-request-id", "content-type")
KEEP_HEADER_PREFIXES = ("x-ratelimit-",)


def build_checks(openrouter_model):
    """Each check: (name, env var holding the key, url, json body).

    The documented /translate and /transliterate routes return 404 (2026-10-20), so all
    Bodhan models go through /v1/chat/completions with extra top-level fields. Transliterate
    wants `target_language` (not the documented `language`); a wrong field name is ignored
    silently, and the model may translate instead of transliterating.
    """
    page_b64 = base64.b64encode(SAMPLE_PAGE.read_bytes()).decode()
    return {
        "translate": (
            "BODHAN_TRANSLATE",
            f"{BODHAN_BASE_URL}/v1/chat/completions",
            {
                "model": "indic-translate",
                "messages": [{"role": "user", "content": "The meeting has been postponed to next week."}],
                "target_language": "hi",
            },
        ),
        "transliterate": (
            "BODHAN_TRANSLITERATE",
            f"{BODHAN_BASE_URL}/v1/chat/completions",
            {
                "model": "indic-transliterate",
                "messages": [{"role": "user", "content": "बैठक अगले सप्ताह तक स्थगित कर दी गई है।"}],
                "target_language": "hi",
                "script": "roman",
            },
        ),
        "ocr": (
            "BODHAN_OCR",
            f"{BODHAN_BASE_URL}/v1/chat/completions",
            {
                "model": "indic-ocr",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_b64}"}},
                        ],
                    }
                ],
            },
        ),
        "openrouter": (
            "OPENROUTER",
            f"{OPENROUTER_BASE_URL}/chat/completions",
            {
                "model": openrouter_model,
                "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                "max_tokens": 10,
            },
        ),
    }


def redact_body(name, body):
    """Keep recordings small: replace the inline page image with a file reference."""
    if name != "ocr":
        return body
    body = json.loads(json.dumps(body))
    body["messages"][0]["content"][0]["image_url"]["url"] = f"<base64 of {SAMPLE_PAGE.relative_to(ROOT)}>"
    return body


def kept_headers(headers):
    """The response headers worth recording (request id, content type, rate limits)."""
    return {k: v for k, v in headers.items() if k.lower() in KEEP_HEADERS or k.lower().startswith(KEEP_HEADER_PREFIXES)}


def run_check(client, name, env_var, url, body, dry_run):
    """Send one check's request and record the response under fixtures/recorded/; whether it succeeded (False when its
    key isn't set)."""
    key = os.environ.get(env_var)
    if not key:
        print(f"[{name}] SKIP: {env_var} not set in .env")
        return False

    print(f"[{name}] POST {url}")
    if dry_run:
        print(json.dumps(redact_body(name, body), ensure_ascii=False, indent=2))
        return True

    started = time.monotonic()
    resp = client.post(url, json=body, headers={"Authorization": f"Bearer {key}"})
    elapsed = round(time.monotonic() - started, 2)
    try:
        payload = resp.json()
    except ValueError:
        payload = {"_raw_text": resp.text}

    record = {
        "check": name,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "request": {"method": "POST", "url": url, "body": redact_body(name, body)},
        "response": {
            "status": resp.status_code,
            "elapsed_s": elapsed,
            "headers": kept_headers(resp.headers),
            "body": payload,
        },
    }
    out = OUT_DIR / f"{name}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")

    ok = resp.is_success
    print(f"[{name}] {'OK' if ok else 'FAIL'} {resp.status_code} in {elapsed}s -> {out.relative_to(ROOT)}")
    for k, v in kept_headers(resp.headers).items():
        print(f"    {k}: {v}")
    if "usage" in payload:
        print(f"    usage: {payload['usage']}")
    return ok


def main():
    """Run the selected checks and exit non-zero if any failed."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", choices=["translate", "transliterate", "ocr", "openrouter"])
    parser.add_argument("--dry-run", action="store_true", help="print requests without sending them")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    checks = build_checks(os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL))
    selected = args.only or list(checks)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    with httpx.Client(timeout=120) as client:
        for name in selected:
            env_var, url, body = checks[name]
            try:
                results[name] = run_check(client, name, env_var, url, body, args.dry_run)
            except httpx.HTTPError as exc:
                print(f"[{name}] ERROR: {exc!r}")
                results[name] = False

    print("\nSummary:", ", ".join(f"{n}={'ok' if ok else 'FAIL'}" for n, ok in results.items()))
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
