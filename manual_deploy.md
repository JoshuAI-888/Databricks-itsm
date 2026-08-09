# Manual Deploy Runbook — Milford Support Desk (Databricks Web UI only)

This is a complete, click-by-click guide to deploying this repository to
Databricks using **only the Databricks web UI** — no command line, no
`databricks` CLI, no `git` command, no `pip install` on your own machine.
Everything, including running SQL, is done by clicking around in your
browser and pasting code into a Databricks notebook cell (which is not the
same thing as "using a terminal" — more on that in Step 8).

This guide assumes you have never used Lakebase or Databricks Apps before.
Every term is explained the first time it's used, and there's a glossary in
Step 2 you can jump back to.

> **This document uses placeholders everywhere a real value would normally
> go** — things like `<workspace-url>`, `<instance-name>`,
> `<service-principal-id>`, `<your-username>`. That's deliberate: this repo
> is public, and those values are specific to *your* workspace. Anywhere you
> see angle brackets `<like-this>`, replace the whole thing (brackets
> included) with your own value. Anywhere this guide shows an "example," it
> is a made-up value for illustration only — not a real hostname, ID, or
> account.

---

## Contents

0. [Before you start](#0-before-you-start)
1. [What we're building](#1-what-were-building)
2. [Glossary](#2-glossary)
3. [Create the Lakebase database instance](#3-create-the-lakebase-database-instance)
4. [Get the code into your workspace](#4-get-the-code-into-your-workspace)
5. [Create the Databricks App](#5-create-the-databricks-app)
6. [Attach the Lakebase instance as an app resource](#6-attach-the-lakebase-instance-as-an-app-resource)
7. [Point the app at your instance (edit app.yaml)](#7-point-the-app-at-your-instance-edit-appyaml)
8. [Load the schema and sample data (via a notebook)](#8-load-the-schema-and-sample-data-via-a-notebook)
9. [Grant the app's service principal access to the tables](#9-grant-the-apps-service-principal-access-to-the-tables)
10. [Deploy the app](#10-deploy-the-app)
11. [End-to-end test checklist](#11-end-to-end-test-checklist)
12. [Troubleshooting reference table](#12-troubleshooting-reference-table)
13. [Redeploying after you change code](#13-redeploying-after-you-change-code)
14. [Shutting things down (stop paying for them)](#14-shutting-things-down-stop-paying-for-them)

---

## 0. Before you start

### 0.1 What you need

- A **Databricks workspace** you can already log into in your browser (a URL
  like `https://<workspace-url>`, which on AWS deployments typically ends in
  `.cloud.databricks.com`, on Azure `.azuredatabricks.net`, or on GCP
  `.gcp.databricks.com`).
- Permission in that workspace to (a) create a **Lakebase database
  instance** and (b) create a **Databricks App**. See 0.2 to check.
- Nothing else. No local Python, no CLI, no GitHub account (the repo is
  public, so you can clone it without signing in to GitHub).

### 0.2 Checking you have permission

There's no single "Am I allowed?" page — the honest way to check is to try
the first click of each flow and see whether it lets you proceed:

1. Click the **app switcher** icon in the top-right corner of the workspace
   (a grid/squares icon) and look for **"Lakebase Postgres"** in the menu.
   Click it, then click **"Provisioned"**. If you see a **"Create database
   instance"** button and clicking it opens a form (rather than an error
   like "You don't have permission to perform this action"), you have
   Lakebase create permission.
2. From the same app switcher, click **"Databricks Apps"**. If you see a
   **"+ Create app"** button that opens a form, you have Apps create
   permission.

> **If you goes wrong:** if either button is missing, greyed out, or gives a
> permission error, you don't have the entitlement yet. Ask your workspace
> admin to grant you (or a group you're in) permission to **create Lakebase
> database instances** and **create/deploy Databricks Apps**. In most
> workspaces this is done from the workspace's admin settings under identity
> and access / entitlements — exact labels vary by Databricks version, so if
> you're the one granting access and can't find it, search your admin
> console for "entitlements" or ask Databricks support. This guide can't
> give you a precise click path here because it depends on your workspace's
> admin console version, which isn't something we can verify without access
> to one.

### 0.3 Find your own Databricks username

You'll need your exact Databricks username later (Step 8), and it can
**differ from the email address you think you use** — sometimes by as
little as one character (e.g. a workspace-specific alias). Don't guess it;
you'll read the real value directly out of a notebook in Step 8, which is
more reliable than hunting through account settings.

---

## 1. What we're building

**Milford Support Desk** is a small internal support-ticket app. People
create tickets, hold a threaded conversation on each one, change status,
and delete tickets. Every piece of that data — tickets, messages, statuses —
lives in a real Postgres database, not in the app's memory, so it survives
restarts and is shared by everyone who opens the app.

```
 ┌─────────┐        ┌──────────────────────────┐        ┌───────────────────┐
 │ Browser │ ─────► │ Databricks App            │ ─────► │ Lakebase           │
 │ (you)   │  HTTPS │ (Streamlit UI: app.py)    │  SQL   │ (managed Postgres)  │
 └─────────┘        └──────────────────────────┘        └───────────────────┘
                       runs as its own                     tables: tickets,
                       "service principal"                 ticket_messages
                       identity
```

**The one design decision that confuses people most: there is no database
password stored anywhere, ever.** Instead, every time the app needs to talk
to Postgres, it asks Databricks — via the Databricks SDK, in Python, inside
`db.py` — to mint it a brand-new **OAuth token** (a proof-of-identity string
that expires after 60 minutes) and uses that token as the Postgres
password. This happens automatically, on every connection. Nobody typed a
password into a config file; there's nothing to leak, and nothing to
rotate by hand. You'll see this exact mechanic twice in this guide: once
when the *deployed app* does it for you automatically, and once when *you*
do the same thing manually inside a notebook to run setup SQL as yourself
(Step 8).

The relevant code, in `db.py`'s `_resolve_credentials()` function, looks
roughly like this (for your reference — you don't need to edit this file):

```python
w = WorkspaceClient()
cred = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()), instance_names=[instance]
)
password = cred.token   # a 60-minute OAuth token, used as the Postgres password
```

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Workspace** | Your organization's Databricks environment — the website you log into. Has its own URL. |
| **Lakebase** | Databricks' fully managed Postgres database service. You click a button, it gives you a running Postgres server; Databricks handles patching, backups, etc. |
| **Postgres (PostgreSQL)** | A popular open-source relational (SQL) database. Lakebase *is* Postgres under the hood — anything that speaks Postgres can connect to it. |
| **Database instance** | One running Lakebase Postgres server. You name it when you create it (this guide's placeholder: `<instance-name>`). |
| **Capacity / CU** | The size of a Lakebase instance, chosen from a dropdown, measured in "Compute Units" (CU). `CU_1` is the smallest and is plenty for this app. |
| **PGHOST** | The network address (hostname) of your database instance — where Postgres connections actually go. |
| **Read/write DNS** vs **read-only DNS** | A Lakebase instance exposes two hostnames. Only the **read/write** one accepts `INSERT`/`UPDATE`/`DELETE`. Using the read-only one by mistake makes writes fail. |
| **Databricks App** | A web application (here, this Streamlit app) that Databricks hosts and runs for you, inside your workspace, with its own URL. |
| **Streamlit** | A Python framework for building simple web UIs with plain Python — no HTML/JS needed. It's what renders every screen of this app. |
| **Service principal** | A non-human ("robot") identity. Every Databricks App gets one automatically when it's created; the app runs *as* this identity, not as you. It has its own ID (a UUID) and its own permissions. |
| **Client ID** | The service principal's UUID — its unique identifier, e.g. (made-up example) `a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d`. This value doubles as the name of its Postgres role (see below). |
| **OAuth token** | A temporary, auto-expiring (60-minute) proof of identity that Databricks issues. Used here as the Postgres password instead of a fixed secret. |
| **App resource** | Something a Databricks App is explicitly allowed to use — here, a Lakebase database instance. Attaching a resource is what lets the app's service principal request tokens for that instance at all. |
| **Git folder** | A folder in your Databricks Workspace that's a live clone of a Git repository (GitHub, in this case). Lets you get code into Databricks without a local terminal or `git` command. |
| **Role** (Postgres) | A Postgres user/identity that can own objects, log in, and be granted privileges. Both humans and service principals get roles. |
| **Grant** | A permission given to a role — e.g. "role X may `SELECT` from table Y." Without a grant, even a role that can log in gets `permission denied`. |
| **Schema** (Postgres) | A namespace inside a database that groups tables together. This app uses the default schema, called `public`. (Not to be confused with `sql/schema.sql`, the *file* that defines this app's tables.) |
| **Notebook** | A Databricks page where you write and run code in cells, interactively, in your browser. This is how we'll run SQL setup steps without a terminal. |
| **Instance owner** | Whoever ran the `CREATE TABLE` statements owns the resulting tables in Postgres — by default, only the owner (and superusers) can touch them. That's why the service principal needs explicit grants even though the tables clearly "belong" to this app. |

---

## 3. Create the Lakebase database instance

A **database instance** is a running Lakebase (Postgres) server. You create
exactly one for this app.

**3.1 — Open Lakebase.** Click the **app switcher** icon (top right of the
workspace) → **"Lakebase Postgres"** → **"Provisioned"**.

> If your workspace's menu labels look different, look for anything
> mentioning "Lakebase" or "Database instances" — this is a newer area of
> the product and label wording has moved around across releases. If you
> genuinely can't find it, search the top workspace search bar for
> "database instance".

**3.2 — Start creation.** Click **"Create database instance"**.

**3.3 — Fill in the form:**

| Field | What to enter | Why |
|---|---|---|
| **Name** | A short name, 1–63 characters, **letters and hyphens only** (no underscores, no spaces). Example: `support-lakebase`. | This becomes `<instance-name>` for the rest of this guide — you'll type it again later, so pick something memorable. |
| **Capacity** | Choose **`CU_1`** (the smallest option) from the dropdown. | See the warning box below. |
| **Serverless usage policy** | Leave as default/blank unless your org requires budget attribution. | Optional. |
| **Advanced Settings** ("Create from parent", "Enable HA") | Leave collapsed / default. | Not needed for this app. |

> **This field is not actually optional, even though it might look like it.**
> A real deployment of this exact app hit `Field instance.capacity must be
> defined` when capacity was left unset. In the UI, "Capacity" is a
> dropdown that defaults to **2 CU** — but explicitly picking the smallest
> option, **`CU_1`**, is enough for this app (a handful of users, a couple
> of small tables) and costs less. Don't leave this field untouched and
> assume a default will silently apply — make sure a value is visibly
> selected before you click Create.

**3.4 — Click "Create".**

**3.5 — Wait for it to become Available.** This can take a few minutes.
The instance list (or the instance's own page) shows a status badge —
watch for it to change from something like "Starting"/"Creating" to
**Available**.

> **How to tell it worked:** the instance's status badge reads
> **Available**, and clicking into the instance shows a detail page with
> connection information.
>
> **If it goes wrong:** if creation fails immediately, re-check the Name
> field (letters/hyphens only, ≤63 chars) and make sure Capacity has a
> value selected, then try again.

**3.6 — Record the read/write DNS hostname (this is your `PGHOST`).** On the
instance's detail page, find the connection information — look for a field
labeled something like **"read/write DNS"** or **"Connection endpoint"**.
It looks like `ep-<some-words>-<id>.database.<region>.cloud.databricks.com`
(a made-up example — yours will differ). **Write this value down.**

> **This is the single easiest mistake to make in this whole guide.** The
> instance page shows **two** hostnames: a read/write one and a read-only
> one. This app needs the **read/write** one, because it inserts, updates,
> and deletes rows. If you accidentally copy the read-only hostname, the
> app will be able to *load* tickets but every create/update/delete will
> fail. If something that should be a write mysteriously fails later, this
> is the first thing to double check.

### Record these values before moving on

| Value | What it is | Example (made up) |
|---|---|---|
| `<instance-name>` | The name you chose in 3.3 | `support-lakebase` |
| `<PGHOST>` | The **read/write** DNS hostname from 3.6 | `ep-still-cloud-1234.database.us-east-1.cloud.databricks.com` |

> **Tip:** if you name your instance exactly `support-lakebase`, you can
> skip part of Step 7 later — `app.yaml` in this repo already defaults
> `LAKEBASE_INSTANCE_NAME` to that value. Any other name means you'll edit
> that one line.

---

## 4. Get the code into your workspace

The repo lives on GitHub. Without a terminal, the cleanest way to get it
into Databricks — and to keep it easy to pull future updates — is a **Git
folder**: a workspace folder that's a live clone of the GitHub repo.

**4.1 — Open the Workspace browser.** In the left sidebar, click
**"Workspace"**.

**4.2 — Navigate to your home folder** (usually shown as **Users →
`<your-username>`**, or simply click "Home" if shown).

**4.3 — Create the Git folder.** Click **"Create"** → **"Git folder"**.
(In some Databricks versions this may still say **"Repo"** — it's the same
feature, renamed.)

**4.4 — Fill in the dialog:**

| Field | Value |
|---|---|
| **Git repository URL** | `https://github.com/JoshuAI-888/Databricks-itsm.git` |
| **Git provider** | GitHub |
| **Git folder name** | Leave the suggested name (e.g. `Databricks-itsm`), or pick your own. |

Leave "Sparse checkout mode" off — you want the whole repo.

**4.5 — Click "Create"** (or "Create Git folder"). Databricks clones the
repository into your workspace.

**How to tell it worked:** a new folder appears under your Workspace home,
and opening it shows the repo's files — `app.py`, `db.py`, `app.yaml`,
`requirements.txt`, a `sql/` folder, a `scripts/` folder, etc.

**If it goes wrong:**
- *"Repository not found" / clone fails* — double-check you typed the URL
  exactly, including `.git` at the end, and that your workspace has
  outbound network access to GitHub (ask an admin if it's on a locked-down
  network).
- *You don't see a "Git folder" option at all* — try "Repo" instead; some
  workspace versions haven't renamed it yet.

**4.6 — Note the full workspace path.** It will be:

```
/Workspace/Users/<your-username>/<git-folder-name>
```

For example (made up): `/Workspace/Users/jsmith/Databricks-itsm`. You'll
need this path in Steps 8 and 10.

> **Alternative if Git folders aren't available to you:** you can also
> create an empty folder under Workspace → your home folder, then use
> **Upload** (drag-and-drop, or the "⋮" menu → "Upload files") to manually
> upload each file from a local copy of the repo, preserving the folder
> structure (`sql/schema.sql` must end up at `sql/schema.sql` relative to
> the folder root, etc.). This works but you lose the ability to pull
> future updates with a click — prefer the Git folder if you can.

---

## 5. Create the Databricks App

**5.1 — Open Databricks Apps.** Click the **app switcher** icon (top right)
→ **"Databricks Apps"**.

**5.2 — Click "+ Create app"**.

**5.3 — Choose a blank/custom app, not a template.** You should see a
choice between pre-built templates (things like a "Gradio Hello world"
sample) and a plain custom option — click the **custom app** option (it may
be labeled **"Create a custom app"** or similar). You're bringing your own
code, so you don't want a template.

> If the exact wording differs in your workspace, look for anything that
> implies "start from scratch" / "bring your own app" rather than a named
> sample template.

**5.4 — Name it.** Enter a name — for example `milford-support-desk`. App
names are typically restricted to lowercase letters, numbers, and hyphens.
Optionally add a description like "Milford Support Desk — ticket tracker."

**5.5 — Skip or configure the Git step.** You may be offered a "Configure
Git" step here. Since you already created a Git folder in Step 4, you can
skip this and point the app at that folder later during deployment (Step
10) — or, if the app-creation wizard lets you pick a workspace path right
now, you can point it at the Git folder path from 4.6 immediately. Either
order works.

**5.6 — Skip advanced configuration for now.** You'll attach the database
resource in the next step, so you can click through any "resources /
authorization / compute" screen without adding anything yet, or add the
resource here if the option is in front of you — either is fine.

**5.7 — Click "Create app".**

**How to tell it worked:** you land on the app's detail page, and its
status shows something like "Not deployed" / "Created" (this is expected —
Databricks creates the app but does not deploy any code yet).

**5.8 — Find and copy the service principal's client ID.** On the app's
detail page, look for the app's identity — it may be under a label like
**"Authorization"**, **"App details"**, **"Service principal"**, or shown
next to a **"Client ID"** field. It's a UUID, formatted like this made-up
example: `a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d`. **Copy it and write it
down** — this is `<service-principal-id>`, needed in Steps 6 and 9.

> **If it goes wrong / you can't find it:** the exact tab name for this
> varies by Databricks release, and this guide can't promise the current
> label with certainty — if "Authorization" isn't there, look for any
> section mentioning "Service principal," "Client ID," or "App identity" on
> the app's detail or settings page. It is always shown somewhere on that
> page; Databricks creates one automatically for every app, you cannot miss
> it entirely.

### Record this value

| Value | What it is |
|---|---|
| `<service-principal-id>` | The app's auto-created service principal client ID (a UUID), from 5.8 |

---

## 6. Attach the Lakebase instance as an app resource

This is the step that lets the app's service principal request database
tokens at all. Skipping it is a common failure mode — see the callout
below.

**6.1 — On the app's detail page, find "Resources"** (sometimes labeled
"App resources" or "Dependencies").

**6.2 — Click "+ Add resource"** (or "Edit").

**6.3 — Choose "Database instance"** as the resource type.

**6.4 — Select your instance**, `<instance-name>` from Step 3, from the
list. You may be asked to name this resource reference (a short key like
`lakebase`) and to set a permission level — choose one that allows both
connecting and creating (sometimes shown as "Can connect and create").

**6.5 — Save.**

**How to tell it worked:** the Resources section now lists your Lakebase
instance.

> **Important thing this step does for you, invisibly:** attaching the
> instance here **automatically creates a matching Postgres role** for the
> app's service principal, named exactly `<service-principal-id>` (the same
> UUID from Step 5.8), with login privileges. You are not going to manually
> `CREATE ROLE` for it later in Step 9 — that step is written expecting you
> to discover the role already exists and skip that part. This is expected
> and correct, not a bug.
>
> **If it goes wrong — the failure this step exists to prevent:** if you
> *skip* attaching the instance as a resource, the app has no authorization
> to mint database tokens at all, no matter how perfect your `GRANT`
> statements are later. The symptom is confusing: manual steps you ran
> yourself (Step 8, Step 9) work fine, because you were connecting as
> *yourself*, but the *deployed app* can't connect at all. If you ever see
> "local scripts / notebook worked, but the deployed app can't reach the
> database," come back here first and confirm the instance is listed under
> Resources.

---

## 7. Point the app at your instance (edit app.yaml)

`app.yaml` in the repo controls how the app starts and which environment
variables it sees. You need it to reference the exact instance name you
chose in Step 3.

**7.1 — Open the file in your Git folder.** In the Workspace browser,
navigate to your Git folder (Step 4) and open `app.yaml`. Click on it to
open Databricks' built-in file editor.

**7.2 — Check the `LAKEBASE_INSTANCE_NAME` value.** The file ships with:

```yaml
env:
  - name: "LAKEBASE_INSTANCE_NAME"
    value: "support-lakebase"
```

If you named your instance `support-lakebase` in Step 3, this is already
correct — skip to 7.3. Otherwise, **edit the value** to your exact
`<instance-name>`, e.g.:

```yaml
  - name: "LAKEBASE_INSTANCE_NAME"
    value: "<instance-name>"
```

**7.3 — (Optional) Set `PGHOST` explicitly.** You do **not** need to. If
`PGHOST` is unset, `db.py` looks the read/write hostname up through the SDK
using `LAKEBASE_INSTANCE_NAME`, and refuses to start if it can't find a
read/write endpoint — it will never quietly connect you to the read-only one.
Leaving it unset is the more portable choice, because `app.yaml` then contains
no environment-specific hostnames and the same file works in any workspace.

Set it only if you want to skip that one lookup at startup, or you're pinning
to a specific endpoint. If you do, add it to the same `env:` block:

```yaml
  - name: "PGHOST"
    value: "<PGHOST>"
```

using the **read/write** DNS hostname from Step 3.6 — never the read-only one.

> Prefer keeping real hostnames out of the repo if it's public. The app's own
> **Environment** settings in the Databricks UI are a better home for them than
> a committed file.

**7.4 — Leave everything else alone**, especially:

```yaml
command:
  - "streamlit"
  - "run"
  - "app.py"
  - "--server.port=8000"
  - "--server.address=0.0.0.0"
```

> **Do not change the port.** Databricks Apps only routes incoming traffic
> to **port 8000**. If this line is changed or removed, the deployed app
> will show a blank page or "site can't be reached" even though it's
> technically running.

Also leave `PGPASSWORD` unset — it should not appear in this file at all.
That's intentional (Step 1's design point): the deployed app mints its own
token every time it connects.

**7.5 — Save the file** (the editor typically auto-saves; look for a
"saved" indicator, or use the editor's save action if one is shown).

**How to tell it worked:** reopening `app.yaml` shows your edited values.

**If it goes wrong:** if the file editor won't let you save, check you
have write access to the Git folder (you should, since you created it in
Step 4). YAML is indentation-sensitive — make sure your edited lines keep
the same indentation (two spaces) as the surrounding lines.

---

## 8. Load the schema and sample data (via a notebook)

Now you'll create the two tables this app needs (`tickets`,
`ticket_messages`) and load sample rows. There's no SQL-editor-only way to
do this reliably here, because a later step (Step 9) requires running as
**you** specifically — you need to be the owner of these tables for the
`GRANT` statements to work, and a notebook lets you authenticate as
yourself and run arbitrary Python + SQL together. This is also exactly the
mechanism the deployed app itself uses (Step 1) — minting your own
short-lived token via the Databricks SDK — so this step doubles as a good
way to see that mechanism in action.

> A **notebook** here is not a terminal. It's a normal Databricks workspace
> page where you write small blocks of code ("cells") and click a ▶ button
> (or press Shift+Enter) to run each one, entirely in your browser.

**8.1 — Create the notebook.** In the Workspace browser, go to your home
folder → **Create** → **Notebook**. Give it a name like `lakebase-setup`,
and make sure the language is set to **Python**.

**8.2 — Attach it to a running cluster / SQL warehouse compute.** If
prompted to attach compute, pick any small running cluster in your
workspace. If you don't have one, you may need to create one, or ask an
admin — any general-purpose cluster works, this notebook does very little
computation.

**8.3 — Cell 1: install the Postgres driver.** psycopg is Python's
standard Postgres client library; it's not preinstalled on Databricks
clusters. Paste this into the first cell and run it:

```python
%pip install "psycopg[binary]"
dbutils.library.restartPython()
```

`restartPython()` is required after `%pip install` so the new package is
actually importable in the next cell.

**How to tell it worked:** the cell finishes without a red error, and
you'll typically see the Python kernel restart (a short pause, then
"Python interpreter restarted").

**8.4 — Cell 2: connect, minting your own token.** Fill in the two
placeholders at the top, then run:

```python
INSTANCE_NAME = "<instance-name>"    # from Step 3
PGHOST = "<PGHOST>"                  # the read/write DNS hostname from Step 3.6

import uuid
from databricks.sdk import WorkspaceClient
import psycopg

w = WorkspaceClient()
me = w.current_user.me().user_name
print("Connecting as:", me)          # this IS your exact Databricks username — see Step 0.3

cred = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()),
    instance_names=[INSTANCE_NAME],
)

conn = psycopg.connect(
    host=PGHOST,
    port=5432,
    dbname="databricks_postgres",
    user=me,
    password=cred.token,   # a fresh 60-minute OAuth token, not a stored password
    sslmode="require",
    autocommit=True,
)
print("Connected.")
```

**How to tell it worked:** the cell prints your username and then
`Connected.` with no error.

**If it goes wrong:**
- `password authentication failed` — usually means `PGHOST` is wrong
  (double check you used the read/write DNS, not read-only, and that you
  copied it exactly), or the token expired between generating it and
  connecting (rare — just re-run the cell to mint a fresh one).
- Any error mentioning connection timeout / could not connect — check
  `PGHOST` for typos, and confirm the instance status is **Available**
  (Step 3.5).
- `ModuleNotFoundError: No module named 'psycopg'` — Cell 1 didn't finish,
  or you ran this cell before the Python restart completed. Re-run Cell 1,
  wait for it to fully finish, then re-run this cell.

**8.5 — Cell 3: run the schema and sample-data SQL files.** This reads the
`.sql` files straight out of your Git folder from Step 4 and executes them.
Replace the `SQL_FOLDER` path with your actual Git folder path from Step
4.6:

```python
from pathlib import Path

SQL_FOLDER = "/Workspace/Users/<your-username>/<git-folder-name>/sql"

for filename in ["schema.sql", "seed_data.sql"]:
    sql_text = Path(f"{SQL_FOLDER}/{filename}").read_text()
    conn.execute(sql_text)
    print(f"{filename}: done")
```

> **`seed_data.sql` starts with a `TRUNCATE` statement.** Specifically:
> `TRUNCATE ticket_messages, tickets RESTART IDENTITY CASCADE;`. That line
> **deletes all existing rows** in both tables before inserting the 5
> sample tickets. It's meant to be safe to re-run for a clean demo dataset
> — but if you ever have real ticket data you care about, **do not re-run
> `seed_data.sql`**, or you will destroy it. There is no undo.

**How to tell it worked:** you see `schema.sql: done` then `seed_data.sql:
done` printed, with no error in between.

**8.6 — (Optional) Cell 4: load extra sample tickets for reporting.** The
repo also includes `sql/seed_more_tickets.sql` — 50 additional tickets
spread across the last year, useful if you want more data to look at in
the stats dashboard. Unlike `seed_data.sql`, **this one is additive and
safe to re-run** — it checks for existing titles before inserting, so
running it twice doesn't create duplicates:

```python
sql_text = Path(f"{SQL_FOLDER}/seed_more_tickets.sql").read_text()
conn.execute(sql_text)
print("seed_more_tickets.sql: done")
```

**8.7 — Cell 5: verify.** Confirm the row counts:

```python
tickets = conn.execute("SELECT count(*) FROM tickets").fetchone()[0]
messages = conn.execute("SELECT count(*) FROM ticket_messages").fetchone()[0]
print(f"{tickets} tickets, {messages} messages")
```

**How to tell it worked:** you see a count of `5` tickets (or `55` if you
ran 8.6) and a nonzero message count, matching the sample data.

> **Keep this notebook open** — you'll come back to it in Step 9 to run the
> `GRANT` statements, reusing the same `conn` object. If you close it or
> your session times out, just re-run Cells 1–2 (Cell 1 only if the
> environment fully reset) to reconnect before continuing.

---

## 9. Grant the app's service principal access to the tables

This is the single most common failure point in the entire deployment.
Skip it, and the deployed app will load its UI fine but every action that
touches the database fails with `permission denied for table tickets`.

**Why this is necessary:** you (a human) created the `tickets` and
`ticket_messages` tables in Step 8, connected as yourself. In Postgres, the
creator of a table is its **owner**, and only the owner (or a superuser)
can touch it by default — nobody else, not even a role that can log in
successfully, can read or write it without an explicit `GRANT`. Databricks
automatically created a Postgres role for the app's service principal when
you attached the Lakebase resource (Step 6) — but Databricks has no way of
knowing you want that role to be able to touch *your* tables, so it does
not grant anything on your behalf. That's on you, right here.

**9.1 — Go back to your notebook from Step 8** (same one, same open `conn`
connection — if you closed it, redo Cell 2 from Step 8.4 to reconnect
first).

**9.2 — New cell: check whether the role already exists.** Fill in your
`<service-principal-id>` from Step 5.8:

```python
SP_ID = "<service-principal-id>"    # from Step 5.8, the app's Client ID

row = conn.execute(
    "SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname = %s", (SP_ID,)
).fetchone()
print(row)
```

**Read the output before continuing:**

- **If it prints a row** (something like
  `('a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d', True)`) — the role already
  exists. This is the **expected, normal case** if you completed Step 6
  (attaching the Lakebase resource auto-creates it). **Skip the
  `CREATE ROLE` statement below entirely** — running it anyway will fail
  with `role "..." already exists`, which is harmless but pointless.
- **If it prints `None`** — the role doesn't exist yet, most likely because
  Step 6 wasn't completed. Go back and do Step 6 first if you haven't, or
  proceed to create the role manually below if you have a reason not to
  attach the resource yet.

**9.3 — New cell: create the role only if 9.2 printed `None`.**

```python
if row is None:
    conn.execute(f'CREATE ROLE "{SP_ID}" WITH LOGIN;')
    print("Role created.")
else:
    print("Role already exists — skipping CREATE ROLE.")
```

**9.4 — New cell: grant privileges (always run this part).** The UUID is
double-quoted in every statement — a bare UUID like `a1b2c3d4-...` is not a
valid Postgres identifier without quotes, since it starts with digits and
contains hyphens:

```python
conn.execute(f'GRANT USAGE ON SCHEMA public TO "{SP_ID}";')
conn.execute(f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{SP_ID}";')
conn.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{SP_ID}";')
conn.execute(
    f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO "{SP_ID}";'
)
conn.execute(
    f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "{SP_ID}";'
)
print("Grants applied.")
```

What each statement does, in plain English:

| Statement | Plain English |
|---|---|
| `GRANT USAGE ON SCHEMA public` | "You're allowed to even look inside the `public` schema at all." Without this, table-level grants don't matter — the role can't reach them. |
| `GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public` | Read/write/etc. on the tables that exist **right now** (`tickets`, `ticket_messages`). |
| `GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public` | Lets the app generate new auto-incrementing IDs (`ticket_id`, `message_id`) when it inserts rows. Without this, inserts fail even with table `INSERT` rights. |
| The two `ALTER DEFAULT PRIVILEGES` statements | "Apply these same grants automatically to any table/sequence **created in the future**." Not strictly required today (the schema won't change itself), but cheap insurance if you ever add tables. |

**9.5 — New cell: verify the grant actually landed.** Do this before
deploying — it's much faster to debug here than inside a deployed app:

```python
check = conn.execute(
    "SELECT has_table_privilege(%s, 'tickets', 'SELECT') AS can_read, "
    "has_table_privilege(%s, 'tickets', 'INSERT') AS can_write",
    (SP_ID, SP_ID),
).fetchone()
print(check)
```

**How to tell it worked:** both `can_read` and `can_write` print as `True`
(Postgres `t`).

**If it goes wrong:**
- Either value prints `False` — re-run Cell 9.4. Common causes: you pasted
  the wrong UUID (double-check against Step 5.8, don't confuse it with the
  instance name or your own username), or a stray typo dropped a quote
  mark.
- `role "..." already exists` from the `CREATE ROLE` statement — this is
  expected per 9.2/9.3 if you didn't check first; it's harmless, just move
  on to 9.4.
- Any authentication error at this point — your token from Cell 2 (Step
  8.4) may have expired (60-minute lifetime). Re-run that cell to mint a
  fresh one, then retry.

You're done with the notebook now.

---

## 10. Deploy the app

**10.1 — Go back to the app's detail page** (app switcher → Databricks Apps
→ click your app's name).

**10.2 — Click "Deploy".**

**10.3 — Point it at your code.** You'll be asked to choose a source —
pick your Git folder from Step 4, using the full path recorded in 4.6:

```
/Workspace/Users/<your-username>/<git-folder-name>
```

**10.4 — Confirm / start the deployment.** Databricks will install
everything listed in `requirements.txt` (`streamlit`, `psycopg[binary]`,
`databricks-sdk`) automatically as part of deploying — you do not install
anything yourself.

**10.5 — Watch the build/deploy logs.** The app's page typically shows a
**"Logs"** tab or a live deployment status. Wait for it to reach a
"Running" / successful state.

> **Benign warning you will very likely see in the build log — ignore it:**
>
> ```
> fastapi 0.115.0 requires starlette<0.39.0, but you have starlette 1.3.1
> ```
>
> This happens because Streamlit pulls in a newer `starlette` version than
> the one bundled with the Apps base image expects for `fastapi`. Nothing
> in this app uses `fastapi` directly. It's noise, not a failure — the
> deployment completes successfully despite this line. Don't spend time
> chasing it.

**How to tell it worked:** the app's status shows **Running** (or
equivalent), and the app page shows a clickable **URL**.

**If it goes wrong:**
- **Blank page / "site can't be reached" when you open the URL** — almost
  always the port. Re-open `app.yaml` (Step 7) and confirm the command
  still ends in `--server.port=8000 --server.address=0.0.0.0`, exactly as
  shipped. Databricks Apps only forwards traffic to port 8000; anything
  else looks like the app isn't there at all.
- **App loads but shows a connection/database error** — check that
  `LAKEBASE_INSTANCE_NAME` (and `PGHOST`, if you set it) in `app.yaml`
  match your real instance (Step 7), and that the Lakebase instance is
  actually listed under the app's Resources (Step 6).
- **`permission denied for table tickets`** anywhere in the app — go back
  to Step 9; the grants either weren't run, or were run against the wrong
  service-principal ID.
- **Deploy step itself fails before the app even starts** — re-check the
  workspace path in 10.3 for typos; it must point at the folder that
  directly contains `app.yaml`, not a subfolder or the parent.

---

## 11. End-to-end test checklist

Open the app's URL from Step 10.5. Each item below exercises the database —
passing all of them proves data is really persisted in Lakebase, not just
held in the app's memory for the current browser tab.

- [ ] **Existing tickets load.** You see the 5 sample tickets from Step
  8.5 (or 55, if you also ran 8.6).
- [ ] **Create a new ticket.** Use the **＋ New ticket** button, fill in the
  form, submit — it appears in the list immediately.
- [ ] **Add a message.** Open any ticket, post a reply — it appears in the
  thread.
- [ ] **Update a ticket's status.** Change a status (e.g. Open → Closed)
  and confirm — the new status sticks and shows on the ticket.
- [ ] **Delete a ticket.** Delete one, confirm the confirmation prompt —
  it disappears from the list.
- [ ] **Refresh the browser tab.** Reload the page (F5 / Cmd+R) and confirm
  every single change above is *still there*. **This is the real test.**
  If the new ticket, the new message, the status change, and the deletion
  all survive a full page reload, the data is genuinely stored in
  Lakebase — not just sitting in the Streamlit session for your one tab.

If everything above holds up after a refresh, the deployment is complete
and working end to end.

---

## 12. Troubleshooting reference table

| Symptom | Cause | Fix |
|---|---|---|
| `Field instance.capacity must be defined` while creating the Lakebase instance | The Capacity dropdown was left unselected. | Go back to Step 3.3 and explicitly pick `CU_1` (or any capacity) before clicking Create. |
| `permission denied for table tickets` (or `ticket_messages`) in the running app | The service principal's role has no grants on the tables — the single most common failure. | Redo Step 9 with the exact `<service-principal-id>` from Step 5.8. Verify with the query in 9.5. |
| `role "<uuid>" already exists` while running `CREATE ROLE` | Attaching the Lakebase instance as an app resource (Step 6) already created this role automatically. | Expected and harmless. Skip `CREATE ROLE` and go straight to the `GRANT` statements (Step 9.4). |
| `password authentication failed` (in the setup notebook) | Wrong `PGHOST` (often the read-only DNS instead of read/write), a typo, or your 60-minute OAuth token expired. | Re-check `PGHOST` against Step 3.6 (must be the read/write hostname). Re-run the connection cell (Step 8.4) to mint a fresh token. |
| Deployed app can't reach the database at all, but the setup notebook worked fine | The Lakebase instance was never attached to the app as a **resource** — without that, the app's service principal cannot mint tokens for it, no matter how correct the grants are. | Go to Step 6 and confirm the instance is listed under the app's Resources. |
| Blank page, or "This site can't be reached," when opening the app URL | Wrong port in `app.yaml`, or the port flags were edited/removed. | Confirm `app.yaml`'s command ends with `--server.port=8000 --server.address=0.0.0.0` exactly (Step 7.4). Databricks Apps only routes to port 8000. |
| `fastapi 0.115.0 requires starlette<0.39.0, but you have starlette 1.3.1` in the build log | Streamlit pulls a newer `starlette` than the base image expects for an unrelated package (`fastapi`), which this app doesn't use directly. | Harmless. Ignore it — deployment still succeeds. |
| All your ticket data is suddenly gone after re-running setup | `sql/seed_data.sql` begins with `TRUNCATE ticket_messages, tickets RESTART IDENTITY CASCADE;`, which wipes both tables before reloading sample rows. | This is expected behavior of that file, not a bug — it's designed to reset to a clean demo dataset. Never re-run it once you have real data you want to keep. `sql/seed_more_tickets.sql` is safe to re-run (additive, no truncate). |
| `ModuleNotFoundError: No module named 'psycopg'` in the setup notebook | `%pip install` cell (8.3) wasn't run, or the Python restart from `dbutils.library.restartPython()` hadn't finished before the next cell ran. | Re-run Cell 1 (8.3) fully, wait for the restart to complete, then re-run the connection cell. |
| Any `permission denied` / auth error that appears only after the notebook had been open a while | The 60-minute OAuth token from `generate_database_credential` expired. | Re-run the connection cell (Step 8.4) to mint a fresh token, then retry the failing cell. |
| `password authentication failed` and you're sure `PGHOST`/token are right | The Postgres username in use isn't the one you think — Databricks usernames can differ slightly from the email you expect. | Trust the value printed by `w.current_user.me().user_name` in Step 8.4's output over any assumption. |

---

## 13. Redeploying after you change code

If you (or someone else) edits any file in the Git folder — `app.py`,
`db.py`, `theme.py`, `app.yaml`, etc. — the running app does **not**
automatically pick up the change. To redeploy:

1. If you edited files directly in the Databricks file editor inside the
   Git folder, your changes are already saved there — no extra step
   needed. If instead you pushed new changes to the GitHub repo itself,
   open the Git folder in the Workspace browser and use its **Git** panel
   (branch selector / "Pull" button) to pull the latest commit first.
2. Go to the app's detail page (app switcher → Databricks Apps → your
   app).
3. Click **"Deploy"** again, and confirm the same source path from Step
   10.3 (`/Workspace/Users/<your-username>/<git-folder-name>`).
4. Wait for the new deployment to reach **Running**, same as Step 10.5.

Any changes to `app.yaml`'s `env:` block (like a different instance name
or `PGHOST`) also require a redeploy to take effect — editing the file
alone doesn't restart the running app.

---

## 14. Shutting things down (stop paying for them)

Both the Databricks App and the Lakebase instance can incur ongoing cost
while running. To tear down what you built in this guide:

**Stop or delete the app:**
1. App switcher → Databricks Apps → open your app.
2. Look for a **"Stop"** action to pause it without deleting it (keeps
   configuration and history, no compute cost while stopped), or a
   **"Delete"** action (in a "⋮" / overflow menu, or the app's settings) to
   remove it entirely, including its auto-created service principal.

**Delete the Lakebase instance** (this permanently deletes all ticket
data — make sure you don't need it first):
1. App switcher → Lakebase Postgres → Provisioned.
2. Select your `<instance-name>` instance.
3. Look for a **"Delete"** action, typically in a "⋮" overflow menu on the
   instance's row or detail page.
4. Confirm the deletion when prompted (it will likely ask you to type the
   instance name to confirm — this is a destructive, irreversible action).

> **If it goes wrong / you can't find Delete:** deletion actions are
> sometimes restricted to whoever created the resource, or to workspace
> admins. If the option isn't there for you, ask whoever has admin rights
> on the workspace to remove it.

There's no need to separately "delete" the Git folder unless you want to —
it's just workspace files and doesn't incur its own runtime cost.
