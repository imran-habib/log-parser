# log-parser

A fast, concurrent log file parser built in Python. Processes 500k+ lines at **~1 million lines/second** using multiprocessing with byte-range chunking. Works on both Windows and Linux with zero external dependencies.

## Features

- **Parallel processing** — splits files into byte-range chunks, processes them across multiple CPU cores
- **Regex pattern matching** — full regex support with case-sensitive/insensitive modes
- **Time range filtering** — filter log lines by timestamp window
- **Color highlighting** — matched text highlighted in red (auto-detects terminal support)
- **JSON export** — export results to structured JSON for further processing
- **Top-N frequency analysis** — find the most common matching messages
- **Cross-platform** — works on Windows and Linux
- **Zero dependencies** — pure Python standard library only
- **Smart scaling** — auto-selects worker count based on available CPU cores

## Installation

No installation needed. Clone and run:

```bash
git clone https://github.com/your-username/log-parser.git
cd log-parser
```

Requires Python 3.7+.

## Usage

```
usage: logparser.py [-h] [-i] [-n MAX] [-w WORKERS] [-s] [-c] [--no-color]
                    [--after AFTER] [--before BEFORE] [--output OUTPUT]
                    [--top TOP]
                    file pattern

Fast concurrent log parser

positional arguments:
  file                  Log file to parse
  pattern               Regex pattern to search for

options:
  -h, --help            show this help message and exit
  -i, --ignore-case     Case-insensitive matching
  -n, --max MAX         Max matches to show (0=all)
  -w, --workers WORKERS
                        Number of workers
  -s, --stats           Show summary stats
  -c, --count           Only show match count
  --no-color            Disable colored output
  --after AFTER         Only lines after this timestamp (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
  --before BEFORE       Only lines before this timestamp
  --output OUTPUT       Export results to JSON file
  --top TOP             Show top N most frequent matches
```

## Examples

### Basic search

Find all lines containing "ERROR":

```bash
python logparser.py server.log "ERROR"
```

Output:
```
      16: 2025-01-01T00:00:15 [ERROR] [auth] User authentication completed
      18: 2025-01-01T00:00:17 [ERROR] [worker] File descriptor limit approaching
      54: 2025-01-01T00:00:53 [ERROR] [gateway] Memory allocation failed for buffer
```

### Case-insensitive regex

Search for multiple patterns:

```bash
python logparser.py server.log "timeout|connection refused" -i
```

### Limit results

Show only the first 20 matches:

```bash
python logparser.py server.log "WARN" --max 20
```

### Count matches with stats

Get a quick count and performance summary:

```bash
python logparser.py server.log "ERROR" --count --stats
```

Output:
```
49862

────────────────────────────────────────────────────────────
  Pattern:       ERROR
  File size:     33.83 MB
  Total lines:   500,000
  Matches:       49,862
  Workers used:  8
  Time:          0.463s
  Speed:         1,079,067 lines/sec
────────────────────────────────────────────────────────────
```

### Time range filtering

Only search within a specific time window:

```bash
# Lines from a specific hour
python logparser.py server.log "ERROR" --after "2025-01-01 08:00:00" --before "2025-01-01 09:00:00"

# Lines from a specific day
python logparser.py server.log "timeout" --after "2025-01-03" --before "2025-01-04"
```

### Top N most frequent matches

Find the most common error messages:

```bash
python logparser.py server.log "ERROR" --count --top 10
```

Output:
```
50225

────────────────────────────────────────────────────────────
  Top 10 most frequent matches:
────────────────────────────────────────────────────────────
    3458x  Invalid input received from client
    3407x  SSL handshake failed with peer
    3384x  Connection established to database
    3355x  Connection refused: service unavailable
    3347x  Request processed successfully
    3320x  Timeout waiting for response from upstream
    3298x  Memory allocation failed for buffer
    3285x  File descriptor limit approaching: 421/1024
    3270x  Retrying request attempt 2/3
    3251x  Cache miss for key session_847
────────────────────────────────────────────────────────────
```

