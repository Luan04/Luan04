import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from assistente_pc.speech import speak


class SpeechTests(unittest.TestCase):
    def test_already_cancelled_does_not_initialize_audio(self):
        event = threading.Event()
        event.set()
        with patch('assistente_pc.speech.platform.system') as system:
            speak('oi', cancel=event)
            system.assert_not_called()

    def test_sapi_loop_is_pumped_and_closed(self):
        engine = Mock()
        engine.getProperty.return_value = [SimpleNamespace(id='pt-BR', name='Portuguese')]
        engine.isBusy.side_effect = [True, True, False]
        pyttsx3 = Mock()
        pyttsx3.init.return_value = engine
        dll = Mock()
        dll.ole32.CoInitialize.return_value = 0
        with patch('assistente_pc.speech.platform.system', return_value='Windows'), \
                patch('ctypes.windll', dll, create=True), \
                patch.dict(sys.modules, {'pyttsx3': pyttsx3}), \
                patch('assistente_pc.speech.time.sleep'):
            speak('Olá!')
        self.assertEqual(engine.iterate.call_count, 2)
        engine.say.assert_called_once_with('Olá!')
        engine.stop.assert_called_once()
        engine.endLoop.assert_called_once()
        dll.ole32.CoUninitialize.assert_called_once()

    def test_cancel_during_speech_stops_engine(self):
        event = threading.Event()
        engine = Mock()
        engine.getProperty.return_value = [SimpleNamespace(id='pt-BR', name='Portuguese')]
        engine.isBusy.return_value = True
        engine.iterate.side_effect = event.set
        pyttsx3 = Mock()
        pyttsx3.init.return_value = engine
        dll = Mock()
        dll.ole32.CoInitialize.return_value = 0
        with patch('assistente_pc.speech.platform.system', return_value='Windows'), \
                patch('ctypes.windll', dll, create=True), \
                patch.dict(sys.modules, {'pyttsx3': pyttsx3}), \
                patch('assistente_pc.speech.time.sleep'):
            speak('Olá!', cancel=event)
        engine.iterate.assert_called_once()
        engine.stop.assert_called_once()
        engine.endLoop.assert_called_once()
