# AI usage log

Dated, append-only. Each entry: what was asked, what came back wrong, how it was caught, what changed. This file starts with the first commit, not written retroactively at the end.

---

**2026-08-13 — Phase 0, Madurai near-duplicate check.**

The brief's framing was specific: "three of our outlets share a wall... I cannot tell you which one a BDM was standing in," implying a literal cluster of outlets a few metres apart in Madurai. Going in, the working assumption (mine, not verified yet) was that the coordinate data would contain such a triplet, and the job was just to find it and use it as the running example for Phase 3.

It isn't there. I ran a pairwise haversine distance check within each normalized territory (script: `scripts/explore.py` + inline analysis, see `docs/data-notes.md` §3). Result: the closest pair of *genuinely differently-named* outlets in Madurai is 191 metres apart — a different block, not a shared wall. What the data actually contains is 20 pairs of outlets nationwide sitting at the *exact same* coordinates with near-identical names (casing differences, trailing spaces, `"- Branch"` suffixes), concentrated in outlet codes OA0798–OA0820.

The catch: my first pass treated the 0.0m-apart pairs as "found it, that's the Madurai case" and almost wrote them up that way. Before committing to that framing, I checked whether those pairs were empty duplicate rows or real records — and both codes in every pair independently appear in `billing-monthly.csv` with different revenue and in `visit-log.csv` with real visits. That's a different bug: duplicate outlet registration splitting one shop's history across two codes, not two adjacent-but-distinct shops that GPS can't tell apart. Same visible symptom to the client ("can't tell which outlet the BDM was at"), different root cause, different fix (a de-dupe/merge candidate list, not a verification mechanism).

Fix: `docs/data-notes.md` reports both findings separately and explicitly says the literal "3-shops-5m-apart" scenario is not reproduced in this dataset's coordinates, rather than forcing the duplicate-registration finding into that shape to match the brief's narrative. The Phase 3 design (outlet-side code, GPS demoted to anomaly-only) still holds either way — but the evidence backing it is now the real evidence, not a reach.

---

**2026-08-13 — Phase 2, live browser test of the Counter Conversation screen.**

Wrote `db/queries.py::fetch_manual_dues` with `SELECT response_value, created_at FROM visit_checklist_responses vcr JOIN visits v ON v.visit_id = vcr.visit_id ...` — both `visit_checklist_responses` and `visits` have a `created_at` column, and the bare `created_at` in the SELECT list is ambiguous. Postgres rejected it: `AmbiguousColumn: column reference "created_at" is ambiguous`.

I didn't catch this from reading the code — it only surfaced when I actually loaded the app in a browser at 390px and opened a Counter Conversation screen, which is exactly the kind of bug a code review skims past (the query looks fine until you remember the schema has two `created_at` columns three tables apart). Unit tests didn't catch it either, since the segmentation/scoring/normalize test suite never touches this query.

Worse side effect: the app caches one Postgres connection per session (`@st.cache_resource`) and reuses it across every screen rerun. Once this one query failed, Postgres left the connection in `InFailedSqlTransaction` state, so *every subsequent query on that connection* failed too — including completely unrelated ones like `fetch_outlets` on the next screen — until the process restarted. The visible symptom (a `fetch_outlets` traceback) was not the real bug; the real bug was three calls earlier.

Fix: qualified the column as `vcr.created_at`, and added a `try/except psycopg2.Error: conn.rollback(); raise` around the screen dispatch in `app.py` so one bad query can't permanently wedge the cached connection for the rest of the session. Take-away: with a cached long-lived DB connection, any unhandled query error becomes a session-wide outage, not a one-screen error — that needs a rollback safety net regardless of how careful the SQL is.

---

**2026-08-13 — Phase 3, scripted write-path test found a duplicate-key crash.**

`db/queries.py::submit_visit` generated each new visit's primary key as `f"APP-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{outlet_code}"` -- a timestamp down to the microsecond, which reads as unique enough on its face. Testing the write path with `scripts/dev_verify_writes.py` (three back-to-back `submit_visit` calls to check the Verified/Partial/Unverified confidence branches), the third call crashed: `psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "visits_pkey"`. Two calls a few milliseconds apart had generated the *same* visit_id string.

Checked directly: `datetime.utcnow().strftime('%Y%m%d%H%M%S%f')` called five times in a tight loop on this machine returned the identical string all five times. Windows' clock resolution for this call is coarser than one microsecond (commonly ~15ms ticks), so "microsecond precision" was theatre — any two inserts within the same tick collide. This would not have shown up in a single manual click-through test; it only surfaced because the verification script fired requests back-to-back with no human delay between them, which is exactly what a busy BDM tapping through visits quickly could also do.

Fix: switched the ID to `f"APP-{uuid.uuid4().hex[:16]}-{outlet_code}"` -- a real uniqueness guarantee that doesn't depend on OS clock resolution. Take-away: never treat a wall-clock timestamp as a uniqueness source without checking the platform's actual clock granularity; a UUID costs nothing here and removes the assumption entirely.