### Export to JSON

Save results for further processing or integration with other tools:

```bash
python logparser.py server.log "ERROR" --max 100 --output errors.json
```

Output file (`errors.json`):
```json
{
  "pattern": "ERROR",
  "file": "/path/to/server.log",
  "stats": {
    "file_size_mb": 33.84,
    "total_lines": 500000,
    "total_matches": 100,
    "workers_used": 8,
    "elapsed_seconds": 0.493
  },
  "matches": [
    {
      "line_num": 16,
      "text": "2025-01-01T00:00:15 [ERROR] [auth] User authentication completed"
    },
    ...
  ]
}
```

### Combining features

Find top timeout errors in a time window and export:

```bash
python logparser.py server.log "timeout|refused" -i \
  --after "2025-01-05" --before "2025-01-06" \
  --top 5 --stats --output report.json
```

### Searching by service

Use regex to filter by specific service tags:

```bash
# All errors from the gateway service
python logparser.py server.log "\[gateway\].*ERROR" --count

# All warnings from auth or db
python logparser.py server.log "\[(auth|db)\].*WARN" --top 5
```

### Control parallelism

Force a specific number of workers:

```bash
# Use 4 workers
python logparser.py server.log "ERROR" -w 4 --stats

# Single-threaded (for comparison/debugging)
python logparser.py server.log "ERROR" -w 1 --stats
```

## How it works

```
┌─────────────────────────────────────────────────────┐
│  CLI (argparse)                                      │
│  logparser.py parse <file> --pattern "ERROR" ...     │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  Chunker                                             │
│  Splits file into N byte-range chunks                │
│  (aligned to newline boundaries)                     │
└────────────────────────┬────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌────────────────┐┌────────────────┐┌────────────────┐
│   Worker 1     ││   Worker 2     ││   Worker N     │
│   Seeks to     ││   Seeks to     ││   Seeks to     │
│   byte offset  ││   byte offset  ││   byte offset  │
│   Regex match  ││   Regex match  ││   Regex match  │
│   Time filter  ││   Time filter  ││   Time filter  │
└───────┬────────┘└───────┬────────┘└───────┬────────┘
        └─────────────────┼─────────────────┘
                          ▼
┌─────────────────────────────────────────────────────┐
│  Aggregator                                          │
│  Merge results, fix line numbers, stats, export      │
└─────────────────────────────────────────────────────┘
```

1. **Chunking** — The file is divided into N byte-range segments. Each boundary is aligned to a newline so no line is split across workers.
2. **Parallel reading** — Each worker opens the file independently, seeks to its start offset, and reads only its chunk. No data is copied between processes.
3. **Filtering** — Each worker applies regex matching and optional time range filtering on its chunk.
4. **Aggregation** — Results from all workers are merged with corrected line numbers and returned to the CLI for display/export.

## Performance

Benchmarked on a 500,000-line log file (34 MB):

| Workers | Time | Speed |
|---------|------|-------|
| 1 | ~1.5s | ~330k lines/sec |
| 2 | ~0.8s | ~625k lines/sec |
| 4 | ~0.6s | ~830k lines/sec |
| 8 | ~0.46s | ~1.08M lines/sec |

Performance scales near-linearly with CPU cores up to I/O saturation.

## Supported log formats

The parser works with any text-based log file. Time filtering requires ISO-like timestamps at the start of lines:

```
2025-01-01T00:00:15 [ERROR] [auth] Message here
2025-01-01 00:00:15 [WARN] [db] Another message
```

Supported timestamp formats for `--after`/`--before`:
- `YYYY-MM-DD` (matches entire day)
- `YYYY-MM-DD HH:MM:SS` (exact time)

## Generate test data

Create a 500,000-line sample log file for testing:

```bash
python generate_test_log.py
```

## Project structure

```
log-parser/
├── logparser.py          # CLI entry point
├── parser.py             # Core engine (multiprocessing + chunking)
├── generate_test_log.py  # Test data generator
└── README.md
```

## License

MIT
