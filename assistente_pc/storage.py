"""Dados locais explícitos. Uma conexão por operação permite uso na interface."""
import json
from contextlib import contextmanager
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .planner import validate_plan


def data_directory():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "AssistentePC"


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "assistant.sqlite3"
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS memories (name TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS routines (name TEXT PRIMARY KEY, plan TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, created TEXT NOT NULL, request TEXT NOT NULL,
                    plan TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id)
                    ON DELETE CASCADE, page INTEGER NOT NULL, content TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def clean_name(name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("Use um nome de 1 a 100 caracteres.")
        name = name.strip().casefold()
        if any(ord(c) < 32 for c in name):
            raise ValueError("Nome contém caracteres de controle.")
        return name

    def memories(self):
        with self.connect() as db:
            return dict(db.execute("SELECT name, value FROM memories ORDER BY name").fetchall())

    def remember(self, name, value):
        name = self.clean_name(name)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 1000:
            raise ValueError("A preferência deve ter de 1 a 1000 caracteres.")
        with self.connect() as db:
            if db.execute("SELECT count(*) FROM memories").fetchone()[0] >= 50 and name not in self.memories():
                raise ValueError("Limite de 50 memórias. Exclua alguma antes de adicionar outra.")
            db.execute("INSERT OR REPLACE INTO memories VALUES (?, ?)", (name, value.strip()))

    def routines(self):
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT name FROM routines ORDER BY name")]

    def save_routine(self, name, plan):
        name = self.clean_name(name)
        validate_plan(plan)
        if not plan["actions"]:
            raise ValueError("Não há ações para salvar como rotina.")
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO routines VALUES (?, ?)",
                       (name, json.dumps(plan, ensure_ascii=False)))

    def routine(self, name):
        with self.connect() as db:
            row = db.execute("SELECT plan FROM routines WHERE name=?", (self.clean_name(name),)).fetchone()
        if row is None:
            raise ValueError("Rotina não encontrada.")
        return validate_plan(json.loads(row[0]))

    def delete(self, category, name):
        if category not in ("memories", "routines"):
            raise ValueError("Categoria inválida.")
        with self.connect() as db:
            db.execute(f"DELETE FROM {category} WHERE name=?", (self.clean_name(name),))

    def log(self, request, plan, status):
        # Chamado somente quando o usuário habilita histórico.
        with self.connect() as db:
            db.execute("INSERT INTO history(created,request,plan,status) VALUES (?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), request,
                        json.dumps(plan, ensure_ascii=False), status))
            db.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 200)")

    def history(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT created, request, status FROM history ORDER BY id DESC LIMIT 50")]

    def suggestions(self):
        # Agrupa pelas ações, não pela explicação variável produzida pelo modelo.
        with self.connect() as db:
            rows = db.execute("SELECT plan FROM history WHERE status='completed'").fetchall()
        groups = {}
        for row in rows:
            plan = validate_plan(json.loads(row[0]))
            if not plan["actions"]:
                continue
            key = json.dumps(plan["actions"], sort_keys=True, ensure_ascii=False)
            entry = groups.setdefault(key, {"plan": plan, "uses": 0})
            entry["uses"] += 1
        return sorted((v for v in groups.values() if v["uses"] >= 3),
                      key=lambda v: -v["uses"])[:5]

    def clear_history(self):
        with self.connect() as db:
            db.execute("DELETE FROM history")

    def clear_all(self):
        with self.connect() as db:
            for table in ("memories", "routines", "history", "chunks", "documents"):
                db.execute(f"DELETE FROM {table}")
