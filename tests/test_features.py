import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from assistente_pc.executor import ExecutionCancelled, authorize_target, execute_plan, pause
from assistente_pc.knowledge import Knowledge, tokens
from assistente_pc.session import Session
from assistente_pc.storage import Store


def plan(message="Abrir calculadora"):
    return {"message": message, "actions": [{"type": "open_app", "value": "calculadora"}]}


class LocalDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.knowledge = Knowledge(self.store)

    def document(self, name="notas.txt", content="O projeto Aurora usa Python e o prazo é sexta-feira."):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_memories_persist_update_and_delete(self):
        self.store.remember(" Profissão ", "Programador")
        reopened = Store(self.root / "state")
        self.assertEqual(reopened.memories(), {"profissão": "Programador"})
        reopened.remember("profissão", "Designer")
        self.assertEqual(self.store.memories()["profissão"], "Designer")
        reopened.delete("memories", "profissão")
        self.assertFalse(self.store.memories())

    def test_memory_limits(self):
        for name, value in [("", "oi"), ("ok", ""), ("a" * 101, "ok"), ("ok", "x" * 1001)]:
            with self.assertRaises(ValueError):
                self.store.remember(name, value)
        for i in range(50):
            self.store.remember(str(i), "value")
        with self.assertRaises(ValueError):
            self.store.remember("extra", "value")
        self.store.remember("0", "updated")

    def test_routine_roundtrip(self):
        self.store.save_routine("Trabalho", plan())
        self.assertEqual(self.store.routines(), ["trabalho"])
        self.assertEqual(self.store.routine("TRABALHO"), plan())
        self.store.delete("routines", "trabalho")
        with self.assertRaises(ValueError):
            self.store.routine("trabalho")

    def test_invalid_routine_is_not_saved(self):
        for invalid in ({"message": "nada", "actions": []},
                        {"message": "ruim", "actions": [{"type": "shell", "value": "dir"}]}):
            with self.assertRaises(ValueError):
                self.store.save_routine("bad", invalid)
        self.assertFalse(self.store.routines())

    def test_routine_revalidated_on_load(self):
        with self.store.connect() as db:
            db.execute("INSERT INTO routines VALUES (?,?)", ("bad", '{"message":"x","actions":[{"type":"shell","value":"dir"}]}'))
        with self.assertRaises(ValueError):
            self.store.routine("bad")

    def test_history_is_empty_until_explicitly_logged(self):
        self.store.remember("pref", "value")
        self.store.save_routine("routine", plan())
        self.assertEqual(self.store.history(), [])

    def test_suggestions_group_actions_not_explanations(self):
        for i in range(3):
            self.store.log("pedido", plan(str(i)), "completed")
        self.store.log("pedido", plan(), "failed")
        self.assertEqual(self.store.suggestions()[0]["uses"], 3)
        self.assertFalse(self.store.routines())
        self.store.clear_history()
        self.assertFalse(self.store.history())
        self.assertFalse(self.store.suggestions())

    def test_history_retention(self):
        for i in range(205):
            self.store.log(str(i), plan(), "completed")
        self.assertEqual(len(self.store.history()), 50)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM history").fetchone()[0], 200)

    def test_document_import_search_and_remove(self):
        path = self.document()
        self.assertEqual(self.knowledge.import_file(path), 1)
        result = self.knowledge.search("Qual o prazo do projeto Aurora?")
        self.assertEqual(result[0]["name"], "notas.txt")
        self.assertIn("sexta-feira", result[0]["content"])
        self.knowledge.remove(self.knowledge.documents()[0]["id"])
        self.assertFalse(self.knowledge.search("Aurora"))
        self.assertTrue(path.exists())

    def test_document_reimport_updates_snapshot(self):
        path = self.document()
        self.knowledge.import_file(path)
        path.write_text("Novo conteúdo com bananas", encoding="utf-8")
        self.assertTrue(self.knowledge.search("Aurora"))
        self.knowledge.import_file(path)
        self.assertFalse(self.knowledge.search("Aurora"))
        self.assertTrue(self.knowledge.search("bananas"))
        self.assertEqual(len(self.knowledge.documents()), 1)

    def test_import_failures_keep_old_snapshot(self):
        path = self.document()
        self.knowledge.import_file(path)
        path.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.knowledge.import_file(path)
        self.assertTrue(self.knowledge.search("Aurora"))
        for name, content in [("app.exe", "code"), ("empty.txt", ""), ("large.md", "a" * 500001)]:
            with self.assertRaises(ValueError):
                self.knowledge.import_file(self.document(name, content))

    def test_accent_search(self):
        self.knowledge.import_file(self.document(content="Informação: férias disponíveis em março."))
        self.assertTrue(self.knowledge.search("informacao ferias marco"))
        self.assertFalse(self.knowledge.search("de a o"))
        self.assertEqual(tokens("FÉRIAS férias"), {"ferias"})

    @patch("assistente_pc.knowledge.request_json")
    def test_no_match_does_not_call_model(self, request):
        self.assertIn("Não encontrei", self.knowledge.answer("aurora", "local"))
        request.assert_not_called()

    @patch("assistente_pc.knowledge.request_json")
    def test_document_answer_attaches_real_sources(self, request):
        self.knowledge.import_file(self.document())
        source = self.knowledge.search("Aurora")[0]
        request.return_value = {"answer": "Sexta-feira.", "sources": [source["id"]]}
        answer = self.knowledge.answer("prazo Aurora", "local")
        self.assertIn("notas.txt", answer)
        self.assertIn("página 1", answer)
        self.assertIn("Trecho:", answer)

    @patch("assistente_pc.knowledge.request_json")
    def test_invented_sources_or_actions_rejected(self, request):
        self.knowledge.import_file(self.document())
        for response in [{"answer": "oi", "sources": [999999]}, {"answer": "oi", "sources": [True]},
                         {"answer": "oi", "sources": [], "actions": []}, {"answer": [], "sources": []}]:
            request.return_value = response
            with self.assertRaises(ValueError):
                self.knowledge.answer("Aurora", "local")

    def test_clear_all_keeps_original_files(self):
        path = self.document()
        self.knowledge.import_file(path)
        self.store.remember("pref", "value")
        self.store.save_routine("work", plan())
        self.store.log("req", plan(), "completed")
        self.store.clear_all()
        self.assertEqual(self.store.memories(), {})
        self.assertEqual(self.store.routines(), [])
        self.assertEqual(self.store.history(), [])
        self.assertEqual(self.knowledge.documents(), [])
        self.assertTrue(path.exists())

    @patch("assistente_pc.session.make_plan")
    def test_session_uses_explicit_memory_and_bounded_context(self, make):
        self.store.remember("profissão", "Designer")
        make.return_value = plan()
        session = Session(self.store)
        for i in range(18):
            session.prepare(f"pedido {i}")
        self.assertEqual(make.call_args.args[2], {"profissão": "Designer"})
        self.assertEqual(len(session.turns), 24)
        self.assertIn("apenas propostas", session.turns[-1]["content"])
        self.assertFalse(self.store.history())
        session.reset()
        self.assertEqual(session.turns, [])

    @patch("assistente_pc.session.make_plan")
    def test_named_routine_does_not_use_model(self, make):
        self.store.save_routine("trabalho", plan())
        result = Session(self.store).prepare("executar rotina trabalho")
        self.assertEqual(result["actions"], plan()["actions"])
        self.assertIn("Ainda não executei", result["message"])
        make.assert_not_called()

    @patch("assistente_pc.session.request_json")
    def test_conversation_cannot_return_actions(self, request):
        request.return_value = {"answer": "Olá!"}
        session = Session(self.store)
        self.assertEqual(session.prepare("oi", "conversa")["actions"], [])
        request.return_value = {"answer": "ok", "actions": plan()["actions"]}
        with self.assertRaises(ValueError):
            session.prepare("oi", "conversa")


class ExecutionProtectionTests(unittest.TestCase):
    def test_cancel_before_any_action(self):
        event = threading.Event()
        event.set()
        with patch("assistente_pc.executor.open_app") as launch:
            with self.assertRaises(ExecutionCancelled):
                execute_plan(plan(), cancel=event)
            launch.assert_not_called()

    def test_wait_is_interruptible(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(ExecutionCancelled):
            pause(10, event)

    def test_typing_only_in_allowed_editors(self):
        for executable in ("notepad.exe", "WINWORD.EXE", "wordpad.exe"):
            authorize_target("type_text", "oi", executable)
        for executable in ("cmd.exe", "powershell.exe", "WindowsTerminal.exe", "Code.exe", "chrome.exe", "python.exe"):
            with self.subTest(executable=executable), self.assertRaises(RuntimeError):
                authorize_target("type_text", "oi", executable)

    def test_clipboard_shortcuts_blocked_in_shells(self):
        with self.assertRaises(RuntimeError):
            authorize_target("shortcut", "colar", "cmd.exe")
        authorize_target("shortcut", "colar", "chrome.exe")
        authorize_target("shortcut", "mostrar_area_de_trabalho", "cmd.exe")
