# Fraud Detection — New Term Beneficiaries

Detect outbound bank transactions sent to a beneficiary the account has **never used before** — a strong fraud signal. Everything runs inside Dynatrace Automations; no external infrastructure required.

The pattern is generic: swap the banking event type for any domain that needs "known vs. unknown entity" detection (new login IPs, new API consumers, new supplier accounts, etc.).

## How it works

```
banking.transaction logs (or inline demo data)
        │
        ▼ every :01/:06/:11/...
┌─────────────────────────────┐
│  Workflow: DQL to Lookup     │
│  collectDistinct(beneficiary)│
│  → banking_beneficiaries     │  (lookup table)
└─────────────────────────────┘

        ▼ every :00/:05/:10/...  (1 min earlier)
┌─────────────────────────────┐
│  Workflow: DQL to Event      │
│  join transactions vs lookup │
│  flag is_new_beneficiary     │
│  → emit_alerts task          │
└─────────────────────────────┘
```

**Ordering is intentional.** The alert workflow runs 1 minute *before* the lookup update:
1. New beneficiary detected → alert fires.
2. Lookup updated → next cycle is clean (no repeat alert for the same beneficiary).

---

## Option 1 — Quick start (workflows + notebook only)

No scripts, no tooling. Import and run.

**Prerequisites:** a Dynatrace environment with Automations enabled.

### 1. Import the workflows

In Dynatrace → Automations → Workflows, import both files:

| File | Purpose |
|---|---|
| `workflows/dql-to-lookup-inline.yaml` | Builds/refreshes the known-beneficiary lookup (inline demo data) |
| `workflows/dql-to-event.yaml` | Detects new-term transactions and fires alerts (inline demo data) |

After import, set `owner` to your user or a service account.

> **Note:** `owner`, `actor`, and workflow `id` fields are stripped from the YAML files. Dynatrace assigns them on import.

### 2. Run the workflows

Both workflows ship with a synthetic inline `data … record(…)` block — they work immediately with no data ingest required. Run them manually to verify the end-to-end flow before enabling schedules.

### 3. Enable the schedules

- **DQL to Lookup** — :01/:06/:11/... (every 5 min, offset +1)
- **DQL to Event** — :00/:05/:10/... (every 5 min, offset +0)

Schedules are disabled by default (`isActive: false`).

### 4. Explore with the notebook

Import `notebooks/new-term-transactions.json` in Dynatrace → Notebooks to explore the detection query interactively.

---

## Option 2 — Full setup with real log data

Uses `scripts/` to seed a large beneficiary lookup and generate live incoming logs for end-to-end testing.

**Prerequisites:** `dtctl` installed and configured, Python 3.8+.

### Step 1 — Send incoming logs

```bash
# Generate and ingest 200 transactions across 20 accounts (default)
python3 scripts/generate_logs.py

# Scale up: 5000 transactions, 100 accounts
python3 scripts/generate_logs.py 5000 100
```

Prompts for an API token with `logs.ingest` scope.

### Step 2 — Bootstrap the lookup

Import and manually trigger **`workflows/dql-to-lookup-logs.yaml`** once to build the `banking_beneficiaries` lookup from the logs you just ingested. This workflow reads from `fetch logs` directly — no inline data. The lookup stores one row per account with a `beneficiaries` array built by `collectDistinct()`, which is the format the detection DQL expects.

> **Scale-test note:** `scripts/generate_beneficiaries.py` + `scripts/upload_lookup.sh` generate and upload a large flat CSV (~90 MB, 4.5M rows) to stress-test the lookup upload API. That flat format is not compatible with the detection DQL and is not needed for the detection flow.

### Step 3 — Send more logs and watch alerts fire

Log format ingested:

| Field | Example |
|---|---|
| `event.type` | `banking.transaction` |
| `account_id` | `NL00000000` |
| `beneficiary_account` | `DE00000042` |
| `transaction_id` | `TXN-20250723-0001` |
| `amount` | `1250.00` |
| `currency` | `EUR` |
| `transaction_type` | `CREDIT_TRANSFER` |
| `status` | `COMPLETED` |

Run `generate_logs.py` again. Now that the lookup is populated, ~20% of transactions (those with `XX`-prefixed beneficiaries) will trigger alerts. The rest are recognised as known.

### Step 4 — Point the workflows at real logs

Replace the `data … record(…)` block in each workflow's DQL task:

**DQL to Event** (`detect_new_term_transactions`):
```dql
fetch logs, from:now()-6m
| filter `event.type` == "banking.transaction" and status == "COMPLETED"
| lookup [load "/lookups/banking_beneficiaries"], sourceField:account_id, lookupField:account_id
| fieldsAdd is_new_beneficiary = isNull(lookup.beneficiaries) or not(in(beneficiary_account, lookup.beneficiaries))
| filter is_new_beneficiary == true
| fields timestamp, account_id, transaction_id, beneficiary_account, amount, currency, transaction_type
| sort timestamp asc
```

**DQL to Lookup** (`execute_dql_query`):
```dql
fetch logs, from:now()-24h
| filter `event.type` == "banking.transaction"
| filter status == "COMPLETED"
| summarize beneficiaries = collectDistinct(beneficiary_account),
            transaction_count = count(),
            total_outflow = sum(toDouble(amount)),
  by:{account_id}
```

### Step 5 — Extend the alert action

The `emit_alerts` task in `dql-to-event.yaml` logs flagged transactions to the workflow execution log. Extend it to send a real notification:

```typescript
// TODO: replace console.log with one of:
// - sendNotification (Davis event)
// - Slack webhook via fetch()
// - Email via Dynatrace notification action
```

---

## Adapting to other domains

| Swap | With |
|---|---|
| `banking.transaction` | Your `event.type` value |
| `beneficiary_account` | The "new entity" field to track |
| `account_id` | Your grouping key (per-user, per-tenant, etc.) |
| `banking_beneficiaries` | Your lookup table name (update workflow input) |

The lookup workflow accepts `lookup_name`, `lookup_field`, and `append` as workflow inputs — no script edits needed for basic reuse.

---

## Files

```
├── workflows/
│   ├── dql-to-lookup-inline.yaml          # Option 1: build lookup from inline demo data
│   ├── dql-to-lookup-logs.yaml     # Option 2: build lookup from real ingested logs
│   └── dql-to-event.yaml           # detect new-term transactions → alert (both options)
├── notebooks/
│   └── new-term-transactions.json  # Dynatrace notebook for interactive exploration
└── scripts/                        # Option 2 only
    ├── generate_beneficiaries.py   # generate a lookup CSV for API scale testing (~90 MB)
    ├── generate_logs.py            # generate + ingest synthetic banking transaction logs
    └── upload_lookup.sh            # upload CSV → Dynatrace lookup table via API
```
