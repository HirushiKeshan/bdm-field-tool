"""
Dev-only: embedded local Postgres (no docker needed) kept alive in the
background so the Streamlit app can be previewed and tested end-to-end
during the build. Not part of the shipped product.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pgserver
import psycopg2

DATA_DIR = str(Path(__file__).parent / "_pgdata_appdev")
srv = pgserver.get_server(DATA_DIR)
uri = srv.get_uri()
print("embedded postgres:", uri, flush=True)

for attempt in range(10):
    try:
        base_conn = psycopg2.connect(uri)
        break
    except psycopg2.OperationalError as e:
        print(f"connect attempt {attempt} failed: {e}", flush=True)
        time.sleep(2)
else:
    raise SystemExit("could not connect")

base_conn.autocommit = True
with base_conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_database WHERE datname='bdm_tool'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE bdm_tool")
base_conn.close()

app_uri = uri.rsplit("/", 1)[0] + "/bdm_tool"
os.environ["DATABASE_URL"] = app_uri

env_path = Path(__file__).parent.parent / ".env"
env_path.write_text(f"DATABASE_URL={app_uri}\n")
print("wrote .env with", app_uri, flush=True)

import seed
seed.main()

print("\nDB ready and seeded. Sleeping to stay alive for app testing.", flush=True)
time.sleep(3000)
