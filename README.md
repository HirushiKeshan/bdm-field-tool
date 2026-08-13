# IT WORLD Field Sales

A simple tool for field sales reps (BDMs) and their manager.

It tells each rep which shops need a visit first, shows the shop's numbers before they walk in, and turns every visit into a checklist so the manager can tell if a real conversation happened — not just a GPS ping.

**Live app**: https://bdm-field-tool-v5yti45munds6hvgsytfzt.streamlit.app/

> First open can take 30-60 seconds if the app has been asleep. Just wait and reload once.

## What's inside

- **My Visits** — every shop assigned to a rep, grouped by urgency (Slipping, Dormant, Core, New, Dormant-valuable).
- **Counter Conversation** — the screen a rep uses during a visit: this month vs last month, a 6-month trend chart, dues, last agreed action, a short checklist, an optional photo, and a code the shop owner reads out to confirm the visit really happened.
- **This Week** — a rep's own weekly summary: shops covered, money collected, orders taken, open follow-ups.
- **Insights** — one page for the manager: coverage gaps, how reps spend their time, checklist quality, dormant shops that used to be valuable, and how trustworthy the visit data is.

## Run it yourself

### Option A — Docker (easiest)

```bash
docker compose up --build
```

Open **http://localhost:8501**. This starts Postgres, loads the 4 CSVs, and starts the app.

### Option B — plain Python

```bash
pip install -r requirements.txt
cp .env.example .env        # point DATABASE_URL at your own Postgres
streamlit run app.py
```

The app loads the CSVs into the database automatically the first time it runs.

### Run the tests

```bash
pytest
```

55 tests, no database needed — they test the logic directly (segmentation, scoring, checklist rules, charts, confidence).

### Deploying it

1. Create a free Supabase project. Use its **Session pooler** connection string (not the direct one — Streamlit Cloud needs IPv4).
2. Push this repo to GitHub, deploy `app.py` on Streamlit Community Cloud, and paste the connection string as `DATABASE_URL` in the app's Secrets.
3. Done — the first load sets up the database on its own.

## Assumptions I made

The source CSVs don't say these things directly, so here's what I decided and why:

- **Which rep owns which shop** — matched by town → territory. No assignment table exists, but every town name lines up cleanly with one of the 12 rep territories once cleaned up.
- **When a shop counts as "slipping" or "dormant"** — slipping if this month is 30%+ below its own average, or it missed last month. Two or more missed months = dormant.
- **The verification code at the counter** — the CSVs don't have a printable code, so the app generates a stable 4-digit code per shop. In a real rollout this would be a printed card.
- **"Area" inside a beat** — not a real place name. It's a rough direction (north/south/east/west) worked out from the shop's coordinates, since the data has no finer location detail.
- **Dues owed** — not in the source data at all. It's a manual number the rep can type in, remembered for next time.
- **"This Week"** — the real last 7 days, not a slice of old 2026 data. It stays empty until a rep actually submits a visit.

## What I left out on purpose

- **Login** — anyone can pick any rep's name right now. Fine for 12 known people testing this; needs real auth before a real rollout.
- **A real mobile app** — this is a website, so there's nothing to install. "Add to Home Screen" gets most of the benefit.
- **Route planning** — shops are ranked by priority, not turned into a walking/driving route.
- **Working offline** — every visit needs an internet connection right now.
- **Tamil language** — reps likely want this in Tamil, not English. Not done yet.
- **Merging duplicate shops** — 20 shops in the data look like the same shop registered twice. Flagged with a warning, not auto-merged, since that's a decision for the client to make, not a script.

## Why GPS isn't used to identify which shop was visited

The brief describes shops sitting a few metres apart, too close for GPS to tell apart. That's true — a phone's GPS is accurate to about 10-50 metres, and shops sharing a wall can be 3-5 metres apart. So GPS alone can't prove which shop a rep is standing in.

Instead, the app checks a visit is real using:

1. **A code from the counter** — the shop owner reads it out, the rep types it in. This proves someone was actually standing there.
2. **What happened at the visit** — a real order, a collection, or a specific note is stronger proof than a location pin.
3. **An optional photo.**
4. **GPS as a background check only** — it's captured, but only used to flag a visit that's clearly impossible (like being 500m+ from the shop's address), never to decide which of two nearby shops was visited.

## Project layout

```
outlets.csv, bdms.csv, billing-monthly.csv, visit-log.csv   the 4 source files
db/                    database schema and queries
seed.py                loads the CSVs into Postgres
logic/                 all the business rules (segmentation, scoring, checklist, confidence)
checklists.yaml        per-shop-type checklist questions
app.py, screens/       the Streamlit app itself
tests/                 55 tests, no database needed
docs/
  data-notes.md          Phase 0 findings on the source data
  ai-log.md              a log of bugs found while building this, and how they were fixed
scripts/explore.py     the script used to explore the raw CSVs in Phase 0
docker-compose.yml, Dockerfile, .env.example
```
