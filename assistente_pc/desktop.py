"""Interface nativa; I/O lento em worker e toda interação Tk no thread principal."""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .conversation import review_plan
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
        self.live_active = False
        root.title("Assistente PC · Local e sob seu controle")
        width = min(1100, max(850, root.winfo_screenwidth() - 80))
        height = min(790, max(650, root.winfo_screenheight() - 120))
        root.geometry(f"{width}x{height}")
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
        style.configure("Voice.TButton", background="#85dfc5", foreground="#102a25")
        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)
        # Only the transcript grows/shrinks. Reserve space for the composer first;
        # pack previously let the transcript consume the bottom controls on Windows.
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)
        ttk.Label(outer, text="Seu assistente. Seu controle.", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="VOZ LOCAL  /  MEMÓRIA EXPLÍCITA  /  AÇÕES COM CONFIRMAÇÃO", style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 12))
        toolbar = ttk.Frame(outer)
        toolbar.grid(row=2, column=0, sticky="ew")
        self.model = tk.StringVar(value=args.model)
        ttk.Label(toolbar, text="Modelo Ollama").grid(row=0, column=0, sticky="w")
        model_entry = ttk.Entry(toolbar, textvariable=self.model, width=22)
        model_entry.grid(row=0, column=1, padx=8, sticky="w")
        self.mode = tk.StringVar(value="assistente")
        mode_entry = ttk.Combobox(toolbar, textvariable=self.mode, values=("assistente", "conversa", "documentos"), state="readonly", width=14)
        mode_entry.grid(row=0, column=2, padx=5, sticky="w")
        self.options = [(model_entry, "normal"), (mode_entry, "readonly")]
        self.record_history = tk.BooleanVar(value=args.history)
        history_check = ttk.Checkbutton(toolbar, text="Salvar histórico de ações", variable=self.record_history)
        history_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.allow_simple = tk.BooleanVar(value=False)
        simple_check = ttk.Checkbutton(toolbar, text="Voz: apps e volume sem confirmar", variable=self.allow_simple)
        simple_check.grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.options.extend([(history_check, "normal"), (simple_check, "normal")])
        tools = ttk.Frame(outer)
        tools.grid(row=3, column=0, sticky="ew", pady=10)
        for label, callback in [("Memórias", self.memories), ("Rotinas", self.routines),
                                ("Documentos", self.documents), ("Histórico", self.history),
                                ("Nova conversa", self.reset), ("Privacidade", self.privacy)]:
            self.button(tools, label, callback).pack(side="left", padx=(0, 6))
        self.output = ScrolledText(outer, wrap="word", bg="#172337", fg="#e3edf7", insertbackground="white",
                                   font=("Segoe UI", 11), width=1, height=4, relief="flat", padx=12, pady=10, state="disabled")
        self.output.grid(row=4, column=0, sticky="nsew")
        self.write("ASSISTENTE", "Olá! Posso conversar, preparar ações e consultar documentos que você importar.\n"
                   "Ensine preferências em Memórias e salve planos em Rotinas. Nada é monitorado em segundo plano.\n"
                   "Exemplos: ‘abra a calculadora’ ou ‘executar rotina começar trabalho’.\n"
                   "Clique em Conversar por voz para falar e ouvir sem clicar a cada frase. "
                   "Ações exigem autorização; a opção de apps e volume diretos é voluntária.")
        self.status = tk.StringVar(value="Pronto · microfone desligado")
        status_label = ttk.Label(outer, textvariable=self.status, style="Hint.TLabel", wraplength=750)
        status_label.grid(row=5, column=0, sticky="ew", pady=(8, 6))
        outer.bind("<Configure>", lambda event: status_label.configure(wraplength=max(200, event.width - 40)))
        self.entry = tk.Text(outer, width=1, height=3, wrap="word", bg="#223149", fg="white", insertbackground="white",
                             font=("Segoe UI", 11), relief="flat", padx=10, pady=8)
        self.entry.grid(row=6, column=0, sticky="ew")
        self.entry.bind("<Control-Return>", lambda event: self.send())
        actions = ttk.Frame(outer)
        actions.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        for column in range(4):
            actions.columnconfigure(column, weight=1, uniform="actions")
        for index, (label, callback) in enumerate([
                ("Enviar · Ctrl+Enter", self.send), ("Conversar por voz", self.start_live),
                ("Falar uma vez", self.listen), ("Executar plano", self.execute), ("Salvar rotina", self.save_routine),
                ("Ouvir resposta", self.speak)]):
            button = self.button(actions, label, callback)
            if label == "Conversar por voz":
                button.configure(style="Voice.TButton")
            button.grid(row=index // 4, column=index % 4, sticky="ew", padx=3, pady=3)
        self.stop_button = ttk.Button(actions, text="Parar", command=self.stop)
        self.stop_button.grid(row=1, column=3, sticky="ew", padx=3, pady=3)
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
        for control, _ in self.options:
            control.configure(state="disabled")
        self.entry.configure(state="disabled")

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
                    self.live_active = False
                    self.entry.configure(state="normal")
                    for control, state in self.options:
                        control.configure(state=state)
                    for control in self.controls:
                        control.configure(state="normal")
                    self.status.set("Pronto · microfone desligado")
                elif kind == "error":
                    self.write("AVISO", value + "\nAções já realizadas não são desfeitas.")
                elif kind == "status":
                    if not self.cancel.is_set():
                        self.status.set(value)
                elif kind == "heard":
                    self.write("VOCÊ · VOZ", value)
                elif kind == "reply":
                    if not self.cancel.is_set():
                        self.last_message = value
                        self.write("ASSISTENTE", value)
                elif kind == "message":
                    self.write("ASSISTENTE", value)
                elif kind == "transcript":
                    if not self.cancel.is_set():
                        self.entry.configure(state="normal")
                        self.entry.delete("1.0", "end")
                        self.entry.insert("1.0", value)
                        self.write("MICROFONE", "Confira a transcrição no campo abaixo e clique em Enviar.")
                elif kind == "plan":
                    if not self.cancel.is_set():
                        self.pending = value
                        request, plan = value
                        if plan["actions"]:
                            plan = review_plan(plan)
                        self.pending = (request, plan)
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

    def start_live(self):
        if self.busy:
            return
        permission = ("O microfone será reaberto após cada resposta até você parar. "
                      "Nada é gravado em arquivo. Use fones e um ambiente sem outras vozes.\n\n"
                      "Enquanto penso, falo ou executo, não estou ouvindo. Para interromper a qualquer momento, "
                      "use o botão Parar. Durante a escuta, diga ‘parar assistente’.\n\n")
        if self.allow_simple.get():
            permission += ("Você marcou execução direta: abrir programas e alterar volume não terão "
                           "uma segunda confirmação nesta sessão de voz. Reconhecimento incorreto pode "
                           "acionar essas tarefas. Outros pedidos continuam sujeitos a revisão.\n\n")
        permission += "Ativar conversa por voz?"
        if not messagebox.askyesno("Ativar microfone em turnos", permission, parent=self.root):
            return
        self.pending = None
        self.session.model = self.model.get().strip()
        allow_simple, history, mode = self.allow_simple.get(), self.record_history.get(), self.mode.get()
        self.live_active = True

        def work():
            from .audio import Microphone
            from .live import LiveConversation
            from .speech import speak
            if self.mic is None:
                self.mic = Microphone(self.args.voice_model, self.args.device)
            LiveConversation(self.session, self.mic, speak, self.cancel,
                             lambda kind, value: self.events.put((kind, value)),
                             allow_simple=allow_simple, history=history, mode=mode).run()
        self.run("Preparando conversa por voz…", work)

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
                self.session.record_result(plan, status)
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
        self.run("Lendo resposta com voz local · Parar interrompe", lambda: speak(text, cancel=self.cancel))

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
