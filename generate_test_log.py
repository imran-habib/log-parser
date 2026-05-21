"""Generate a large test log file with 500k lines."""
import random
import datetime

LEVELS = ["INFO"] * 70 + ["WARN"] * 15 + ["ERROR"] * 10 + ["DEBUG"] * 5
MESSAGES = [
    "Request processed successfully",
    "Connection established to database",
    "User authentication completed",
    "Cache miss for key session_{}",
    "Timeout waiting for response from upstream",
    "Connection refused: service unavailable",
    "Disk usage at {}% on /var/log",
    "Memory allocation failed for buffer",
    "Retrying request attempt {}/3",
    "Scheduled task completed in {}ms",
    "Invalid input received from client",
    "SSL handshake failed with peer",
    "Rate limit exceeded for IP 192.168.1.{}",
    "Garbage collection took {}ms",
    "File descriptor limit approaching: {}/1024",
]

SERVICES = ["auth", "api", "db", "cache", "worker", "scheduler", "gateway"]

def generate(filepath, num_lines=500_000):
    base = datetime.datetime(2025, 1, 1, 0, 0, 0)
    with open(filepath, "w") as f:
        for i in range(num_lines):
            ts = base + datetime.timedelta(seconds=i)
            level = random.choice(LEVELS)
            svc = random.choice(SERVICES)
            msg = random.choice(MESSAGES).format(random.randint(1, 999))
            f.write(f"{ts.isoformat()} [{level:>5}] [{svc}] {msg}\n")
    print(f"Generated {num_lines:,} lines -> {filepath}")

if __name__ == "__main__":
    generate("test.log")
