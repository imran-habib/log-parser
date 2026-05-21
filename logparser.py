#!/usr/bin/env python3
"""
logparser - Fast concurrent log file parser.

Usage:
    python logparser.py <file> <pattern> [options]

Examples:
    python logparser.py app.log "ERROR"
    python logparser.py app.log "timeout|refused" -i --top 10
    python logparser.py app.log "WARN" --after "2025-01-03" --before "2025-01-04"
    python logparser.py app.log "ERROR" --output results.json
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

from parser import parse_log

# ANSI color codes
RED = "\033[91m"
RESET = "\033[0m"
CYAN = "\033[96m"
YELLOW = "\033[93m"


def supports_color():
    """Check if terminal supports color."""
    if os.name == "nt":
        return os.environ.get("ANSICON") or "WT_SESSION" in os.environ
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def colorize_match(line, pattern, case_sensitive):
    """Highlight matched text in red."""
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.sub(f"({pattern})", f"{RED}\\1{RESET}", line, flags=flags)


def print_summary(result, elapsed, pattern):
    """Print a stats summary."""
    print(f"\n{'─' * 60}")
    print(f"  Pattern:       {pattern}")
    print(f"  File size:     {result['file_size_mb']} MB")
    print(f"  Total lines:   {result['total_lines']:,}")
    print(f"  Matches:       {result['total_matches']:,}")
    print(f"  Workers used:  {result['workers_used']}")
    print(f"  Time:          {elapsed:.3f}s")
    if elapsed > 0:
        lines_per_sec = result['total_lines'] / elapsed
        print(f"  Speed:         {lines_per_sec:,.0f} lines/sec")
    print(f"{'─' * 60}")


def print_top(matches, n):
    """Show top N most frequent matching lines (message part only)."""
    # Strip line number prefix and timestamp to group by message content
    messages = []
    for m in matches:
        # Try to extract message after timestamp and level
        parts = m.line.split("] ", 2)
        msg = parts[-1] if len(parts) > 1 else m.line
        messages.append(msg)

    counter = Counter(messages)
    print(f"\n{'─' * 60}")
    print(f"  Top {n} most frequent matches:")
    print(f"{'─' * 60}")
    for msg, count in counter.most_common(n):
        print(f"  {count:>6}x  {msg}")
    print(f"{'─' * 60}")


def export_json(result, elapsed, pattern, filepath):
    """Export results to JSON file."""
    output = {
        "pattern": pattern,
        "file": os.path.abspath(result.get("_filepath", "")),
        "stats": {
            "file_size_mb": result["file_size_mb"],
            "total_lines": result["total_lines"],
            "total_matches": result["total_matches"],
            "workers_used": result["workers_used"],
            "elapsed_seconds": round(elapsed, 3),
        },
        "matches": [{"line_num": m.line_num, "text": m.line} for m in result["matches"]],
    }
    with open(filepath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results exported to {filepath}")


def main():
    p = argparse.ArgumentParser(description="Fast concurrent log parser")
    p.add_argument("file", help="Log file to parse")
    p.add_argument("pattern", help="Regex pattern to search for")
    p.add_argument("-i", "--ignore-case", action="store_true", help="Case-insensitive matching")
    p.add_argument("-n", "--max", type=int, default=0, help="Max matches to show (0=all)")
    p.add_argument("-w", "--workers", type=int, default=None, help="Number of workers")
    p.add_argument("-s", "--stats", action="store_true", help="Show summary stats")
    p.add_argument("-c", "--count", action="store_true", help="Only show match count")
    p.add_argument("--no-color", action="store_true", help="Disable colored output")
    p.add_argument("--after", type=str, help="Only lines after this timestamp (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")
    p.add_argument("--before", type=str, help="Only lines before this timestamp")
    p.add_argument("--output", type=str, help="Export results to JSON file")
    p.add_argument("--top", type=int, default=0, help="Show top N most frequent matches")

    args = p.parse_args()
    use_color = supports_color() and not args.no_color
    case_sensitive = not args.ignore_case

    start = time.perf_counter()
    result = parse_log(
        filepath=args.file,
        pattern=args.pattern,
        case_sensitive=case_sensitive,
        num_workers=args.workers,
        max_matches=args.max,
        after=args.after,
        before=args.before,
    )
    elapsed = time.perf_counter() - start

    if result["error"]:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    # JSON export
    if args.output:
        result["_filepath"] = args.file
        export_json(result, elapsed, args.pattern, args.output)
        if args.stats:
            print_summary(result, elapsed, args.pattern)
        return

    # Count only
    if args.count:
        print(result["total_matches"])
        if args.top:
            print_top(result["matches"], args.top)
        if args.stats:
            print_summary(result, elapsed, args.pattern)
        return

    # Print matches
    for m in result["matches"]:
        line = m.line
        if use_color:
            line = colorize_match(line, args.pattern, case_sensitive)
        print(f"{CYAN}{m.line_num:>8}{RESET}: {line}" if use_color else f"{m.line_num:>8}: {line}")

    # Top N frequent
    if args.top:
        print_top(result["matches"], args.top)

    if args.stats or not result["matches"]:
        print_summary(result, elapsed, args.pattern)


if __name__ == "__main__":
    main()
