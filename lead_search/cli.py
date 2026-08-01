"""lead-search CLI: run the org-search pipeline from the terminal. No UI."""

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from .pipeline import RunConfig, run_pipeline
from .storage import append_to_registry, build_rows, load_registry_snapshot, write_run_log


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="lead-search",
        description="Discover, verify, and research organizations of any type in a target "
        "area, and find outreach contacts. Results append to a registry CSV.",
    )
    parser.add_argument("org_type", help='e.g. "food banks", "youth sports leagues"')
    parser.add_argument("--area", required=True, help='e.g. "Medford, Massachusetts"')
    parser.add_argument("--purpose", default="", help="Why you're reaching out (enables outreach drafting)")
    parser.add_argument("--sender", default="", help="Signature name for outreach messages")
    parser.add_argument("--registry", default="registry.csv", help="Registry CSV path (default: registry.csv)")
    parser.add_argument("--out", default="runs", help="Directory for raw run logs (default: runs/)")
    parser.add_argument("--model", default="claude-opus-5", help="Claude model ID (default: claude-opus-5)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel research workers (default: 4)")
    parser.add_argument(
        "--no-email-hunt", action="store_true",
        help="Skip the deep email hunt for contacts without a published email",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    cfg = RunConfig(
        org_type=args.org_type,
        area=args.area,
        purpose=args.purpose,
        sender=args.sender,
        model=args.model,
        workers=args.workers,
        deep_email_hunt=not args.no_email_hunt,
    )
    registry_path = Path(args.registry)
    known = load_registry_snapshot(registry_path)

    result = run_pipeline(cfg, known)

    rows = build_rows(result["orgs"], result["contacts"])
    append_to_registry(registry_path, rows)

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", f"{args.org_type}-{args.area}".lower()).strip("-")[:80]
    log_path = write_run_log(
        Path(args.out),
        f"{stamp}-{slug}",
        {
            "config": vars(args),
            "candidates": [c.model_dump() for c in result["candidates"]],
            "verdicts": [v.model_dump() for v in result["verdicts"]],
            "orgs": [o.model_dump() for o in result["orgs"]],
            "contacts": [c.model_dump() for c in result["contacts"]],
        },
    )

    print(
        f"\nDone: {len(result['orgs'])} orgs researched, {len(result['contacts'])} contacts "
        f"found.\nRegistry: {registry_path}  ({len(rows)} rows appended)\nRun log: {log_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
