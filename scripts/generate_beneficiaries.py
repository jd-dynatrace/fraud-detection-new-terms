#!/usr/bin/env python3
"""
Generate a representative banking beneficiary lookup CSV.

Output: one row per (account, beneficiary) pair — flat format suitable for
Dynatrace lookup upload and DQL composite-key joins.

Schema:
  account_id          originating account
  beneficiary_account destination account
  first_seen          date of first transaction to this beneficiary

Usage:
  python3 generate_beneficiaries.py [n_accounts] [output_file]

Defaults: 150_000 accounts, avg 30 beneficiaries, output to beneficiaries_lookup.csv (same folder as this script)
"""
import random
import sys
import time
import os

# ── Config ─────────────────────────────────────────────────────────────────
N_ACCOUNTS        = int(sys.argv[1]) if len(sys.argv) > 1 else 150_000
_default_output   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beneficiaries_lookup.csv")
OUTPUT            = sys.argv[2] if len(sys.argv) > 2 else _default_output
POOL_SIZE         = 500_000     # distinct beneficiary account pool
AVG_BENEFICIARIES = 30
SIGMA             = 10          # std dev — right-skewed in reality, normal is fine for load test
MAX_BENEFICIARIES = 80          # hard cap per account
FLUSH_ROWS        = 200_000     # rows per write flush
REPORT_EVERY      = 25_000      # progress report interval (accounts)

# NOTE: Dynatrace lookup tables are capped at 100 MB per file.
# At ~22 bytes/row (account_id,beneficiary_account), 100 MB ≈ 4.5M pairs.
# Default: 150K accounts × ~30 beneficiaries ≈ 4.5M rows ≈ 90 MB.
# To scale to 5M accounts you'd need 5M accounts × 30 benes = 150M rows ≈ 6 GB —
# requires chunked upload or a different lookup architecture (e.g. partitioned tables).

COUNTRY_CODES = ["NL","DE","FR","GB","BE","ES","IT","US","PL","CH","AT","SE","DK","NO","AE","SG","JP","AU","CA","ZA"]
START_DATE_OFFSET = 365 * 3     # accounts can have up to 3 years of history

# ── Build beneficiary pool ─────────────────────────────────────────────────
print(f"Building pool of {POOL_SIZE:,} beneficiary accounts...", file=sys.stderr)
cc = COUNTRY_CODES
pool = [f"{cc[i % len(cc)]}{i:08d}" for i in range(POOL_SIZE)]

# Pre-compute a simple date pool (365 date strings covering ~3 years)
import datetime
base = datetime.date(2022, 1, 1)
dates = [(base + datetime.timedelta(days=d)).isoformat() for d in range(START_DATE_OFFSET)]

# ── Generate ───────────────────────────────────────────────────────────────
print(f"Generating {N_ACCOUNTS:,} accounts (~{AVG_BENEFICIARIES} beneficiaries each)...", file=sys.stderr)
t0 = time.time()
total_rows = 0

with open(OUTPUT, "wb", buffering=64 * 1024 * 1024) as f:
    # Flat format: one row per (account, beneficiary) pair.
    # Use composite key `account_id|beneficiary_account` for DQL lookup joins.
    f.write(b"composite_key,account_id,beneficiary_account,first_seen\n")
    buf = []

    for i in range(N_ACCOUNTS):
        country = cc[i % len(cc)]
        account_id = f"{country}{i:08d}"
        n = min(MAX_BENEFICIARIES, max(1, int(random.gauss(AVG_BENEFICIARIES, SIGMA))))
        beneficiaries = random.sample(pool, n)

        for bene in beneficiaries:
            first_seen = dates[random.randrange(len(dates))]
            composite = f"{account_id}|{bene}"
            buf.append(f"{composite},{account_id},{bene},{first_seen}\n")

        total_rows += n

        if len(buf) >= FLUSH_ROWS:
            f.write("".join(buf).encode())
            buf.clear()

        if i % REPORT_EVERY == 0 and i > 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (N_ACCOUNTS - i) / rate
            print(
                f"  {i:>9,}/{N_ACCOUNTS:,}  ({100*i/N_ACCOUNTS:5.1f}%)  "
                f"{rate:>8,.0f} acc/s  ETA {eta:.0f}s",
                file=sys.stderr,
                flush=True,
            )

    if buf:
        f.write("".join(buf).encode())

elapsed = time.time() - t0
size_bytes = os.path.getsize(OUTPUT)
size_gb = size_bytes / 1024**3

print(f"\nDone in {elapsed:.1f}s", file=sys.stderr)
print(f"Rows:    {total_rows:,} ({N_ACCOUNTS:,} accounts × avg {total_rows//N_ACCOUNTS} beneficiaries)", file=sys.stderr)
print(f"File:    {OUTPUT}", file=sys.stderr)
print(f"Size:    {size_gb:.2f} GB ({size_bytes:,} bytes)", file=sys.stderr)
print(f"Rate:    {N_ACCOUNTS/elapsed:,.0f} accounts/s", file=sys.stderr)
