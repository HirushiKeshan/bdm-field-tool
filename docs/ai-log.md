# AI usage log

Dated, append-only. Each entry: what was asked, what came back wrong, how it was caught, what changed. This file starts with the first commit, not written retroactively at the end.

---

**2026-08-13 — Phase 0, Madurai near-duplicate check.**

The brief's framing was specific: "three of our outlets share a wall... I cannot tell you which one a BDM was standing in," implying a literal cluster of outlets a few metres apart in Madurai. Going in, the working assumption (mine, not verified yet) was that the coordinate data would contain such a triplet, and the job was just to find it and use it as the running example for Phase 3.

It isn't there. I ran a pairwise haversine distance check within each normalized territory (script: `scripts/explore.py` + inline analysis, see `docs/data-notes.md` §3). Result: the closest pair of *genuinely differently-named* outlets in Madurai is 191 metres apart — a different block, not a shared wall. What the data actually contains is 20 pairs of outlets nationwide sitting at the *exact same* coordinates with near-identical names (casing differences, trailing spaces, `"- Branch"` suffixes), concentrated in outlet codes OA0798–OA0820.

The catch: my first pass treated the 0.0m-apart pairs as "found it, that's the Madurai case" and almost wrote them up that way. Before committing to that framing, I checked whether those pairs were empty duplicate rows or real records — and both codes in every pair independently appear in `billing-monthly.csv` with different revenue and in `visit-log.csv` with real visits. That's a different bug: duplicate outlet registration splitting one shop's history across two codes, not two adjacent-but-distinct shops that GPS can't tell apart. Same visible symptom to the client ("can't tell which outlet the BDM was at"), different root cause, different fix (a de-dupe/merge candidate list, not a verification mechanism).

Fix: `docs/data-notes.md` reports both findings separately and explicitly says the literal "3-shops-5m-apart" scenario is not reproduced in this dataset's coordinates, rather than forcing the duplicate-registration finding into that shape to match the brief's narrative. The Phase 3 design (outlet-side code, GPS demoted to anomaly-only) still holds either way — but the evidence backing it is now the real evidence, not a reach.
