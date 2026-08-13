# IT WORLD Field Sales

A field-sales tool for IT WORLD's field executives and the outlets they cover. It ranks each rep's visit list by what actually needs attention, gives them the outlet's numbers and last agreed action before they open their mouth at the counter, and turns the checklist outcome into evidence for whether a visit really happened. Built for the rep first — every number in Insights traces back to the same data the rep screens already use, not a separate rollup. Colors and wordmark are drawn from [it-world.in](https://it-world.in)'s public brand (navy, magenta accent).

**Live**: https://bdm-field-tool-v5yti45munds6hvgsytfzt.streamlit.app/

**A note on scope, for anyone comparing this against the original brief**: that brief argued the manager-facing view should be a low-key, secondary link rather than an equal navigation tab ("manager visibility is a byproduct... never the primary design goal"). It shipped that way initially. It was then explicitly promoted to a full tab (**Insights**, alongside **My Visits** and **This Week**) at the requester's direction, after that tradeoff was flagged — logged here for anyone auditing the decision trail, not as a disagreement with the reasoning.

## Run it in under 15 minutes

The live link above is already running against a seeded database — open it and pick any name from the dropdown. To run your own copy:

### Option A — Docker (recommended, ~3 minutes)

```bash
docker compose up --build
```

This starts Postgres, seeds it from the four CSVs, and starts the app. Open **http://localhost:8501**. First run takes a minute or two to build the image; `docker compose up` again after that is fast.

### Option B — bare Python (~5 minutes, needs a Postgres somewhere)

```bash
pip install -r requirements.txt
cp .env.example .env        # edit DATABASE_URL if you're not using the docker-compose Postgres
streamlit run app.py
```

The app seeds the database itself on first load if it's empty (schema + all four CSVs) — no separate `python seed.py` step needed, though `python seed.py` still works standalone if you'd rather run it explicitly (e.g. to see the coercion summary printed to a terminal, or to re-run it after editing a CSV). `.env.example` has a working default matching `docker-compose.yml`'s Postgres service (`postgresql://bdm:bdm@localhost:5432/bdm_tool`) — if you don't already have Postgres running locally, `docker compose up postgres` starts just the database and leaves the app to you.

### Running the tests

```bash
pip install -r requirements.txt
pytest
```

38 tests, no database required — they exercise the pure logic modules (`logic/segmentation.py`, `logic/scoring.py`, `logic/normalize.py`, `logic/checklist.py`) directly, including one that runs segmentation against the real `outlets.csv`/`billing-monthly.csv` and asserts every one of the 820 outlets lands in exactly one segment.

### Deploying it live

1. Create a free Supabase project. Use its **Session pooler** connection string (Project Settings → Database → Connect → Session pooler), not the direct connection — the direct one is IPv6-only unless you pay for Supabase's IPv4 add-on, and Streamlit Community Cloud's network is IPv4.
2. Push this repo to GitHub, deploy `app.py` on Streamlit Community Cloud, and paste that connection string as `DATABASE_URL` under the app's Secrets.
3. That's it — first load seeds the empty database automatically (see `app.py::_ensure_seeded`), the same idempotent path `seed.py` uses standalone.

## Who this is for

The field executive opening it on their phone before a counter visit, and — only because that rep is now actually using it — the manager who couldn't previously tell who was visited, whether the conversation happened, or which of two identically-registered outlets a visit log entry actually meant (see "The Madurai decision" below for the specific 20 pairs this turned out to be).

## What I assumed

Every one of these is a real inference the source data forced, not a guess made for convenience — see `docs/data-notes.md` for the numbers behind each one.

- **Outlet → BDM assignment is Town → Territory, normalized.** There's no assignment table. 40 raw town spellings collapse cleanly onto the 12 BDM territory names with zero leftovers once cased and de-duplicated (`Madras`→Chennai, `Mdu`→Madurai, etc.) — but "a BDM owns every outlet in their territory" is an assumption the join makes, not a fact the source states.
- **Segmentation thresholds**: an outlet drops from Core to Slipping if its current month is >30% below its own trailing average, or it's missed exactly the latest month. Two or more missed months moves it to Dormant. "Valuable" (Dormant-valuable vs -low) is the **median** peak monthly value among outlets that have ever billed — not a percentile chosen to sound rigorous; I first tried the 75th percentile and it made Dormant-valuable mathematically unreachable (see `docs/ai-log.md`), because currently-thriving outlets dominate the top of that distribution. The median is a "was this a typical solid outlet or below" bar, which is what "used to matter" should mean.
- **The outlet-side verification code is generated, not sourced.** Nothing in `outlets.csv` is a printable counter-card code. `seed.py` derives a stable 4-digit code per outlet from a hash of its outlet code. In production this would be a printed card at the counter (or reuse an existing outlet code/QR the client already has); the mechanism (owner reads it, BDM types it, code match drives confidence) is the real design, the specific 4 digits are a placeholder.
- **"Area" inside a beat is a derived quadrant, not a real locality.** Town collapses 1:1 onto Territory, so there's no finer geography in the source to filter a day's beat by. Outlets with coordinates get bucketed into a North/South/East/West quadrant relative to their territory's centroid, labelled honestly in the UI as derived, not a real place name.
- **Dues are manual-entry only.** No dues/outstanding/receivables field exists anywhere in the four files (confirmed, not inferred — see `docs/data-notes.md` Q6). The Counter Conversation screen has a plain number field labelled "Dues not tracked from source data," stored per-visit, and the last value entered shows up next time as a starting point — it is never computed.
- **"This Week" is the last 7 real calendar days**, not a slice of the historical May–July 2026 log. New app-submitted visits use the real current date, so This Week is empty until you actually submit a visit through the app — that's intentional, not a bug.

