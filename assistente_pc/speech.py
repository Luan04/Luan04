"""Síntese opcional com vozes instaladas no Windows, sem serviço online."""
import platform


def speak(text):
    if platform.system() != "Windows":
        raise RuntimeError("A resposta falada desta versão requer vozes do Windows.")
    import ctypes
    # Chamado em worker: inicializa COM neste thread, sem executar comandos de shell.
    result = ctypes.windll.ole32.CoInitialize(None)
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
        engine.runAndWait()
        engine.stop()
    finally:
        if result in (0, 1):
            ctypes.windll.ole32.CoUninitialize()
