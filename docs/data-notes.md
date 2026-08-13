# Phase 0 — Data Notes

Source files: `outlets.csv`, `bdms.csv`, `billing-monthly.csv`, `visit-log.csv`, all in repo root.
All four were read with `dtype=str, keep_default_na=False` so nothing was coerced or imputed before being inspected. Raw counts below.

## 1. Schema, dtypes, row counts

| File | Rows | Columns |
|---|---|---|
| `outlets.csv` | 820 | Outlet Code, Outlet Name, Type, Town, Owner Name, Phone, Onboarded, Credit Days, Latitude, Longitude, Status |
| `bdms.csv` | 12 | BDM Code, Name, Territory, Phone, Joined |
| `billing-monthly.csv` | 2,142 | Outlet Code, Month, Units, Value |
| `visit-log.csv` | 5,904 | Visit ID, BDM Code, BDM Name, Outlet Code, Outlet Name, Visit Date, Check In, Duration (mins), Purpose, Remarks |

Everything arrives as text; there is no numeric or date typing in the source. All four files parsed without row-count surprises (field-count-per-row is constant within each file — no embedded commas breaking rows).

## 2. Null / gap classification per column

Legend: **SA** = Structurally Absent (real business fact, not a gap), **NC** = Not Captured (field exists, process didn't fill it), **BR** = Broken Record (malformed/needs coercion).

### outlets.csv

| Column | Blank/bad count | % | Type | Handling |
|---|---|---|---|---|
| Outlet Code | 0 | 0.0% | — | Primary key, unique across all 820 rows. |
| Outlet Name | 9 | 1.1% | NC | Display as "Unnamed outlet (OA0XXX)"; never blank in UI. |
| Type | 0 | 0.0% | — | 4 clean values: General Trade (444), Mobile Specialist (222), Premium Reseller (111), Multi-Yard (43). Drives `checklists.yaml` item sets. |
| Town | 0 | 0.0% | BR (casing/synonyms) | 40 raw spellings collapse to the 12 real territory names once lower-cased and mapped through synonyms (KARUR/Karur/karur → Karur; Mdu/Madurai/MADURAI → Madurai; Madras → Chennai; Tanjore → Thanjavur; CBE/Cbe → Coimbatore; Tiruchirappalli/TRICHY/trichy → Trichy; Nellai/TIRUNELVELI → Tirunelveli; Tiruppur/TIRUPUR/tirupur → Tirupur). After normalization the 12 towns match the 12 BDM territories exactly — see Q7 below. Normalization map lives in code, not invented data. |
| Owner Name | 0 | 0.0% | — | Clean. |
| Phone | 57 | 7.0% | NC/BR mixed | 57 blank (NC). Of the remainder, 216 rows use a non-`^\d{10}$` format: `+91 XXXXX XXXXX`, hyphenated `XXXXX-XXXXX`, 12-digit with leading `91`, or the literal placeholder `"0"` (which is a Broken Record, not a real number). Normalize by stripping non-digits and taking the last 10; treat `"0"` and blank identically as "No phone on file." Not used by app logic, only display — low priority. |
| Onboarded | 0 | 0.0% | BR (3 date formats) | `DD/MM/YYYY` (423), `YYYY-MM-DD` (215), `DD-Mon-YY` (182). All three parse unambiguously (no day-vs-month collisions found: every `DD/MM/YYYY` row has a first component that only ever means day when >12, confirmed against the 12-Mon-YY variant). Parsed once in `seed.py`, logged as coerced, never re-guessed downstream. Range: 2019-06-03 to 2025-06-09 — every outlet was onboarded before the 6-month billing window starts, so no outlet's "never billed" status is explained by late onboarding. |
| Credit Days | 108 | 13.2% | NC (blank) / BR (mixed representation) | Values seen: `30` (208), `45` (109), blank (108), `30 days` (105), `COD` (103), `0` (99), `15` (88). `COD` and `0` both mean "cash on delivery / no credit" — treated as terms code `0`, distinct from blank ("terms not recorded"). `"30 days"` normalized to integer `30`. Not used in Phase 1–4 scope (no dues ledger exists to apply terms to) — recorded for completeness and for the "what I'd do next" list. |
| Latitude / Longitude | 108 / 108 | 13.2% | NC | Same 108 rows missing both (one outlet has no location data at all). These outlets cannot get an anomaly/near-neighbour check and are flagged "Location not recorded" rather than silently omitted from the beat. |
| Status | 77 | 9.4% | BR (casing) / NC (blank) | Active/ACTIVE/active → Active (421); Dormant/dormant → Dormant (170); Hold (79, as-is); Inactive (73, as-is); blank (77) → "Status not recorded", not defaulted to Active or Dormant. |

### bdms.csv

| Column | Blank count | % | Type | Handling |
|---|---|---|---|---|
| BDM Code / Name / Territory | 0 | 0.0% | — | Clean, 12 distinct BDMs, 12 distinct territories, 1:1. |
| Phone | 1 | 8.3% | NC | Display "No phone on file." |
| Joined | 0 | 0.0% | — | Consistent `YYYY-MM-DD`, unlike outlets. Not used by app logic. |

### billing-monthly.csv

| Column | Blank/bad count | % | Type | Handling |
|---|---|---|---|---|
| Outlet Code | 0 | 0.0% | — | 492 distinct outlets appear at least once out of 820 — i.e. 328 outlets have **zero rows in this file for all 6 months** (SA: never billed, not a missing record — see below). |
| Month | 0 | 0.0% | — | 6 clean values, `2026-02`…`2026-07`. |
| Units | 0 | 0.0% | — | Integer, consistent. 41 rows are `0`. |
| Value | 0 | 0.0% | — | Integer rupees, no currency symbols/commas/decimals found. 41 rows are `0`, always paired with `Units=0` (no Units/Value contradiction anywhere). Avg price-per-unit resolves to one of 5 clean SKU price points with zero outliers — this file is otherwise very clean. |

**The three-way null distinction this file actually needs (per the brief's Required Handling #2):**
- **No record** (SA) — an outlet/month pair with *no row at all*. 820 outlets × 6 months = 4,920 possible pairs; only 2,142 exist. The other 2,778 are "no record," meaning either the outlet never billed that specific month or was outside the reporting window — the source gives no way to tell those apart further, so both render as "No bill recorded" (not zero).
- **Zero bill** (SA, but a *different* fact) — a present row with `Value=0` (41 rows). This is a submitted record saying the outlet did no business that month. It must render differently from "no record" in the 6-month trend (e.g. a marked zero point vs. a gap) because it's stronger evidence of trouble — the outlet was live enough to report and reported nothing.
- **Broken record** (BR) — none found in this file; every present row is a valid non-negative integer pair.

I could not build "zero bill" vs "no record" as a UI distinction from a fabricated placeholder — it comes directly from row presence, which is why `seed.py` must load billing as a sparse fact table (one row per outlet-month that exists) rather than a dense pivot filled with 0.

### visit-log.csv

| Column | Blank count | % | Type | Handling |
|---|---|---|---|---|
| Visit ID | 0 | 0.0% | — | Unique per row, no exact duplicate rows anywhere in the file. |
| BDM Code / BDM Name | 0 | 0.0% | — | Clean, matches `bdms.csv` 1:1. |
| Outlet Code | 0 | 0.0% | — | Every value exists in `outlets.csv` — FK integrity is clean. 819 of 820 outlets have at least one logged visit in 3 months; 1 has none. |
| Outlet Name | 231 | 3.9% | NC | Falls back to the name on record in `outlets.csv` by Outlet Code; if that's also blank, "Unnamed outlet." |
| Visit Date | 0 | 0.0% | BR (2 formats) | `DD/MM/YYYY` (4,155) and `YYYY-MM-DD` (1,749), mixed row by row with no pattern by BDM or date. Confirmed unambiguous: every slash-format row has a day component >12 in enough cases to fix the format as `DD/MM/YYYY` (2,464 of 4,155 rows have a first component >12, zero rows have a second component >12). Parsed to one range: 2026-05-01 to 2026-07-31 — a clean 3-month window. |
| Check In | 14 | 0.2% | NC | Time of day, `HH:MM`. Blank ones cannot be used in the pacing/anomaly check. |
| Duration (mins) | 811 | 13.7% | NC | Never fabricated to look complete — renders "Duration not logged." |
| Purpose | 534 | 9.0% | NC (blank) / BR (casing/synonyms) | 10 raw values collapse to ~6: Routine visit / routine → Routine visit (1,398); followup / Follow up → Follow up (1,152); Collection (574); Order (568); Complaint (561); New onboarding (590); Stock check (527); blank (534) → "Purpose not logged," never defaulted to a guessed category. |
| Remarks | 2,262 | 38.3% | NC | **Not free text.** Only 8 distinct non-blank values across 3,642 filled rows (`discussed scheme`, `shop closed`, `will order next week`, `asked for better margin`, `stock displayed`, `collection pending`, `owner not available`, `display not as per norms`) — this is a canned outcome/blocker picklist already, not prose. That's a product finding, not just a data-quality note: the "outcome" concept the brief asks the checklist to capture already exists in embryonic form here. 38.3% of visits have **no outcome recorded at all** — this is direct, quotable evidence for the manager's "did the conversation actually happen" question (see Log Integrity, Q5). |

## 3. Answers to the required questions

**Outlets and billing.** 820 outlets on the books (one line short of "~800," consistent with the brief). 279 billed (Value > 0) in the most recent month (2026-07); 285 have *any* row (incl. zero) that month. 328 outlets (40%) have never billed a positive value in the full 6-month window — these are candidates for the New/Never segment, not automatically "bad data."

**Outlet types.** General Trade 444 (54%), Mobile Specialist 222 (27%), Premium Reseller 111 (14%), Multi-Yard 43 (5%). Four clean categories, no casing issues — this is the field `checklists.yaml` will key on.

**Months-since-last-bill** (for the 492 outlets that billed at least once; months since = 0 means billed in the latest month):

| Months since last bill | Outlets |
|---|---|
| 0 (current) | 279 |
| 1 | 13 |
| 2 | 37 |
| 3 | 40 |
| 4 | 63 |
| 5 (billed only in the oldest month on file) | 60 |
| Never billed in window | 328 |

Reading this straight: once an outlet stops billing in this data, it rarely comes back next month (13) — most gaps run 3+ months, and 328 outlets have no billing history at all in the window. That's a real "dormant" and "never" population, not noise.

**Revenue concentration.** Total 6-month revenue across 492 billing outlets: ₹2,000,369,000. Top 20% by revenue (98 outlets) = 70.1% of revenue. Top 10% (49 outlets) = 45.7%. Highly concentrated — this justifies a priority score that weights value, not just recency.

**Visit log.**
- Visits/BDM/month range from ~134 to ~198 (mean ~163) across the 3 months — fairly even across BDMs, no one BDM stands out as idle or overloaded.
- Only **58.8%** of visits land on outlets that bill at all in the 6-month window, against a base rate of 60.0% of outlets being billing outlets — i.e. visit allocation is statistically indistinguishable from random with respect to whether the outlet matters. BDM time is not visibly weighted toward Core/valuable outlets in this log.
- **38.3%** of visits have no Remarks (outcome) at all; 9.0% have no Purpose; 3.5% have neither — a fully blank outcome.
- **Impossible patterns, found directly:**
  - One BDM (BDM002) logged **26 visits in a single day** (2026-05-08).
  - 352 pairs of same-BDM, same-day visits are check-in-stamped **less than 10 minutes apart at different outlet codes** — e.g. BDM001 on 2026-06-05 shows check-ins at 6 different outlets between 17:02 and 17:12. No plausible travel time between counters is reflected in the timestamps.
  - 286 of 5,904 visits (4.8%) are logged by a BDM against an outlet outside that BDM's own territory (after Town normalization — see Q7). Some of this may be legitimate covering, but it's large enough to flag, not ignore.
  - No exact duplicate rows exist (`Visit ID` is always unique and no full-row dupes), so the trust problem is about implausible timing and missing outcomes, not literal double-entry.

  This is direct, numeric support for the client's stated distrust of the log — it goes straight into Phase 3/4 (Log Integrity) rather than being fixed or hidden.

**Dues / outstanding / receivables.** **No such field exists anywhere in any of the four files.** `outlets.csv` has `Credit Days` (payment terms) but no ledger; `billing-monthly.csv` has invoiced Value only, no payment/receipt tracking. This is a material, named gap: the brief's Counter Conversation screen calls for "outstanding dues if the data supports it" — it does not. This will be a manual-entry field with an explicit "Dues not tracked from source data" label, not a computed one, and goes in the README as a real "what I left out and why."

**Outlet–BDM join.** No explicit assignment table exists. The only path is `outlets.Town` → normalized territory name → `bdms.Territory`, which is a many-to-one join on a derived, normalized key, not a stated foreign key. After the synonym/casing normalization above, the 40 raw town spellings collapse to exactly the 12 BDM territory names with no leftovers and no ambiguity — so the join is reliable **once normalized**, but it is an assumption (a BDM owns every outlet in their named territory) rather than a fact stated anywhere in the source. I'm flagging this as the one join-level assumption the segmentation and beat-ranking logic will depend on.

**Near-identical outlets (the Madurai case) — this needs a direct correction to the brief's framing, backed by the numbers:**

I looked for a literal 3-outlets-within-a-few-metres cluster in Madurai, since that's how the problem was described. It isn't there. What the coordinate data actually contains, across *all* territories (not just Madurai):

- **20 pairs of outlets sitting at the exact same latitude/longitude (0.0m apart)**, each pair having near-identical names — same name with different casing (`Big C Infotech` / `BIG C INFOTECH`), a trailing space, or a `"- Branch"` suffix (`Muthu Digital` / `Muthu Digital - Branch`). These are concentrated in outlet codes OA0798–OA0820, a block at the tail of the file.
- Critically, these are **not empty duplicate rows** — both codes in a pair independently appear in `billing-monthly.csv` with real, different revenue, and both receive real visits in `visit-log.csv`. That means the same physical shop is very likely double-registered under two outlet codes, and its true volume and visit coverage are currently split and undercounted under either code alone.
- Only 2 pairs of *genuinely differently-named* Madurai outlets are within any tight radius, and the closest is 191 metres apart — a different city block, not a shared wall. 108 outlets (13.2%) have no coordinates at all and can't be checked either way.

So the evidence points to a **duplicate-registration problem**, not a **GPS-precision problem**, in this specific dataset — though the two produce the same symptom the client described ("I can't tell which outlet the BDM was actually at"), and the underlying fix the brief asks for (an outlet-side code, not GPS, as the source of truth) is correct for both. I'll flag the 20 duplicate pairs to the client as "possible duplicate outlet — verify" rather than silently merging them, since merging would destroy real billing/visit history attached to each code.

## 4. Data-quality problems and proposed handling (summary)

1. **Town spelling/casing** (40 raw → 12 real) — fix with a normalization map in code; verified it collapses cleanly onto the 12 BDM territories with zero leftovers.
2. **Status/Type casing** on Status only (Type is already clean) — fix with `.strip().lower()` + canonical map; blank stays "not recorded," never defaulted to Active.
3. **Three date formats in `Onboarded`, two in `Visit Date`** — all unambiguous once checked (verified via the >12 test), parsed explicitly in `seed.py`, every coercion logged.
4. **Credit Days mixed representation** (`30`, `"30 days"`, `COD`, `0`, blank) — normalize `COD`/blank-terms cases explicitly; not used by app logic in this scope.
5. **Phone number formatting** — cosmetic only, normalize for display, not used in any logic.
6. **20 likely-duplicate outlet registrations** (exact coordinates + near-identical names, both independently billing/visited) — flagged to the client as a data-integrity issue, not auto-merged.
7. **108 outlets missing coordinates entirely** — excluded from geo-anomaly checks with an explicit "location not recorded" state, not silently dropped from beat planning.
8. **No dues/receivables field anywhere** — named gap, manual-entry field in the UI, called out in the README.
9. **No explicit outlet→BDM assignment** — join via normalized Town→Territory is the only path; flagged as an assumption, not a stated fact.
10. **38.3% of visits carry no outcome, and visit timing shows physically impossible pacing (up to 26 visits/day, <10-minute gaps between different outlets)** — this is the client's mistrust, quantified. It drives the Phase 3 verification design (outlet-side code + outcome-as-evidence, GPS demoted to anomaly-only) and the Phase 4 Log Integrity section directly; it is reported, not cleaned up or smoothed over.
11. **`billing-monthly.csv` must stay a sparse fact table.** Pivoting it to a dense outlet×month grid and filling gaps with 0 would erase the No-record vs. Zero-bill distinction required by the brief. `seed.py` loads it as-is; "no record" and "zero" are computed downstream, never conflated.

## 5. Segmentation logic to confirm before Phase 1

Proposed, pending your sign-off, using the 6 months of `billing-monthly.csv` per outlet:

- **Core** — billed (Value>0) in the latest month, and in at least 4 of the last 6 months, with the latest month not down more than ~30% from the outlet's own trailing average.
- **Slipping** — billed in the latest month but down materially (>30%) from trailing average, OR billed previously but missed only the most recent 1 month.
- **Dormant-valuable** — 2+ consecutive months with no bill (incl. the latest), but had at least one month historically above [a value threshold — proposing the outlet's own 75th percentile of all billing outlets, will confirm once I see the shape], i.e. it used to matter.
- **Dormant-low** — 2+ consecutive months with no bill, and never crossed that value threshold.
- **New/Never** — zero rows in `billing-monthly.csv` across all 6 months (the 328 identified above).

Edge cases the tests will cover explicitly: single-month history, gaps in the middle of the 6 months (not just trailing), and the 41 explicit zero-value rows (treated as "billed nothing," i.e. a live but bad month — not the same as "no record"). Every one of the 820 outlets must land in exactly one bucket; this will be an assertion in the test suite, not just a hope.

**Waiting for confirmation on:** the value threshold for "valuable" in Dormant-valuable/-low, and the 30%-drop threshold for Slipping, before writing the scoring code.
