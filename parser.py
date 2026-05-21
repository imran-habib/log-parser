"""
Fast concurrent log parser.
Splits files into byte-range chunks and processes them in parallel using multiprocessing.
Works on Windows and Linux.
"""
import os
import re
import multiprocessing as mp
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Match:
    line_num: int
    line: str


@dataclass
class ChunkResult:
    matches: List[Match] = field(default_factory=list)
    lines_scanned: int = 0
    error: Optional[str] = None


def find_chunk_boundaries(filepath: str, num_chunks: int) -> List[tuple]:
    """Split file into byte-range chunks aligned to newline boundaries."""
    file_size = os.path.getsize(filepath)
    if file_size == 0:
        return []

    chunk_size = file_size // num_chunks
    boundaries = []

    with open(filepath, "rb") as f:
        start = 0
        for i in range(num_chunks):
            if i == num_chunks - 1:
                boundaries.append((start, file_size))
                break

            end = start + chunk_size
            # Seek to approximate end and find next newline
            f.seek(end)
            f.readline()  # advance to end of current line
            end = f.tell()

            if end >= file_size:
                boundaries.append((start, file_size))
                break

            boundaries.append((start, end))
            start = end

    return boundaries


TS_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


def extract_timestamp(line: str) -> Optional[str]:
    """Extract ISO-like timestamp from start of line."""
    m = TS_PATTERN.search(line[:30])
    return m.group(0).replace("T", " ") if m else None


def process_chunk(args: tuple) -> dict:
    """Worker: read a byte range from file and match lines against pattern."""
    filepath, start, end, pattern, case_sensitive, after, before = args

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return {"matches": [], "lines_scanned": 0, "error": f"Invalid regex: {e}"}

    matches = []
    lines_scanned = 0
    has_time_filter = after is not None or before is not None

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        f.seek(start)
        pos = start
        while pos < end:
            line = f.readline()
            if not line:
                break
            pos = f.tell()
            lines_scanned += 1

            if has_time_filter:
                ts = extract_timestamp(line)
                if ts:
                    if after and ts < after:
                        continue
                    if before and ts > before:
                        continue

            if regex.search(line):
                matches.append({"line_num": lines_scanned, "line": line.rstrip("\n\r")})

    return {"matches": matches, "lines_scanned": lines_scanned, "error": None}


def parse_log(
    filepath: str,
    pattern: str,
    case_sensitive: bool = False,
    num_workers: Optional[int] = None,
    max_matches: int = 0,
    after: Optional[str] = None,
    before: Optional[str] = None,
) -> dict:
    """
    Parse a log file concurrently.

    Args:
        filepath: Path to log file
        pattern: Regex pattern to search for
        case_sensitive: Whether matching is case-sensitive
        num_workers: Number of parallel workers (default: CPU count)
        max_matches: Max matches to return (0 = unlimited)
        after: Only include lines with timestamp after this (YYYY-MM-DD HH:MM:SS)
        before: Only include lines with timestamp before this

    Returns:
        Dict with matches, stats, and any errors.
    """
    if not os.path.isfile(filepath):
        return {"matches": [], "total_lines": 0, "error": f"File not found: {filepath}"}

    if num_workers is None:
        num_workers = min(mp.cpu_count(), 8)

    # For small files, single process is faster
    file_size = os.path.getsize(filepath)
    if file_size < 1_000_000:  # < 1MB
        num_workers = 1

    boundaries = find_chunk_boundaries(filepath, num_workers)
    if not boundaries:
        return {"matches": [], "total_lines": 0, "error": None}

    # Build args for each worker
    work_args = [
        (filepath, start, end, pattern, case_sensitive, after, before)
        for start, end in boundaries
    ]

    # Process chunks in parallel
    if num_workers == 1:
        results = [process_chunk(work_args[0])]
    else:
        with mp.Pool(processes=num_workers) as pool:
            results = pool.map(process_chunk, work_args)

    # Aggregate results
    all_matches = []
    total_lines = 0
    errors = []

    for result in results:
        if result["error"]:
            errors.append(result["error"])
            continue
        # Adjust line numbers based on cumulative lines from previous chunks
        for m in result["matches"]:
            m["line_num"] += total_lines
            all_matches.append(Match(line_num=m["line_num"], line=m["line"]))
        total_lines += result["lines_scanned"]

    if max_matches > 0:
        all_matches = all_matches[:max_matches]

    return {
        "matches": all_matches,
        "total_lines": total_lines,
        "total_matches": len(all_matches),
        "workers_used": num_workers,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
        "error": "; ".join(errors) if errors else None,
    }