## What I left out and why

- **Auth.** Anyone can pick any BDM's name from a dropdown. Fine for a prototype with 12 known users behind one link; not fine to ship as-is. Real auth (magic link or phone OTP, matched to `bdms.csv`) is the first thing I'd add before a real rollout.
- **Live GPS capture.** The schema has `latitude`/`longitude` on every visit, but a Streamlit page can't request the phone's live location without a custom JS component outside the fixed stack. App-submitted visits log the *outlet's* stored coordinates as a placeholder and rely entirely on the outlet-code + outcome-evidence verification instead — which is the correct verification mechanism regardless (see "The Madurai decision" below), so this cut costs less than it sounds like.
- **Route optimization.** The beat is ranked by priority, not sequenced into an actual walking/driving route. Worth doing once outlet coordinates are reliable for all 820 outlets (108 currently have none).
- **Offline / sync.** Every write goes straight to Postgres; no connectivity means no save. Real rural coverage makes this a near-term problem, not a hypothetical one.
- **ERP / accounting integration.** Orders and collections logged in the app live in this app's own tables; nothing pushes them anywhere. Wiring that up depends entirely on what system the client's actual billing runs on, which wasn't specified.
- **i18n / Tamil.** BDMs on the ground almost certainly want this in Tamil, not English. Didn't touch it — `checklists.yaml`'s labels would need a translation layer, and Streamlit's own chrome (buttons, camera prompt) doesn't localize for free.
- **Push notifications.** No "you have 3 outlets overdue" nudge. The tool has to be worth opening on its own; a notification layer is a later optimization, not a replacement for that.
- **Export to Excel.** Not built, not asked for. The manager view answers the five questions the brief named directly in-app instead of via a spreadsheet.
- **Merging the 20 possible-duplicate outlets.** Flagged with a warning banner on the Counter Conversation screen, never auto-merged — merging would silently destroy real billing/visit history attached to whichever code got deleted. That decision belongs to the client, not to a seed script.

## What I'd do next, in priority order

1. **Auth**, matched to the 12 known BDMs — everything else in this list assumes you know who's actually submitting.
2. **Resolve the 20 possible-duplicate outlets** with the client directly — every one of them is currently billing and being visited under two separate codes, which means the manager's revenue and coverage numbers are already slightly wrong in a specific, findable way.
3. **A real dues ledger**, if one exists anywhere in the client's systems (it wasn't in the four files given) — manual entry is a stopgap, not a fix.
4. **Route sequencing** once outlet coordinates are complete enough to trust (currently 108 of 820 have none).
5. **Offline queue** for the Counter Conversation form — a written visit currently either reaches Postgres or is lost outright; no dataset here tells me connectivity is worse at the dormant/rural end of the beat, but it's the failure mode most worth insuring against before assuming it away.
6. Re-run the segmentation thresholds (30% slip, median valuable-bar) past the client once they've seen the tool live — both are defensible defaults, not numbers the client confirmed.

## The Madurai decision

The brief describes three outlets sharing a wall, indistinguishable by GPS. I looked for that literally in the coordinate data before designing around it, and it isn't there — the closest genuinely-different-name outlets in Madurai are 191 metres apart, a different block, not a shared wall (full numbers in `docs/data-notes.md`). What the data does contain is 20 pairs of outlets nationwide sitting at *exactly* the same coordinates with near-identical names, both independently billing and being visited under separate codes — a duplicate-registration problem, not a GPS-precision one, but the same visible symptom the client described ("I can't tell which outlet the BDM was at").

Either way, the underlying reasoning holds: **phone GPS is accurate to 10–50 metres; shops that share a wall are 3–5 metres apart.** No amount of GPS logging can separate them, and claiming otherwise would be shipping a metric the client would eventually catch as fake. So verification here is:

1. **Primary — an outlet-side code.** The owner reads a code off a card at their counter; the BDM types it in. Cheap, works offline, and requires the owner's actual presence — the one thing GPS can't prove.
2. **Secondary — outcome as evidence.** A visit with a real order, collection, or specific blocker recorded is stronger evidence than a location pin, and is weighted into the confidence level even without a code match.
3. **Optional — a counter photo**, captured at submit time via the phone's camera.
4. **GPS is logged but never used to identify which outlet was visited** — only to flag physically impossible patterns: 715 of 5,904 historical visits (12.1%) are flagged this way, split roughly evenly across implausible daily visit counts, impossibly tight pacing between different outlets, and visits outside the BDM's assigned territory. That number is itself the strongest evidence for why the old log couldn't be trusted, and it's surfaced directly in the manager view's Log Integrity section rather than buried.

## Repo layout

```
outlets.csv, bdms.csv, billing-monthly.csv, visit-log.csv   source data
db/schema.sql, db/connection.py, db/queries.py,             Postgres layer
  db/manager_queries.py
seed.py                                                     idempotent CSV -> Postgres loader
logic/                                                       pure, DB-free business logic
  normalize.py       every coercion rule from Phase 0
  segmentation.py     5-bucket outlet classification
  scoring.py           priority score + plain-English reason
  confidence.py        Verified/Partial/Unverified
  checklist.py, geo.py
checklists.yaml                                              per-outlet-type checklist config
app.py, screens/                                              Streamlit app (My Visits, Counter
                                                               Conversation, This Week, Insights)
tests/                                                        38 tests, no DB required
docs/
  data-notes.md         Phase 0 findings, full null-classification table
  ai-log.md              dated log of what the AI got wrong and how it was caught
  rejected-rows.csv      every field-level coercion seed.py made, regenerate with `python seed.py`
docker-compose.yml, Dockerfile, .env.example
```
