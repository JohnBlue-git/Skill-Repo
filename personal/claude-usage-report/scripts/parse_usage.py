#!/usr/bin/env python3
"""Aggregate Claude Code local session logs (~/.claude/projects/*.jsonl) into
per-day token usage and estimated cost. Stdlib only, no dependencies.
"""
import json
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime

DEFAULT_PRICING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pricing.json")


def load_pricing(path=None):
    with open(path or DEFAULT_PRICING_PATH) as f:
        return json.load(f)


def compute_usage(claude_dir=None, pricing=None):
    """Returns {"files_scanned", "total_lines", "daily": {date: {...}}}."""
    claude_dir = claude_dir or os.path.join(os.path.expanduser("~"), ".claude")
    pricing = pricing or load_pricing()
    models = pricing["models"]
    default_price = pricing["default"]
    mult_1h = pricing["cache_write_1h_multiplier"]
    mult_5m = pricing["cache_write_5m_multiplier"]
    mult_read = pricing["cache_read_multiplier"]

    files = glob.glob(os.path.join(claude_dir, "projects", "**", "*.jsonl"), recursive=True)

    # per (day, model) — needed because pricing varies by model
    bucket = defaultdict(lambda: {
        "input": 0, "output": 0, "cache_1h": 0, "cache_5m": 0, "cache_read": 0, "messages": 0
    })
    total_lines = 0

    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total_lines += 1
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts = obj.get("timestamp")
                    msg = obj.get("message")
                    if not ts or not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    try:
                        day = datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
                    except ValueError:
                        continue

                    model = msg.get("model", "unknown")
                    b = bucket[(day, model)]
                    b["input"] += usage.get("input_tokens", 0) or 0
                    b["output"] += usage.get("output_tokens", 0) or 0
                    cc = usage.get("cache_creation") or {}
                    if cc:
                        b["cache_1h"] += cc.get("ephemeral_1h_input_tokens", 0) or 0
                        b["cache_5m"] += cc.get("ephemeral_5m_input_tokens", 0) or 0
                    else:
                        # older transcripts have no 1h/5m breakdown; API default is 5m
                        b["cache_5m"] += usage.get("cache_creation_input_tokens", 0) or 0
                    b["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                    b["messages"] += 1
        except (OSError, IOError):
            continue

    daily = defaultdict(lambda: {
        "input": 0, "output": 0, "cache_1h": 0, "cache_5m": 0, "cache_read": 0,
        "messages": 0, "cost_usd": 0.0
    })
    for (day, model), b in bucket.items():
        price = models.get(model, default_price)
        cost = (
            b["input"] * price["input"]
            + b["output"] * price["output"]
            + b["cache_1h"] * price["input"] * mult_1h
            + b["cache_5m"] * price["input"] * mult_5m
            + b["cache_read"] * price["input"] * mult_read
        ) / 1_000_000
        d = daily[day]
        for k in ("input", "output", "cache_1h", "cache_5m", "cache_read", "messages"):
            d[k] += b[k]
        d["cost_usd"] += cost

    out = {}
    for day, d in sorted(daily.items()):
        total_tokens = d["input"] + d["output"] + d["cache_1h"] + d["cache_5m"] + d["cache_read"]
        out[day] = {
            **{k: d[k] for k in ("input", "output", "cache_1h", "cache_5m", "cache_read", "messages")},
            "total_tokens": total_tokens,
            "cost_usd": round(d["cost_usd"], 4),
        }

    return {"files_scanned": len(files), "total_lines": total_lines, "daily": out}


def main():
    result = compute_usage()
    daily = result["daily"]
    out_path = sys.argv[1] if len(sys.argv) > 1 else None

    payload = json.dumps(daily, indent=2)
    if out_path:
        with open(out_path, "w") as f:
            f.write(payload)
    else:
        print(payload)

    total_cost = sum(d["cost_usd"] for d in daily.values())
    dest = f" -> {out_path}" if out_path else ""
    print(
        f"[parse_usage] {result['files_scanned']} files scanned, {len(daily)} active days, "
        f"${total_cost:.2f} estimated{dest}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
