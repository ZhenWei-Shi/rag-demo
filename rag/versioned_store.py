"""Atomic visibility manifest for the single-worker Chroma demo.

New chunks stay invisible until a SQLite transaction selects their IDs. A crash
before commit leaves the old version readable; cleanup never determines visibility.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def manifest(collection):
    directory = Path(os.getenv("RAG_DATA_DIR", "chroma_data"))
    directory.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(directory / "versions.sqlite3", timeout=30) as db:
        db.execute("CREATE TABLE IF NOT EXISTS versions (collection TEXT, source TEXT, ids TEXT NOT NULL, PRIMARY KEY(collection,source))")
        yield db, str(collection.id)


def selected(collection):
    with manifest(collection) as (db, key):
        return {source: set(json.loads(ids)) for source, ids in db.execute(
            "SELECT source,ids FROM versions WHERE collection=?", (key,))}


def publish(collection, source, ids):
    with manifest(collection) as (db, key):
        db.execute("INSERT OR REPLACE INTO versions VALUES (?,?,?)", (key, source, json.dumps(ids)))


def visible(collection):
    choices = selected(collection)
    records = collection.get(include=["metadatas"])
    return [(identifier, meta) for identifier, meta in zip(records["ids"], records["metadatas"])
            if identifier in choices.get(meta["source"], set())
            or (meta["source"] not in choices and "revision" not in meta)]
