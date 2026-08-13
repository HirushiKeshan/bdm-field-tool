"""
Single place that knows how to get a Postgres connection. Works the same
way whether Postgres is the docker-compose service, a local pgserver
instance (used by the test suite), or a real Supabase project -- all three
are just a DATABASE_URL. Never falls back to a local file.
"""
import os
from pathlib import Path

import psycopg2
import psycopg2.extras

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env (local/docker) "
        "or add DATABASE_URL to Streamlit secrets (cloud deploy)."
    )


def get_connection():
    return psycopg2.connect(get_database_url())


def dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def apply_schema(conn) -> None:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
