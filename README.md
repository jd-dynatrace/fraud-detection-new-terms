# Fraud Detection — New Term Beneficiaries

Detect outbound bank transactions sent to a beneficiary the account has **never used before** — a strong fraud signal. Everything runs inside Dynatrace Automations; no external infrastructure required.

The pattern is generic: swap the banking event type for any domain that needs "known vs. unknown entity" detection (new login IPs, new API consumers, new supplier accounts, etc.).

## How it works

```
banking.transaction bizevents (or inline demo data)
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

## Prerequisites

- A Dynatrace environment with **Automations** (Workflows) enabled
- [`dtctl`](https://docs.dynatrace.com/docs/deliver/dynatrace-cli) installed and configured (`dtctl config` must resolve your environment URL)
- Python 3.8+ (only needed if you want to generate a bulk lookup CSV for scale testing)

## Setup

### 1. Upload a seed lookup table (optional but recommended)

Generate a synthetic lookup CSV and upload it so the alert workflow has something to compare against on first run.

```bash
# Generate ~4.5M rows (150k accounts × ~30 beneficiaries, ~90 MB)
python generate_beneficiaries.py

# Upload to Dynatrace
bash upload_lookup.sh banking_beneficiaries beneficiaries.csv
# Prompts for your Bearer token — not stored anywhere.
```

Skip this step if you want the first run to flag every transaction (everything is "new").

### 2. Import the workflows

In Dynatrace → Automations → Workflows, import both files:

| File | Purpose |
|---|---|
| `workflows/dql-to-lookup.yaml` | Builds/refreshes the known-beneficiary lookup |
| `workflows/dql-to-event.yaml` | Detects new-term transactions and fires alerts |

After import, set `owner` to your user or a service account, then enable the schedules.

> **Note:** The `owner`, `actor`, and workflow `id` fields are stripped from the YAML files in this repo. Dynatrace will assign them when you import.

### 3. Enable the schedules

- **DQL to Lookup** — set to run at :01/:06/:11/... (every 5 min, offset +1)
- **DQL to Event** — set to run at :00/:05/:10/... (every 5 min, offset +0)

The schedules are disabled by default (`isActive: false`).

### 4. Point at real data

Both workflows ship with a synthetic inline `data … record(…)` block so you can run them immediately without any ingest. To switch to real business events, replace that block in each workflow's DQL task.

**DQL to Event** (`detect_new_term_transactions` task):
```dql
fetch bizevents, from:now()-6m
| filter event.type == "banking.transaction" and status == "COMPLETED"
```

**DQL to Lookup** (`execute_dql_query` task):
```dql
fetch bizevents, from:now()-24h
| filter event.type == "banking.transaction"
| filter status == "COMPLETED"
| summarize beneficiaries = collectDistinct(beneficiary_account),
            transaction_count = count(),
            total_outflow = sum(amount),
  by:{account_id}
```

Adjust `event.type` and field names to match your actual ingest schema.

### 5. Extend the alert action

The `emit_alerts` task in `dql-to-event.yaml` logs flagged transactions to the workflow execution log. Extend it to send a real notification:

```typescript
// TODO: replace console.log with one of:
// - sendNotification (Davis event)
// - Slack webhook via fetch()
// - Email via Dynatrace notification action
```

## Adapting to other domains

| Swap | With |
|---|---|
| `banking.transaction` | Your event type |
| `beneficiary_account` | The "new entity" field you want to track |
| `account_id` | The grouping key (per-user, per-tenant, etc.) |
| `banking_beneficiaries` | Your lookup table name (update workflow input) |

The lookup workflow accepts `lookup_name`, `lookup_field`, and `append` as workflow inputs — no script edits needed for basic reuse.

## Files

```
├── generate_beneficiaries.py       # generate a seed lookup CSV for scale testing
├── upload_lookup.sh                # upload CSV → Dynatrace lookup table via API
├── notebooks/
│   └── new-term-transactions.json  # Dynatrace notebook for interactive exploration
└── workflows/
    ├── dql-to-lookup.yaml          # Workflow 1: build/refresh the beneficiary lookup
    └── dql-to-event.yaml           # Workflow 2: detect new-term transactions → alert
```
