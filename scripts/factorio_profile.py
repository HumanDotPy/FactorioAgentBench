"""Enable, inspect, or stop profiling an active local-envd lease."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["enable", "disable", "report"])
    parser.add_argument("--url", default=os.environ.get("ENVD_URL"))
    parser.add_argument("--lease", default=os.environ.get("LEASE_ID"))
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument(
        "--every", type=int, default=1, help="Sample every N HTTP operations"
    )
    parser.add_argument("--clear", action="store_true", help="Discard earlier samples")
    parser.add_argument("--output", type=Path, help="Export full report as JSON")
    args = parser.parse_args(argv)
    if not args.url or not args.lease:
        parser.error("--url/ENVD_URL and --lease/LEASE_ID are required")
    if not 1 <= args.seconds <= 3600 or not 1 <= args.every <= 1000:
        parser.error("--seconds must be 1..3600 and --every must be 1..1000")
    if args.command == "report" and args.clear:
        parser.error("--clear requires enable or disable")
    url = (
        args.url.rstrip("/")
        + "/v1/leases/"
        + urllib.parse.quote(args.lease, safe="")
        + "/profiling"
    )
    payload = (
        None
        if args.command == "report"
        else {
            "enabled": args.command == "enable",
            "duration_seconds": args.seconds,
            "sample_every": args.every,
            "clear": args.clear,
        }
    )
    request = urllib.request.Request(
        url,
        method="GET" if payload is None else "PUT",
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            report = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        parser.exit(1, f"Profiling request failed: {exc}\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Profiling {'enabled' if report['enabled'] else 'disabled'}; "
        f"{len(report['traces'])} retained samples; "
        f"{report['remaining_seconds']:.0f}s remaining"
    )
    print(
        "Operation                                         n   mean ms    p95 ms    max ms"
    )
    for name, values in report["operations"].items():
        print(
            f"{name:48} {values['count']:3} {values['mean_ms']:9.2f} "
            f"{values['p95_ms']:9.2f} {values['max_ms']:9.2f}"
        )
    print(
        "\nStages (inclusive; nested totals overlap)          n  total ms    max ms  errors"
    )
    for name, values in sorted(
        report["stages"].items(), key=lambda row: -row[1]["total_ms"]
    ):
        print(
            f"{name:48} {values['count']:3} {values['total_ms']:9.2f} "
            f"{values['max_ms']:9.2f} {values['errors']:7}"
        )
    if args.output:
        print(f"Full report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
