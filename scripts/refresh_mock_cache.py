"""Drop mock-run cache entries that a live recording now covers, so the mock replays the real answer.

    uv run scripts/refresh_mock_cache.py

The backend caches every answer it gets, the mock's invented ones included, under data/mock/cache/localhost_9000/.
A request answered with invented text before it was ever run live keeps returning that text after the live answer
is recorded, because the backend's cache is asked before the mock. Cache keys depend only on the request, so a
mock-cache file with the same name as a live one is such a case. Restart the mock afterwards: it reads the live
recordings when it starts.
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "data" / "mock" / "cache" / "localhost_9000"
LIVE = ROOT / "data" / "live" / "cache"


def main():
    """Delete the mock's cached answers that now have a live recording."""
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    live = {
        (model.name, f.name)
        for host in LIVE.iterdir()
        if host.is_dir()
        for model in host.iterdir()
        for f in model.glob("*.json")
    }
    dropped = 0
    for model in MOCK.iterdir() if MOCK.exists() else ():
        for f in model.glob("*.json"):
            if (model.name, f.name) in live:
                f.unlink()
                dropped += 1
    print(f"dropped {dropped} mock cache entries that now have a live recording")


if __name__ == "__main__":
    main()
