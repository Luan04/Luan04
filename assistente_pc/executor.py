"""Executa apenas ações validadas, sem shell ou comandos fornecidos pela IA."""
import ctypes
import os
import platform
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from .planner import SHORTCUTS, SITES, VOLUMES, validate_plan


def open_app(name):
    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    standard = {"bloco_de_notas": system / "System32/notepad.exe",
                "calculadora": system / "System32/calc.exe",
                "explorador": system / "explorer.exe"}
    if name in standard:
        subprocess.Popen([str(standard[name])], shell=False)
        return
    relative = {"edge": "Microsoft/Edge/Application/msedge.exe",
                "chrome": "Google/Chrome/Application/chrome.exe",
                "firefox": "Mozilla Firefox/firefox.exe"}[name]
    for root in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(root)
        if base and (path := Path(base) / relative).is_file():
            subprocess.Popen([str(path)], shell=False)
            return
    raise RuntimeError(f"Navegador {name} não encontrado. Instale-o ou escolha outro.")


TEXT_APPS = {"notepad.exe", "wordpad.exe", "winword.exe"}
SHORTCUT_APPS = TEXT_APPS | {"chrome.exe", "msedge.exe", "firefox.exe", "explorer.exe"}


def authorize_target(kind, value, executable):
    if kind == "shortcut" and value in ("alternar_janela", "mostrar_area_de_trabalho"):
        return
    allowed = TEXT_APPS if kind == "type_text" else SHORTCUT_APPS
    if executable.casefold() not in allowed:
        raise RuntimeError("Janela não autorizada para esta ação. Digitação: Bloco de Notas, Word ou WordPad. "
                           "Atalhos: esses editores, navegadores suportados e Explorador.")


def foreground():
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    window = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    if not window or not user32.GetWindowThreadProcessId(window, ctypes.byref(pid)):
        raise RuntimeError("Não foi possível identificar a janela ativa.")
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        raise RuntimeError("Não foi possível verificar o programa ativo. Ação bloqueada.")
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise RuntimeError("Não foi possível verificar o executável ativo.")
        return window, Path(buffer.value).name
    finally:
        kernel32.CloseHandle(handle)


def type_unicode(text, cancel=None, target_window=None):
    # SendInput suporta acentos sem sobrescrever a área de transferência.
    from ctypes import wintypes
    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]

    send = ctypes.windll.user32.SendInput
    send.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    send.restype = wintypes.UINT
    import pyautogui
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    encoded = text.encode("utf-16-le")
    for offset in range(0, len(encoded), 2):
        check_cancel(cancel)
        pyautogui.failSafeCheck()
        if target_window is not None and user32.GetForegroundWindow() != target_window:
            raise RuntimeError("O foco mudou durante a digitação. Operação interrompida.")
        unit = int.from_bytes(encoded[offset:offset + 2], "little")
        events = (INPUT * 2)()
        for index, flag in enumerate((0x0004, 0x0004 | 0x0002)):
            events[index].type = 1
            events[index].ki = KEYBDINPUT(0, unit, flag, 0, 0)
        if send(2, events, ctypes.sizeof(INPUT)) != 2:
            raise RuntimeError("O Windows bloqueou a digitação. Não execute como administrador.")
        time.sleep(0.01)


class ExecutionCancelled(RuntimeError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ExecutionCancelled("Execução interrompida pelo usuário.")


def pause(seconds, cancel):
    if cancel is None:
        time.sleep(seconds)
    elif cancel.wait(seconds):
        check_cancel(cancel)


def execute_plan(plan, cancel=None, before_focus=None, on_progress=None):
    check_cancel(cancel)
    validate_plan(plan)  # Valida TODO o plano antes de qualquer efeito.
    if platform.system() != "Windows":
        raise RuntimeError("A execução de ações desta versão requer Windows.")
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.3
    for action in plan["actions"]:
        check_cancel(cancel)
        pyautogui.failSafeCheck()
        kind, value = action["type"], action["value"]
        (on_progress or print)(f"Executando: {kind} → {value}")
        if kind == "open_app":
            open_app(value)
            pause(2, cancel)
        elif kind in ("open_site", "search_web"):
            url = SITES[value] if kind == "open_site" else "https://www.google.com/search?q=" + quote_plus(value)
            if not webbrowser.open(url):
                raise RuntimeError("Não foi possível abrir o navegador padrão.")
            pause(2, cancel)
        else:
            if kind in ("type_text", "shortcut"):
                if before_focus:
                    if not before_focus("Confirme e selecione a janela de destino em 5 segundos. "
                                        "Não use terminais nem janelas administrativas."):
                        raise ExecutionCancelled("Seleção de janela cancelada.")
                else:
                    input("Confira a janela de destino. Pressione Enter aqui e selecione a janela em 5 segundos…")
                pause(5, cancel)
                check_cancel(cancel)
                pyautogui.failSafeCheck()
            target = None
            if kind in ("type_text", "shortcut"):
                target, executable = foreground()
                authorize_target(kind, value, executable)
            if kind == "type_text":
                type_unicode(value, cancel, target)
            elif kind == "shortcut":
                pyautogui.hotkey(*SHORTCUTS[value])
            elif kind == "volume":
                pyautogui.press(VOLUMES[value])