---

**2026-08-13 — Phase 4, manager view smoke test: Dormant-valuable was silently empty.**

Ran `db/manager_queries.py::recovery_pipeline` against the full seeded dataset to sanity-check the manager view before calling Phase 4 done, and it returned an empty list — zero outlets in the whole 820-outlet dataset landed in the "Dormant-valuable" segment. That's the segment the "recovery pipeline" section exists to show, so an empty result was suspicious enough to dig into rather than assume the data just has none.

Root cause was in `logic/segmentation.py::compute_valuable_threshold`, which I'd set to the 75th percentile of peak billing value across *every* outlet that has ever billed -- including outlets that are still Core today. Currently-thriving accounts keep compounding over the 6-month window and dominate the top of that distribution, so the 75th-percentile bar (₹15.48L) ended up higher than the single highest peak any *dormant* outlet had ever reached (₹7.9L). By construction, no dormant outlet could ever cross it. I picked 0.75 as a plausible-sounding default without checking whether it was actually reachable by the population it was meant to classify.

Fix: dropped the default to the median (0.5). At the median (₹4.08L), 21 outlets land in Dormant-valuable -- a real, checkable number I verified against `docs/data-notes.md`'s revenue-concentration finding. Also fixed a second, related issue the same smoke test surfaced: `conversation_quality`'s checklist-completion metric was reading 100% because every historical (pre-app) visit is seeded with `is_complete=True` as "a finished log entry" -- which is a true statement about the historical row but not an answer to "did BDMs finish the in-app checklist," since historical visits never went through this app's checklist at all. Restricted that metric to `source='app'` rows, and made it display "no app-recorded visits yet" instead of a misleadingly perfect 100% when there aren't any.

Neither of these would have been caught by the segmentation unit tests, which use small synthetic fixtures rather than the real distribution -- both only surfaced by actually running the manager queries against the full dataset and treating an oddly-round number (0) as a bug to investigate rather than a fact to report.

---

**2026-08-13 — Phase 5, independent review (fresh agent, no build context) caught two live bugs.**

Before finalizing, I asked a separate agent with no memory of this build to review the repo cold -- read the README, the code, and actually run it, rather than trust my own read of code I'd just written. It found two real, "ran without error, silently wrong" bugs, both worse than anything I'd caught myself:

1. **The reference "today" for recency math silently jumped 13+ days the moment any app visit was submitted.** `db/queries.py::_latest_known_date` used `MAX(visit_date)` across *all* visits (historical + app) as "today," reasoning that a fixed historical window needed a matching fixed reference point. But app-submitted visits are stamped with the real wall-clock date, weeks after the historical log ends. The agent reproduced it directly: one outlet's `days_since_last_visit` was 3, then jumped to 16 the instant an unrelated BDM submitted one unrelated visit elsewhere -- because "today" itself had just moved forward 13 days for the whole app, reshuffling every outlet's beat-priority score and every BDM's coverage-gap numbers nationwide, all triggered by a single unrelated write. My own testing never caught this because I was seeding once and reading immediately after, never comparing "before this write" to "after this write" for an unrelated outlet -- exactly the kind of check a fresh reviewer runs and a rushed self-check skips. Fix: just use `date.today()`. The "matching reference point" reasoning was solving a problem that didn't need solving -- a live tool's "today" should be today, and historical outlets correctly reading as long-overdue the moment the tool goes live is the true, useful signal, not a bug to design around.

2. **Streamlit's `st.radio` defaults to its first option, so an untouched checklist item read as an answered one.** Every outlet type's checklist has at least one blocker-type radio item. `st.radio(item["label"], item["options"], ...)` pre-selects `options[0]` the moment the screen renders -- before the BDM has looked at it, let alone answered it. `submit_visit`'s outcome-evidence check (`any(r["response_type"] == "blocker" and r["response_value"] ...)`) then read that untouched default as a real recorded outcome, which is enough to reach `Partial` confidence. The agent simulated a full click-through submit with zero real interaction -- no code, no order, no collection, nothing touched -- and it still stored `confidence = 'Partial'`, never `Unverified`. That's a direct hit against the one feature the whole verification design (see README's "Madurai decision") exists to protect: distinguishing a real conversation from a drive-by check-in becomes nearly impossible if the UI hands out free evidence by default. Fix: `st.radio(..., index=None)` so nothing is pre-selected, and treat a `None` choice as no answer rather than stringifying it into a fake response.

Both bugs share a pattern worth naming: they only show up by comparing state *across* an action (before vs. after a write; a full click-through vs. an empty one), which is exactly what a single-pass code read or a happy-path manual test misses. Neither was in the segmentation/scoring logic I'd already unit-tested hardest -- both were in the thinner, less-tested seams between the DB layer and the UI.
