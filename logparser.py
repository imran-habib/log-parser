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
GREEN = "\033[92m"
BOLD = "\033[1m"
DIM = "\033[2m"


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


def generate_summary(filepath: str):
    """Auto-analyze a log file and print a comprehensive summary."""
    if not os.path.isfile(filepath):
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    start = time.perf_counter()
    file_size = os.path.getsize(filepath)

    # Patterns to detect log levels
    level_pattern = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL|TRACE)\b", re.IGNORECASE)
    # Pattern to detect services/components in brackets
    service_pattern = re.compile(r"\[([a-zA-Z][\w.-]{1,30})\]")
    # Timestamp pattern
    ts_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})")

    levels = Counter()
    services = Counter()
    error_messages = Counter()
    first_ts = None
    last_ts = None
    total_lines = 0

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            total_lines += 1

            # Detect timestamp
            ts_match = ts_pattern.search(line[:30])
            if ts_match:
                ts = ts_match.group(1).replace("T", " ")
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            # Detect log level
            level_match = level_pattern.search(line)
            if level_match:
                level = level_match.group(1).upper()
                if level == "WARNING":
                    level = "WARN"
                levels[level] += 1

            # Detect service
            for svc_match in service_pattern.finditer(line):
                svc = svc_match.group(1)
                # Skip log levels that might be in brackets
                if svc.upper() not in ("DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL", "TRACE"):
                    services[svc] += 1
                    break

            # Collect error messages
            if level_match and level_match.group(1).upper() in ("ERROR", "FATAL", "CRITICAL"):
                # Extract message part (after last ] or after level)
                parts = line.split("] ")
                msg = parts[-1].strip() if len(parts) > 1 else line.strip()
                if msg:
                    error_messages[msg] += 1

    elapsed = time.perf_counter() - start

    # Print summary
    bar = "═" * 60
    print(f"\n{bar}")
    print(f"  Log Summary: {os.path.basename(filepath)}")
    print(f"{bar}")
    print(f"  File size:    {file_size / (1024*1024):.1f} MB")
    print(f"  Total lines:  {total_lines:,}")
    print(f"  Scan time:    {elapsed:.2f}s")

    if first_ts and last_ts:
        print(f"  Time range:   {first_ts} → {last_ts}")

    # Log levels
    if levels:
        print(f"\n  Log Levels:")
        max_count = max(levels.values())
        for level, count in levels.most_common():
            pct = count / total_lines * 100
            bar_len = int(count / max_count * 25)
            bar_str = "█" * bar_len + "░" * (25 - bar_len)
            color = RED if level in ("ERROR", "FATAL", "CRITICAL") else YELLOW if level == "WARN" else ""
            reset = RESET if color else ""
            print(f"    {color}{level:<8}{reset} {count:>10,}  ({pct:4.1f}%)  {bar_str}")

    # Services
    if services:
        print(f"\n  Services/Components:")
        for svc, count in services.most_common(10):
            print(f"    {svc:<20} {count:>10,}")

    # Top errors
    error_count = sum(1 for l, c in levels.items() if l in ("ERROR", "FATAL", "CRITICAL") for _ in range(c))
    if error_messages:
        print(f"\n  Top Errors:")
        for msg, count in error_messages.most_common(5):
            print(f"    {count:>6,}x  {msg[:70]}")

    # Error rate
    if first_ts and last_ts and error_count > 0:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%d %H:%M:%S"
            t1 = datetime.strptime(first_ts, fmt)
            t2 = datetime.strptime(last_ts, fmt)
            hours = (t2 - t1).total_seconds() / 3600
            if hours > 0:
                print(f"\n  Error rate:   ~{int(error_count / hours)}/hour")
        except (ValueError, ImportError):
            pass

    print(f"\n{bar}")
    print(f"  Narrow down with:")
    print(f"    python logparser.py {filepath} \"ERROR\" --top 10")
    print(f"    python logparser.py {filepath} \"timeout\" -i --stats")
    if first_ts:
        print(f"    python logparser.py {filepath} \"ERROR\" --after \"{first_ts[:10]}\"")
    print(f"{bar}\n")


def main():
    p = argparse.ArgumentParser(description="Fast concurrent log parser")
    p.add_argument("file", help="Log file to parse")
    p.add_argument("pattern", nargs="?", default=None, help="Regex pattern to search for")
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
    p.add_argument("--summary", action="store_true", help="Auto-analyze log file and show overview")

    args = p.parse_args()

    # Summary mode
    if args.summary or args.pattern is None:
        generate_summary(args.file)
        return

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
