"""Microfone ativo somente durante uma captura solicitada pelo usuário."""
import json
import queue
import time
from pathlib import Path


class Microphone:
    def __init__(self, model_path, device=None):
        from vosk import Model, SetLogLevel
        if not Path(model_path).is_dir():
            raise RuntimeError(f"Modelo de voz não encontrado: {model_path}. Consulte o README.")
        SetLogLevel(-1)
        self.model = Model(str(model_path))
        self.device = device

    def listen(self, seconds=15, cancel=None):
        import sounddevice as sd
        from vosk import KaldiRecognizer
        rate = int(sd.query_devices(self.device, "input")["default_samplerate"])
        recognizer = KaldiRecognizer(self.model, rate)
        chunks = queue.Queue(maxsize=100)

        def callback(data, frames, timing, status):
            try:
                chunks.put_nowait(bytes(data))
            except queue.Full:
                pass

        print(f"Ouvindo por até {seconds}s… fale e faça uma pausa.", flush=True)
        with sd.RawInputStream(samplerate=rate, blocksize=4000, device=self.device,
                               dtype="int16", channels=1, callback=callback):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    return ""
                try:
                    chunk = chunks.get(timeout=0.2)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(chunk):
                    text = json.loads(recognizer.Result()).get("text", "").strip()
                    if text:
                        return text
        return json.loads(recognizer.FinalResult()).get("text", "").strip()
