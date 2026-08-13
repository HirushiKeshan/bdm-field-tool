"""
Dev-only harness: spins up an embedded local Postgres (pgserver, no docker
needed) purely to prove seed.py and the schema actually work end-to-end.
Not part of the shipped app -- the shipped app talks to docker-compose
Postgres or Supabase via DATABASE_URL. This file is not committed...
actually let's keep it out of the repo, it's a throwaway dev tool.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pgserver

DATA_DIR = str(Path(__file__).parent / "_pgdata_dev2")
srv = pgserver.get_server(DATA_DIR)
uri = srv.get_uri()
print("embedded postgres:", uri)

import time

import psycopg2

for attempt in range(10):
    try:
        base_conn = psycopg2.connect(uri)
        break
    except psycopg2.OperationalError as e:
        print(f"connect attempt {attempt} failed: {e}")
        time.sleep(2)
else:
    raise SystemExit("could not connect to embedded postgres")
base_conn.autocommit = True
with base_conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_database WHERE datname='bdm_tool'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE bdm_tool")
base_conn.close()

app_uri = uri.rsplit("/", 1)[0] + "/bdm_tool"
os.environ["DATABASE_URL"] = app_uri
print("app DATABASE_URL:", app_uri)

import seed
seed.main()

# quick sanity queries
conn = psycopg2.connect(app_uri)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM outlets")
print("outlets rows:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM billing_monthly")
print("billing rows:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM visits")
print("visits rows:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM outlets WHERE possible_duplicate_of IS NOT NULL")
print("flagged duplicates:", cur.fetchone()[0])
cur.execute("SELECT confidence, count(*) FROM visits GROUP BY confidence ORDER BY 2 DESC")
print("confidence mix:", cur.fetchall())
cur.execute("SELECT count(*) FROM visits WHERE gps_anomaly IS NOT NULL")
print("gps anomalies:", cur.fetchone()[0])
conn.close()

with open(Path(__file__).parent / "_pg_uri_persist.txt", "w") as f:
    f.write(app_uri)
print("\nSeed test done. URI was:", app_uri)
