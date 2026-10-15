import json
import unittest
from unittest.mock import patch, MagicMock

from assistente_pc.__main__ import is_confirmed
from assistente_pc.executor import execute_plan
from assistente_pc.planner import make_plan, validate_plan


def plan(*actions):
    return {"message": "Plano", "actions": list(actions)}


def action(kind="open_app", value="calculadora"):
    return {"type": kind, "value": value}


class SafetyTests(unittest.TestCase):
    def test_allowed_actions(self):
        for kind, value in [("open_app", "calculadora"), ("open_site", "youtube"),
                            ("search_web", "previsão do tempo"), ("type_text", "Olá, São Paulo!"),
                            ("shortcut", "copiar"), ("volume", "silenciar")]:
            self.assertEqual(validate_plan(plan(action(kind, value)))["actions"][0]["value"], value)

    def test_refusal_without_actions(self):
        self.assertEqual(validate_plan(plan())["actions"], [])

    def test_forbidden_actions(self):
        for kind, value in [("shell", "whoami"), ("open_app", "powershell"),
                            ("open_site", "file:///C:/Windows"), ("shortcut", "win+r"),
                            ("shortcut", "enter"), ("volume", "100")]:
            with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                validate_plan(plan(action(kind, value)))

    def test_reject_control_characters(self):
        for value in ("comando\n", "comando\r", "texto\t", "texto\x00", "texto\x1b"):
            with self.assertRaises(ValueError):
                validate_plan(plan(action("type_text", value)))

    def test_malformed_plans(self):
        for value in (None, [], {}, {"message": "oi", "actions": "oops"},
                      {"message": 3, "actions": []}, {**plan(), "extra": True},
                      plan({"type": [], "value": "oi"}), plan({"type": "open_app"}),
                      plan(action("type_text", "")), plan(action("type_text", "x" * 2001)),
                      plan(action("type_text", 12))):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_plan(value)

    def test_action_limit(self):
        with self.assertRaises(ValueError):
            validate_plan(plan(*[action()] * 6))

    def test_confirmation_exact_match(self):
        self.assertTrue(is_confirmed(" Executar "))
        for value in ("", "sim", "não executar", "executar depois", "pode executar"):
            self.assertFalse(is_confirmed(value))

    @patch("assistente_pc.executor.open_app")
    def test_validates_whole_plan_before_effects(self, launch):
        with self.assertRaises(ValueError):
            execute_plan(plan(action(), action("shell", "whoami")))
        launch.assert_not_called()

    @patch("assistente_pc.planner.urlopen")
    def test_model_is_local_and_response_is_validated(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({"message": {"content": json.dumps(plan(action()))}})
        urlopen.return_value.__enter__.return_value = response
        self.assertEqual(make_plan("abra a calculadora"), plan(action()))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        self.assertFalse(json.loads(request.data)["stream"])

    @patch("assistente_pc.planner.urlopen")
    def test_rejects_model_generated_shell(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({"message": {"content": json.dumps(plan(action("shell", "dir")))}})
        urlopen.return_value.__enter__.return_value = response
        with self.assertRaises(ValueError):
            make_plan("execute um comando")

    @patch("assistente_pc.planner.urlopen")
    def test_invalid_json_from_model(self, urlopen):
        response = MagicMock()
        response.read.return_value = '{"message":{"content":"not json"}}'
        urlopen.return_value.__enter__.return_value = response
        with self.assertRaises(ValueError):
            make_plan("oi")

    @patch("assistente_pc.executor.platform.system", return_value="Linux")
    def test_non_windows_execution_blocked(self, system):
        with self.assertRaises(RuntimeError):
            execute_plan(plan(action()))


if __name__ == "__main__":
    unittest.main()
