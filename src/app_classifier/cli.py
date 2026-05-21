"""Command-line entry point — `app-classifier <repo-path>`.

Prints a human-readable summary AND a JSON blob (gated on --json).
No LLM call from the CLI — keep it dependency-free and pipeable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app_classifier import classify, __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app-classifier",
        description="Classify what an application does, based on its source code.",
    )
    parser.add_argument("repo", help="Path to the repo to classify")
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of a human-readable summary.",
    )
    parser.add_argument(
        "--include-signals", action="store_true",
        help="(JSON mode) Include the per-signal evidence trail.",
    )
    parser.add_argument(
        "--version", action="version", version=f"app-classifier {__version__}",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"error: not a directory: {repo}", file=sys.stderr)
        return 2

    result = classify(str(repo))

    if args.json:
        payload = result.to_dict()
        if not args.include_signals:
            # The hosting report is bundled IN the result via runtime/framework
            # /databases/etc., but the raw signals trail isn't on AppDescription.
            pass
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    # Human-readable
    print(f"\n=== {result.name} ===\n")
    print(f"Category:    {result.app_category} ({result.app_category_confidence:.0%} confidence)")
    print(f"Runtime:     {result.runtime.get('language', '?')} "
          f"{result.runtime.get('version') or result.runtime.get('version_spec') or ''}".rstrip())
    if result.framework:
        print(f"Framework:   {result.framework}")
    if result.deployment_target:
        print(f"Deploys as:  {result.deployment_target}")
    if result.databases:
        print(f"Databases:   {', '.join(result.databases)}")
    if result.caches_queues:
        print(f"Cache/Queue: {', '.join(result.caches_queues)}")
    if result.detected_features:
        print(f"Features:    {', '.join(result.detected_features)}")

    print(f"\n📋 Summary: {result.one_line_summary}\n")
    print(f"📝 What it does:\n  {result.functional_description}\n")

    if result.routes:
        print(f"🌐 HTTP Routes ({len(result.routes)} found):")
        for r in result.routes[:10]:
            print(f"  {r.method:<6} {r.path}  →  {r.handler}")
        if len(result.routes) > 10:
            print(f"  ... +{len(result.routes) - 10} more")
        print()

    if result.data_models:
        print(f"🗂️  Data Models ({len(result.data_models)} found):")
        for m in result.data_models[:10]:
            fields = ", ".join(m.fields_hint[:5])
            more = f", +{len(m.fields_hint) - 5} more" if len(m.fields_hint) > 5 else ""
            print(f"  {m.name} ({m.framework or '?'}): {fields}{more}")
        if len(result.data_models) > 10:
            print(f"  ... +{len(result.data_models) - 10} more")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
