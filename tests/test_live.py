import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from assistente_pc.conversation import (action_policy, describe, quick_plan, review_plan,
                                        voice_confirmed, voice_stop, HISTORY_CHARACTERS)
from assistente_pc.live import LiveConversation
from assistente_pc.session import Session
from assistente_pc.storage import Store


def plan(kind='open_app', value='calculadora'):
    return {'message': 'Ação realizada!', 'actions': [{'type': kind, 'value': value}]}


class PolicyTests(unittest.TestCase):
    def test_voice_confirmation_is_exact(self):
        self.assertTrue(voice_confirmed('Confirmar execução.'))
        self.assertTrue(voice_confirmed('confirmar execucao'))
        for text in ('sim', 'executar', 'não confirmar execução', 'confirmar execução depois', ''):
            self.assertFalse(voice_confirmed(text))

    def test_stop_is_exact(self):
        self.assertTrue(voice_stop('Parar assistente!'))
        self.assertFalse(voice_stop('como parar assistente'))

    def test_defaults_require_confirmation(self):
        self.assertEqual(action_policy(plan()), 'confirm')
        self.assertEqual(action_policy(plan(), True), 'automatic')
        self.assertEqual(action_policy(plan('volume', 'aumentar'), True), 'automatic')

    def test_sites_and_search_never_automatic(self):
        self.assertEqual(action_policy(plan('open_site', 'google'), True), 'confirm')
        self.assertEqual(action_policy(plan('search_web', 'receitas'), True), 'confirm')

    def test_typing_shortcuts_and_long_plans_require_manual_review(self):
        for kind, value in [('type_text', 'oi'), ('shortcut', 'colar'), ('search_web', 'x' * 1000)]:
            self.assertEqual(action_policy(plan(kind, value), True), 'manual')
        mixed = plan()
        mixed['actions'].append({'type': 'type_text', 'value': 'oi'})
        self.assertEqual(action_policy(mixed, True), 'manual')

    def test_invalid_plan_cannot_reach_auto_execution(self):
        with self.assertRaises(ValueError):
            action_policy(plan('shell', 'dir'), True)

    def test_false_success_message_is_replaced(self):
        original = plan()
        reviewed = review_plan(original)
        self.assertNotIn('realizada', reviewed['message'])
        self.assertIn('Ainda não executei', reviewed['message'])
        self.assertEqual(original['message'], 'Ação realizada!')
        self.assertEqual(describe(reviewed), 'abrir calculadora')

    def test_only_unambiguous_commands_take_fast_path(self):
        self.assertEqual(quick_plan('Abra a calculadora, por favor.')['actions'], plan()['actions'])
        self.assertIsNotNone(quick_plan('abrir bloco de notas'))
        for text in ['não abra a calculadora', 'como abrir a calculadora', 'abra a calculadora e digite oi',
                     'se eu pedir, abra a calculadora', 'abrir powershell', 'oi, tudo bem?']:
            self.assertIsNone(quick_plan(text))


