"""Layout regression tests: run with Tk/display, skip explicitly without them."""
import tempfile
import unittest
from types import SimpleNamespace

try:
    import tkinter as tk
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "Tkinter is not installed")
class DesktopLayoutTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No graphical display: {exc}")
        self.addCleanup(self.root.destroy)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def build(self, scale):
        from assistente_pc.desktop import Desktop
        self.root.tk.call("tk", "scaling", scale)
        args = SimpleNamespace(data_dir=self.directory.name, model="qwen2.5:7b",
                               history=False, voice_model="not-needed", device=None)
        app = Desktop(self.root, args)
        self.root.geometry("850x650+0+0")
        self.root.update()
        return app

    def assert_visible(self, widget):
        self.assertTrue(widget.winfo_ismapped())
        x = widget.winfo_rootx() - self.root.winfo_rootx()
        y = widget.winfo_rooty() - self.root.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), self.root.winfo_width())
        self.assertLessEqual(y + widget.winfo_height(), self.root.winfo_height())
        self.assertGreater(widget.winfo_height(), 10)

    def check_controls(self, app):
        for widget in [app.entry, app.stop_button, *app.controls]:
            self.assert_visible(widget)
        self.assertGreater(app.output.winfo_height(), 20)
        self.assertEqual(app.entry.winfo_manager(), "grid")
        self.assertEqual(app.mode.get(), "assistente")

    def test_composer_at_minimum_window_size(self):
        self.check_controls(self.build(1.333))

    def test_composer_at_windows_125_percent_scale(self):
        app = self.build(1.667)
        app.status.set("Consultando IA local… Parar descarta o resultado; a requisição pode levar até 180s.")
        self.root.update()
        self.check_controls(app)

    def test_composer_at_windows_150_percent_scale(self):
        self.check_controls(self.build(2.0))
