# Milford Support Desk

A small internal **support-ticket** app — a Databricks App (Streamlit) backed by
**Lakebase** (Databricks' managed PostgreSQL). Users create tickets, hold a
threaded conversation on each, change status, and delete tickets. All data is
read from and written to Lakebase — nothing is hard-coded.

> Modern-SaaS "liquid glass" UI painted in Milford's corporate palette
> (slate `#303c42`, orange `#e1690e`, cloud `#eef1f2`, product blue/green/purple).

---

## What it does

| Capability | Where |
|---|---|
| View all tickets | Left column, glass cards |
| Select a ticket & read its messages | Right column, conversation thread |
| Create a new ticket | **＋ New ticket** modal (with validation) |
| Add a message | Reply box on the ticket |
| Update a ticket's status | Status dropdown → **Update** |
| **Bonus** priority + category | Coloured badges on every ticket |
| **Bonus** filter by status/priority + title search | Toolbar |
| **Bonus** statistics dashboard | Stat tiles + status-distribution bar |
| **Bonus** delete with confirmation | **Delete** → confirm modal |
| **Bonus** input validation & friendly errors | Throughout |

## Architecture

```
Browser ──► Databricks App (Streamlit, app.py)
                  │
                  ├─ theme.py   Milford liquid-glass CSS + badges
                  └─ db.py ──►  Lakebase (PostgreSQL)
                                 tickets ─1:N─ ticket_messages
```

No passwords or secrets are stored. In the deployed app, `db.py` mints a
**short-lived OAuth token** at runtime via the Databricks SDK and uses it as the
Postgres password (`w.database.generate_database_credential(...)`).

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI |
| `db.py` | Lakebase connection + all SQL data access |
| `theme.py` | Milford palette, glass CSS, badge helpers |
| `sql/schema.sql` | `tickets` + `ticket_messages` tables |
| `sql/seed_data.sql` | 5 tickets, 2+ messages each, multiple statuses |
| `scripts/init_db.py` | One-off: applies schema + seed to Lakebase |
| `app.yaml` | Databricks Apps runtime config |
| `requirements.txt` | `streamlit`, `psycopg[binary]`, `databricks-sdk` |
| **`DEPLOY.md`** | **Step-by-step deploy runbook (start here)** |

## Deploy

Follow **[DEPLOY.md](./DEPLOY.md)** — a zero-prior-knowledge, click-by-click
runbook: create a Lakebase instance, load the schema/data, create the app,
attach the database, grant access, deploy, and test.

## Run locally (optional)

```bash
pip install -r requirements.txt

# Generate a short-lived token and point at your instance:
export LAKEBASE_INSTANCE_NAME=<your-instance>
export PGHOST=<instance-read-write-dns>
export PGDATABASE=databricks_postgres
export PGUSER=<your-databricks-username>
export PGPASSWORD=<oauth-token>        # from the Databricks CLI, 60-min lifetime
export DEV_USER=<your-email>           # identity used for created_by/author

python scripts/init_db.py              # first time only: schema + sample data
streamlit run app.py
```

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LAKEBASE_INSTANCE_NAME` | in-app | — | Instance name; used to mint token + resolve host |
| `PGHOST` | local | (SDK) | Instance read/write DNS |
| `PGPORT` | no | `5432` | |
| `PGDATABASE` | no | `databricks_postgres` | |
| `PGUSER` | local | (SDK) | Postgres role = Databricks identity |
| `PGPASSWORD` | local | (SDK-minted) | **Never set in the deployed app** |
| `PGSSLMODE` | no | `require` | |
| `DEV_USER` | no | `guest@milford.co.nz` | Local identity fallback |
