"""Interface nativa; I/O lento em worker e toda interação Tk no thread principal."""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .executor import ExecutionCancelled, execute_plan
from .session import Session
from .storage import Store


class Desktop:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.store = Store(args.data_dir)
        self.session = Session(self.store, args.model)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.pending = None
        self.last_message = ""
        self.mic = None
        self.controls = []
        root.title("Assistente PC · Local e sob seu controle")
        root.geometry("1100x790")
        root.minsize(850, 650)
        root.configure(bg="#101827")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#101827")
        style.configure("TLabel", background="#101827", foreground="#e3edf7", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        style.configure("Hint.TLabel", foreground="#91a9c1", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 9))
        style.configure("TCheckbutton", background="#101827", foreground="#e3edf7")
        style.configure("TCombobox", padding=6)
        outer = ttk.Frame(root, padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Seu assistente. Seu controle.", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="VOZ LOCAL  /  MEMÓRIA EXPLÍCITA  /  AÇÕES COM CONFIRMAÇÃO", style="Hint.TLabel").pack(anchor="w", pady=(5, 18))
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x")
        self.model = tk.StringVar(value=args.model)
        ttk.Label(toolbar, text="Modelo Ollama").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.model, width=22).pack(side="left", padx=8)
        self.mode = tk.StringVar(value="assistente")
        ttk.Combobox(toolbar, textvariable=self.mode, values=("assistente", "conversa", "documentos"), state="readonly", width=14).pack(side="left", padx=5)
        self.record_history = tk.BooleanVar(value=args.history)
        ttk.Checkbutton(toolbar, text="Salvar histórico de ações", variable=self.record_history).pack(side="right")
        tools = ttk.Frame(outer)
        tools.pack(fill="x", pady=12)
        for label, callback in [("Memórias", self.memories), ("Rotinas", self.routines),
                                ("Documentos", self.documents), ("Histórico", self.history),
                                ("Nova conversa", self.reset), ("Privacidade", self.privacy)]:
            self.button(tools, label, callback).pack(side="left", padx=(0, 6))
        self.output = ScrolledText(outer, wrap="word", bg="#172337", fg="#e3edf7", insertbackground="white",
                                   font=("Segoe UI", 11), relief="flat", padx=16, pady=16, state="disabled")
        self.output.pack(fill="both", expand=True)
        self.write("ASSISTENTE", "Olá! Posso conversar, preparar ações e consultar documentos que você importar.\n"
                   "Ensine preferências em Memórias e salve planos em Rotinas. Nada é monitorado em segundo plano.\n"
                   "Exemplos: ‘abra a calculadora’ ou ‘executar rotina começar trabalho’.\n"
                   "Ações só acontecem após clicar em Executar plano e confirmar.")
        self.status = tk.StringVar(value="Pronto · microfone desligado")
        ttk.Label(outer, textvariable=self.status, style="Hint.TLabel").pack(anchor="w", pady=(10, 6))
        self.entry = tk.Text(outer, height=3, wrap="word", bg="#223149", fg="white", insertbackground="white",
                             font=("Segoe UI", 11), relief="flat", padx=10, pady=8)
        self.entry.pack(fill="x")
        self.entry.bind("<Control-Return>", lambda event: self.send())
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(12, 0))
        for label, callback in [("Enviar · Ctrl+Enter", self.send), ("🎙 Falar", self.listen),
                                ("Executar plano", self.execute), ("Salvar rotina", self.save_routine),
                                ("Ouvir resposta", self.speak)]:
            self.button(actions, label, callback).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Parar", command=self.stop).pack(side="right")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(80, self.poll)

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=lambda: self.guarded(command))
        self.controls.append(button)
        return button

    def guarded(self, callback):
        try:
            callback()
        except Exception as exc:
            messagebox.showerror("Não foi possível concluir", str(exc), parent=self.root)

    def write(self, who, text):
        self.output.configure(state="normal")
        self.output.insert("end", f"{who}\n{text}\n\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def run(self, label, work):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.status.set(label)
        for control in self.controls:
            control.configure(state="disabled")

        def worker():
            try:
                work()
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "done":
                    self.busy = False
                    for control in self.controls:
                        control.configure(state="normal")
                    self.status.set("Pronto · microfone desligado")
                elif kind == "error":
                    self.write("AVISO", value + "\nAções já realizadas não são desfeitas.")
                elif kind == "message":
                    self.write("ASSISTENTE", value)
                elif kind == "transcript":
                    if not self.cancel.is_set():
                        self.entry.delete("1.0", "end")
                        self.entry.insert("1.0", value)
                        self.write("MICROFONE", "Confira a transcrição no campo abaixo e clique em Enviar.")
                elif kind == "plan":
                    if not self.cancel.is_set():
                        self.pending = value
                        request, plan = value
                        self.last_message = plan["message"]
                        lines = [f"{i}. {a['type']} → {a['value']}" for i, a in enumerate(plan["actions"], 1)]
                        self.write("ASSISTENTE", plan["message"] + ("\n\nPLANO PENDENTE\n" + "\n".join(lines) if lines else ""))
                elif kind == "confirm":
                    prompt, event, answer = value
                    try:
                        answer.append(not self.cancel.is_set() and messagebox.askokcancel("Selecionar janela", prompt, parent=self.root))
                    finally:
                        event.set()
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def send(self):
        if self.busy:
            return
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.pending = None
        self.session.model = self.model.get().strip()
        mode = self.mode.get()
        self.write("VOCÊ", text)
        self.entry.delete("1.0", "end")
        self.run("Consultando IA local… Parar descarta o resultado; a requisição pode levar até 180s.",
                 lambda: self.events.put(("plan", (text, self.session.prepare(text, mode)))))

    def listen(self):
        def work():
            from .audio import Microphone
            if self.mic is None:
                self.mic = Microphone(self.args.voice_model, self.args.device)
            text = self.mic.listen(cancel=self.cancel)
            self.events.put(("transcript", text))
        self.run("Microfone ativo · fale e faça uma pausa (até 15s)", work)

    def confirm_focus(self, text):
        event, answer = threading.Event(), []
        self.events.put(("confirm", (text, event, answer)))
        while not event.wait(0.1):
            if self.cancel.is_set():
                return False
        return bool(answer and answer[0])

    def execute(self):
        if not self.pending or not self.pending[1]["actions"]:
            messagebox.showinfo("Sem ações", "Prepare um pedido ou carregue uma rotina primeiro.", parent=self.root)
            return
        request, plan = self.pending
        summary = "\n".join(f"{a['type']}: {a['value']}" for a in plan["actions"])
        if not messagebox.askyesno("Autorizar ações no PC", summary + "\n\nExecutar exatamente este plano?", parent=self.root):
            return
        self.pending = None  # Uma autorização não pode ser reutilizada por duplo clique.
        record = self.record_history.get()

        def work():
            status = "failed"
            try:
                execute_plan(plan, self.cancel, self.confirm_focus, lambda text: self.events.put(("message", text)))
                status = "completed"
                self.events.put(("message", "Plano concluído."))
            except ExecutionCancelled:
                status = "cancelled"
                raise
            finally:
                if record:
                    self.store.log(request, plan, status)
        self.run("Executando · Parar interrompe nos pontos de verificação", work)

    def save_routine(self):
        if not self.pending or not self.pending[1]["actions"]:
            raise ValueError("Prepare um plano com ações primeiro. Salve antes de executá-lo.")
        name = simpledialog.askstring("Ensinar rotina", "Nome da rotina (ex.: começar trabalho):", parent=self.root)
        if name:
            key = self.store.clean_name(name)
            if key in self.store.routines() and not messagebox.askyesno("Substituir rotina", f"Substituir {key}?", parent=self.root):
                return
            self.store.save_routine(name, self.pending[1])
            self.write("MEMÓRIA", f"Rotina salva: {name}. Para carregar, diga ‘executar rotina {name}’. Ainda exigirá confirmação.")

    def manager(self, title):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("720x460")
        window.transient(self.root)
        window.grab_set()
        listing = tk.Listbox(window, font=("Segoe UI", 11), selectmode="browse")
        listing.pack(fill="both", expand=True, padx=12, pady=12)
        buttons = ttk.Frame(window, padding=12)
        buttons.pack(fill="x")
        return window, listing, buttons

    def memories(self):
        window, listing, buttons = self.manager("Memórias explícitas · armazenadas somente neste PC")
        keys = []

        def refresh():
            listing.delete(0, "end")
            keys[:] = self.store.memories()
            for key, value in self.store.memories().items():
                listing.insert("end", f"{key}: {value}")

        def add():
            name = simpledialog.askstring("Preferência", "Nome (ex.: profissão ou navegador preferido):", parent=window)
            if not name:
                return
            value = simpledialog.askstring("Preferência", "Valor — não guarde senhas ou segredos aqui:", parent=window)
            if value and messagebox.askyesno("Salvar memória", f"Salvar/substituir {name}: {value}?", parent=window):
                self.store.remember(name, value)
                refresh()

        def remove():
            if listing.curselection():
                key = keys[listing.curselection()[0]]
                if messagebox.askyesno("Esquecer", f"Apagar {key}?", parent=window):
                    self.store.delete("memories", key)
                    refresh()
        ttk.Button(buttons, text="Adicionar / atualizar", command=lambda: self.guarded(add)).pack(side="left")
        ttk.Button(buttons, text="Esquecer selecionada", command=lambda: self.guarded(remove)).pack(side="left", padx=8)
        refresh()

    def routines(self):
        window, listing, buttons = self.manager("Rotinas ensinadas")
        keys = self.store.routines()
        for name in keys:
            listing.insert("end", name)

        def load():
            if listing.curselection():
                name = keys[listing.curselection()[0]]
                plan = self.store.routine(name)
                self.pending = ("executar rotina " + name, plan)
                self.write("ROTINA PENDENTE", name + "\n" + "\n".join(f"{a['type']}: {a['value']}" for a in plan["actions"]))
                window.destroy()

        def remove():
            if listing.curselection():
                index = listing.curselection()[0]
                if messagebox.askyesno("Apagar rotina", f"Apagar {keys[index]}?", parent=window):
                    self.store.delete("routines", keys.pop(index))
                    listing.delete(index)
        ttk.Button(buttons, text="Carregar para revisão", command=lambda: self.guarded(load)).pack(side="left")
        ttk.Button(buttons, text="Excluir", command=lambda: self.guarded(remove)).pack(side="left", padx=8)

    def documents(self):
        window, listing, buttons = self.manager("Documentos autorizados · cópias locais do texto")
        docs = self.session.knowledge.documents()
        for doc in docs:
            listing.insert("end", f"{doc['name']} — {doc['path']}")

        def add():
            filename = filedialog.askopenfilename(parent=window, filetypes=[("Documentos", "*.txt *.md *.pdf")])
            if filename and messagebox.askyesno("Autorizar importação", "Copiar o texto deste arquivo para a base local? "
                                                "Não há monitoramento da pasta. Para atualizar, importe novamente.", parent=window):
                window.destroy()
                def work():
                    count = self.session.knowledge.import_file(filename)
                    self.events.put(("message", f"Documento importado: {count} trechos. Use o modo documentos para perguntar."))
                self.run("Importando documento…", work)

        def remove():
            if listing.curselection():
                index = listing.curselection()[0]
                if messagebox.askyesno("Remover da base", "Remover a cópia indexada? O arquivo original será mantido.", parent=window):
                    self.session.knowledge.remove(docs.pop(index)["id"])
                    listing.delete(index)
        ttk.Button(buttons, text="Importar arquivo", command=lambda: self.guarded(add)).pack(side="left")
        ttk.Button(buttons, text="Remover selecionado", command=lambda: self.guarded(remove)).pack(side="left", padx=8)

    def history(self):
        self.write("HISTÓRICO LOCAL", "\n".join(f"{r['created']} · {r['status']} · {r['request']}" for r in self.store.history()) or "Vazio. O registro é opcional e vem desligado.")
        suggestions = self.store.suggestions()
        for suggestion in suggestions:
            self.write("SUGESTÃO DE ROTINA", f"Este plano foi concluído {suggestion['uses']} vezes:\n" +
                       "\n".join(f"{a['type']}: {a['value']}" for a in suggestion["plan"]["actions"]) +
                       "\nSe quiser, prepare esse pedido e salve como rotina. Nada foi salvo automaticamente.")

    def reset(self):
        self.session.reset()
        self.pending = None
        self.last_message = ""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.write("ASSISTENTE", "Contexto da conversa limpo. Memórias explícitas continuam disponíveis.")

    def privacy(self):
        window = tk.Toplevel(self.root)
        window.title("Privacidade e dados locais")
        window.transient(self.root)
        window.grab_set()
        text = (f"Banco local: {self.store.path}\n\nSem criptografia própria. Não salve senhas.\n"
                "Memórias e documentos só são salvos quando você pede.\nHistórico de ações é opcional, limitado aos últimos 200 registros.\n"
                "Conversa recente fica apenas em memória; Nova conversa a limpa.\n"
                "Ollama recebe dados localmente; seus próprios logs têm configuração independente.\n"
                "Excluir a base não elimina backups nem garante apagamento forense do disco.")
        ttk.Label(window, text=text, padding=20, wraplength=600).pack()

        def clear(all_data):
            if messagebox.askyesno("Confirmar exclusão", "Apagar todos os dados locais?" if all_data else "Apagar o histórico de ações?", parent=window):
                if all_data:
                    self.store.clear_all()
                    self.reset()
                else:
                    self.store.clear_history()
                window.destroy()
        ttk.Button(window, text="Apagar histórico", command=lambda: self.guarded(lambda: clear(False))).pack(pady=5)
        ttk.Button(window, text="Apagar memórias, rotinas, histórico e documentos", command=lambda: self.guarded(lambda: clear(True))).pack(pady=12)

    def speak(self):
        if not self.last_message:
            return
        from .speech import speak
        text = self.last_message
        self.run("Lendo resposta com voz local · Parar não interrompe esta leitura", lambda: speak(text))

    def stop(self):
        self.cancel.set()
        self.pending = None
        self.status.set("Parada solicitada · aguardando a operação atual liberar; ações concluídas não são desfeitas")

    def close(self):
        if self.busy and not messagebox.askyesno("Encerrar", "Há uma operação em andamento. Interromper e fechar?", parent=self.root):
            return
        self.cancel.set()
        self.root.destroy()


def launch(args):
    root = tk.Tk()
    Desktop(root, args)
    root.mainloop()
