"""Usage ledger: one JSON line per API call (including cache hits and failures)."""

import json
import time
from collections import defaultdict
from pathlib import Path


class Ledger:
    """Append-only usage log (usage.jsonl): one line per API call, cache hits included."""

    def __init__(self, path):
        self.path = Path(path)

    def record(self, *, service, model, host, status, cached, usage=None, elapsed_s=None, request_id=None):
        """Append one call's entry: service, model, status, tokens, cost and timing."""
        usage = usage or {}
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "service": service,
            "model": model,
            "host": host,
            "status": status,
            "cached": cached,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "cost_usd": usage.get("cost", 0) or 0,  # only OpenRouter reports cost
            "elapsed_s": elapsed_s,
            "request_id": request_id,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def entries(self):
        """Every recorded entry, oldest first."""
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def summary(self):
        """Totals per (host, model). Tokens and cost count live calls only; cache hits are free."""
        totals = defaultdict(
            lambda: {
                "calls": 0,
                "cache_hits": 0,
                "failed": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": 0.0,
            }
        )
        for e in self.entries():
            t = totals[(e["host"], e["model"])]
            if e["cached"]:
                t["cache_hits"] += 1
                continue
            t["calls"] += 1
            if not 200 <= e["status"] < 300:
                t["failed"] += 1
            t["prompt_tokens"] += e["prompt_tokens"]
            t["completion_tokens"] += e["completion_tokens"]
            t["cost_usd"] += e["cost_usd"]
        return [{"host": host, "model": model, **t} for (host, model), t in sorted(totals.items())]
