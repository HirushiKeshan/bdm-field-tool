# AI usage

## What tool was used

**Claude Code (Sonnet 5)** built this project, start to finish, in one long back-and-forth session — not one big prompt.

Roughly how the work broke down:

- **Explored the data first.** Used `scripts/explore.py` plus a few small pandas/GPS-distance checks to find nulls, bad dates, town-name spelling issues, and duplicate shops — before writing any app code. The numbers in `docs/data-notes.md` come from actually running these checks, not from reading the CSVs by eye.
- **Built the data layer.** The database schema, the CSV loader (`seed.py`), and the business rules (segmentation, scoring, checklist logic, confidence scoring) — with tests written alongside.
- **Built the app.** The Streamlit screens (My Visits, Counter Conversation, This Week, Insights).
- **Tested it for real.** Ran the app locally against a real Postgres database and clicked through every screen in a browser before each deploy, instead of just trusting that the code looked right.

No other AI tool was used — no image generation, no separate code-completion tool.

## Where the AI got things wrong

Full details with exact error messages are in [`docs/ai-log.md`](docs/ai-log.md). Short version:

1. **Assumed the wrong shape of a data problem** — expected shops sharing a wall to show up as identical GPS coordinates. They didn't; the real issue was 20 shops registered twice under different codes. Checked directly instead of forcing the data to match the assumption.
2. **A database column name clash** crashed a screen — caught by actually loading the screen, not by reading the code.
3. **A timestamp used as a unique ID** collided on Windows because of its slower clock — caught by a test that fired several writes quickly in a row.
4. **A threshold that could never be reached** — a "dormant but valuable" category used a math rule that no shop could ever satisfy. Caught by noticing a suspicious zero instead of assuming it was correct.
5. **A date calculation shifted for every shop** the moment any one visit was logged, silently changing everyone's numbers. Missed by me at first — caught by a second independent review.
6. **A checklist question counted as "answered" even when untouched**, letting a rep submit a visit without really doing anything. Also caught by that second review — the worst bug of the seven, since the code ran fine and looked correct, it just didn't do what the feature was for.
7. **A new page header was invisible** — code and styles all looked correct, but another element was sitting on top of it. Found by asking the browser what was actually drawn at that spot, not just reading the CSS.
8. **A production-only crash from a database connection timing out** — worked locally, broke on the live server under Supabase's connection pooling. First fix guessed the wrong error type and didn't actually work; the real fix came only after reproducing the exact failure locally and confirming it twice.
9. **GPS capture hung forever on the live server** but worked locally — caused by a security restriction that only exists once the app is wrapped in Streamlit Cloud's own frame. Found by reading the live browser's console, not by re-reading the code.

Two of these (#5 and #6) were only found by asking a second, independent pass to actually use the finished app rather than read the code — a good reminder that "it looks right" and "it works" aren't the same thing.
