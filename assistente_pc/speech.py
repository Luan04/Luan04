"""Síntese opcional com vozes instaladas no Windows, sem serviço online."""
import platform
import time


def speak(text, cancel=None):
    if cancel is not None and cancel.is_set():
        return
    if platform.system() != "Windows":
        raise RuntimeError("A resposta falada desta versão requer vozes do Windows.")
    import ctypes
    # Chamado em worker: inicializa COM neste thread, sem executar comandos de shell.
    result = ctypes.windll.ole32.CoInitialize(None)
    engine = None
    loop_started = False
    try:
        import pyttsx3
        engine = pyttsx3.init("sapi5")
        voices = engine.getProperty("voices")
        portuguese = [v for v in voices if any(part in (v.id + v.name).lower()
                                               for part in ("portugu", "brazil", "pt-br", "pt-pt"))]
        if not portuguese:
            engine.stop()
            raise RuntimeError("Instale uma voz de português nas configurações de Fala do Windows.")
        engine.setProperty("voice", portuguese[0].id)
        engine.setProperty("rate", 175)
        engine.say(text[:3000])
        engine.startLoop(False)
        loop_started = True
        while engine.isBusy():
            if cancel is not None and cancel.is_set():
                break
            engine.iterate()
            time.sleep(0.02)
    finally:
        if engine is not None:
            engine.stop()
            if loop_started:
                engine.endLoop()
        if result in (0, 1):
            ctypes.windll.ole32.CoUninitialize()