class LiveLoopTests(unittest.TestCase):
    def setUp(self):
        self.cancel = threading.Event()
        self.session = Mock()
        self.mic = Mock()
        self.speaker = Mock()
        self.executor = Mock()
        self.events = []
        # Keep tests immediate while preserving event semantics.
        self.wait = patch.object(self.cancel, 'wait', side_effect=lambda seconds: self.cancel.is_set())
        self.wait.start()
        self.addCleanup(self.wait.stop)

    def run_live(self, texts, response, **options):
        self.mic.listen.side_effect = texts
        self.session.prepare.return_value = response
        LiveConversation(self.session, self.mic, self.speaker, self.cancel,
                         lambda key, value: self.events.append((key, value)),
                         executor=self.executor, **options).run()

    def test_conversation_reopens_microphone_without_clicks(self):
        self.run_live(['oi', 'e depois?', 'parar assistente'], {'message': 'Vamos conversar.', 'actions': []})
        self.assertEqual(self.session.prepare.call_count, 2)
        self.assertEqual(self.mic.listen.call_count, 3)
        self.executor.assert_not_called()
        self.session.store.log.assert_not_called()

    def test_exact_voice_confirmation_executes_once(self):
        self.run_live(['abrir calculadora', 'confirmar execução', 'parar assistente'], plan())
        self.executor.assert_called_once()
        self.session.record_result.assert_called_once_with(review_plan(plan()), 'completed')
        self.session.store.log.assert_not_called()

    def test_negation_cancels_plan(self):
        self.run_live(['abrir calculadora', 'não confirmar execução', 'parar assistente'], plan())
        self.executor.assert_not_called()
        self.session.record_result.assert_called_once_with(review_plan(plan()), 'cancelled')

    def test_empty_confirmation_cancels(self):
        self.run_live(['abrir calculadora', '', 'parar assistente'], plan())
        self.executor.assert_not_called()

    def test_stop_during_confirmation_never_executes(self):
        self.run_live(['abrir calculadora', 'parar assistente'], plan())
        self.executor.assert_not_called()

    def test_simple_auto_mode_requires_opt_in(self):
        self.run_live(['abrir calculadora', 'parar assistente'], plan(), allow_simple=True, history=True)
        self.executor.assert_called_once()
        self.assertEqual(self.mic.listen.call_count, 2)
        self.assertEqual(self.session.store.log.call_args.args[-1], 'completed')

    def test_manual_plan_stops_loop_without_partial_execution(self):
        mixed = plan()
        mixed['actions'].append({'type': 'type_text', 'value': 'oi'})
        self.run_live(['abra e escreva'], mixed, allow_simple=True)
        self.executor.assert_not_called()
        self.assertEqual(self.mic.listen.call_count, 1)
        self.assertTrue(any(kind == 'plan' for kind, value in self.events))

    def test_speaker_failure_never_opens_microphone_or_executes(self):
        self.speaker.side_effect = RuntimeError('Voz ausente')
        with self.assertRaises(RuntimeError):
            self.run_live(['oi'], plan(), allow_simple=True)
        self.mic.listen.assert_not_called()
        self.executor.assert_not_called()

    def test_cancel_during_planning_discards_result(self):
        def prepare(*args):
            self.cancel.set()
            return plan()
        self.session.prepare.side_effect = prepare
        self.run_live(['abra calculadora'], plan(), allow_simple=True)
        self.executor.assert_not_called()
        self.assertFalse(any(kind in ('plan', 'reply') for kind, value in self.events))

    def test_cancel_while_announcing_prevents_auto_execution(self):
        def speak(text, cancel=None):
            if text.startswith('Vou '):
                self.cancel.set()
        self.speaker.side_effect = speak
        self.run_live(['abra calculadora'], plan(), allow_simple=True)
        self.executor.assert_not_called()

    def test_executor_failure_ends_session_and_records_failure(self):
        self.executor.side_effect = RuntimeError('Falha')
        with self.assertRaises(RuntimeError):
            self.run_live(['abra calculadora'], plan(), allow_simple=True, history=True)
        self.assertEqual(self.mic.listen.call_count, 1)
        self.assertEqual(self.session.store.log.call_args.args[-1], 'failed')
        self.assertEqual(self.session.record_result.call_args.args[-1], 'failed')

    def test_silence_pauses_session(self):
        self.run_live([''] * 8, plan())
        self.executor.assert_not_called()
        self.session.prepare.assert_not_called()

    def test_listening_never_overlaps_speech(self):
        order = []
        self.speaker.side_effect = lambda *a, **kw: order.append('speak')
        self.mic.listen.side_effect = lambda **kw: order.append('listen') or 'parar assistente'
        LiveConversation(self.session, self.mic, self.speaker, self.cancel,
                         lambda *args: None, executor=self.executor).run()
        self.assertEqual(order, ['speak', 'listen', 'speak'])


class ContextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.session = Session(Store(temp.name))

    @patch('assistente_pc.session.make_plan')
    def test_quick_command_does_not_call_model(self, model):
        reply = self.session.prepare('abra a calculadora')
        self.assertEqual(reply['actions'], plan()['actions'])
        model.assert_not_called()

    def test_actual_outcome_added_to_context(self):
        self.session.record_result(plan(), 'failed')
        self.assertIn('Resultado real do executor', self.session.turns[-1]['content'])
        self.assertIn('Falha', self.session.turns[-1]['content'])

    def test_history_is_bounded_by_characters_and_messages(self):
        self.session.turns = [{'role': 'user', 'content': 'x' * 4000} for _ in range(30)]
        self.session.trim()
        self.assertLessEqual(len(self.session.turns), 24)
        self.assertLessEqual(sum(len(t['content']) for t in self.session.turns), HISTORY_CHARACTERS)
