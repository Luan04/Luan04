import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch

from assistente_pc.__main__ import main
from assistente_pc.storage import Store


class CliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = temp.name

    def command(self, *args):
        output = io.StringIO()
        with patch("sys.argv", ["assistente_pc", "--data-dir", self.directory, *args]), contextlib.redirect_stdout(output):
            main()
        return output.getvalue()

    def test_memory_management_without_model_or_microphone(self):
        self.command("--remember", "profissão", "Designer")
        self.assertIn("Designer", self.command("--list-memories"))
        self.command("--forget", "profissão")
        self.assertNotIn("Designer", self.command("--list-memories"))

    def test_routine_dry_run_does_not_execute(self):
        Store(self.directory).save_routine("teste", {"message": "ok", "actions": [{"type": "open_app", "value": "calculadora"}]})
        with patch("assistente_pc.executor.execute_plan") as execute:
            output = self.command("--routine", "teste", "--dry-run", "--history")
            self.assertIn("calculadora", output)
            execute.assert_not_called()
        self.assertFalse(Store(self.directory).history())

    @patch("assistente_pc.session.make_plan")
    def test_cancelled_plan_does_not_execute_or_log_by_default(self, model):
        model.return_value = {"message": "ok", "actions": [{"type": "open_app", "value": "calculadora"}]}
        with patch("builtins.input", return_value="não executar"), patch("assistente_pc.executor.execute_plan") as execute:
            self.command("--text", "abra a calculadora")
            execute.assert_not_called()
        self.assertFalse(Store(self.directory).history())

    @patch("assistente_pc.session.make_plan")
    def test_explicit_confirmation_and_history(self, model):
        model.return_value = {"message": "ok", "actions": [{"type": "open_app", "value": "calculadora"}]}
        with patch("builtins.input", return_value="executar"), patch("assistente_pc.executor.execute_plan") as execute:
            self.command("--text", "abra a calculadora", "--history")
            execute.assert_called_once()
            self.assertEqual(execute.call_args.args[0]["actions"], model.return_value["actions"])
            self.assertIn("Ainda não executei", execute.call_args.args[0]["message"])
        self.assertEqual(Store(self.directory).history()[0]["status"], "completed")

    def test_dry_run_rejects_memory_mutation(self):
        with self.assertRaises(ValueError):
            self.command("--remember", "pref", "value", "--dry-run")
        self.assertFalse(Store(self.directory).memories())

    def test_clear_data_requires_exact_confirmation(self):
        store = Store(self.directory)
        store.remember("pref", "value")
        with patch("builtins.input", return_value="nao"):
            self.command("--clear-data")
        self.assertTrue(store.memories())
        with patch("builtins.input", return_value="APAGAR"):
            self.command("--clear-data")
        self.assertFalse(store.memories())

    @patch("assistente_pc.session.make_plan", side_effect=ValueError("invalid plan"))
    def test_one_shot_failure_has_nonzero_exit(self, model):
        with self.assertRaises(SystemExit) as error:
            self.command("--text", "test", "--dry-run")
        self.assertEqual(error.exception.code, 1)
