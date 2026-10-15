import argparse
import importlib.util
import json
import platform
from pathlib import Path

LABELS = {"open_app": "Abrir programa", "open_site": "Abrir site", "search_web": "Pesquisar",
          "type_text": "Digitar na janela em foco", "shortcut": "Atalho", "volume": "Volume"}


def is_confirmed(text):
    return text.strip().casefold() == "executar"


def parser():
    p = argparse.ArgumentParser(description="Assistente local: voz, memória, rotinas e documentos")
    p.add_argument("--model", default="qwen2.5:3b", help="Modelo instalado no Ollama")
    p.add_argument("--voice-model", default="models/vosk-model-small-pt-0.3")
    p.add_argument("--device", type=int, help="Índice do microfone")
    p.add_argument("--data-dir", help="Pasta da base local (padrão: LOCALAPPDATA/AssistentePC)")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--check", action="store_true", help="Verifica requisitos locais")
    p.add_argument("--gui", action="store_true", help="Abre a interface de desktop")
    p.add_argument("--keyboard", action="store_true", help="Conversa pelo teclado, sem microfone")
    p.add_argument("--text", help="Pedido único escrito")
    p.add_argument("--mode", choices=("assistente", "conversa", "documentos"), default="assistente")
    p.add_argument("--dry-run", action="store_true", help="Mostra o plano, sem executar ações")
    p.add_argument("--voice-confirm", action="store_true")
    p.add_argument("--speak", action="store_true", help="Lê a resposta com voz local do Windows")
    p.add_argument("--history", action="store_true", help="Autoriza salvar histórico de ações nesta execução")
    p.add_argument("--remember", nargs=2, metavar=("NOME", "VALOR"), help="Salva/substitui uma memória explícita")
    p.add_argument("--forget", metavar="NOME")
    p.add_argument("--list-memories", action="store_true")
    p.add_argument("--routine", metavar="NOME", help="Carrega uma rotina para revisão e confirmação")
    p.add_argument("--save-routine", metavar="NOME", help="Salva o plano revisado após confirmação")
    p.add_argument("--list-routines", action="store_true")
    p.add_argument("--delete-routine", metavar="NOME")
    p.add_argument("--import-file", metavar="ARQUIVO", help="Autoriza copiar o texto do documento à base")
    p.add_argument("--list-documents", action="store_true")
    p.add_argument("--remove-document", type=int, metavar="ID")
    p.add_argument("--show-history", action="store_true")
    p.add_argument("--suggestions", action="store_true")
    p.add_argument("--clear-history", action="store_true")
    p.add_argument("--clear-data", action="store_true", help="Apaga dados do assistente após confirmação")
    return p


def manage(args, store):
    from .knowledge import Knowledge
    operations = [args.remember, args.forget, args.list_memories, args.list_routines,
                  args.delete_routine, args.import_file, args.list_documents,
                  args.remove_document is not None, args.show_history, args.suggestions,
                  args.clear_history, args.clear_data]
    if not any(operations):
        return False
    if sum(bool(op) for op in operations) != 1:
        raise ValueError("Use um comando de gerenciamento por vez.")
    if args.dry_run:
        raise ValueError("--dry-run serve para pedidos e rotinas, não para gerenciar dados.")
    knowledge = Knowledge(store)
    if args.remember:
        store.remember(*args.remember)
        print("Memória salva explicitamente.")
    elif args.forget:
        store.delete("memories", args.forget)
        print("Memória removida. Reinicie conversas abertas para limpar o contexto temporário.")
    elif args.list_memories:
        print(json.dumps(store.memories(), ensure_ascii=False, indent=2))
    elif args.list_routines:
        print(json.dumps(store.routines(), ensure_ascii=False, indent=2))
    elif args.delete_routine:
        store.delete("routines", args.delete_routine)
        print("Rotina removida.")
    elif args.import_file:
        print(f"Documento importado: {knowledge.import_file(args.import_file)} trechos.")
    elif args.list_documents:
        print(json.dumps(knowledge.documents(), ensure_ascii=False, indent=2))
    elif args.remove_document is not None:
        knowledge.remove(args.remove_document)
        print("Documento removido da base. O original não foi alterado.")
    elif args.show_history:
        print(json.dumps(store.history(), ensure_ascii=False, indent=2))
    elif args.suggestions:
        print(json.dumps(store.suggestions(), ensure_ascii=False, indent=2))
    elif args.clear_history or args.clear_data:
        if input("Digite APAGAR para excluir os dados solicitados: ").strip() == "APAGAR":
            (store.clear_all if args.clear_data else store.clear_history)()
            print("Dados removidos. Reinicie outras instâncias abertas para limpar seus contextos temporários.")
        else:
            print("Exclusão cancelada.")
    return True


def main():
    args = parser().parse_args()
    if args.check:
        from .storage import data_directory
        print(f"Sistema: {platform.system()} (ações e fala sintetizada requerem Windows)")
        for module in ("vosk", "sounddevice", "pyautogui", "pypdf", "pyttsx3", "tkinter"):
            print(f"{module}: {'instalado' if importlib.util.find_spec(module) else 'ausente'}")
        print(f"Pasta do modelo de voz: {'encontrada' if Path(args.voice_model).is_dir() else 'ausente'}")
        print(f"Dados locais: {args.data_dir or data_directory()}")
        print("Ollama: teste com 'ollama list'; conexão verificada no primeiro pedido.")
        return
    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        return
    if args.gui:
        if args.dry_run:
            raise ValueError("--dry-run não se aplica à interface. Planos da interface sempre exigem confirmação.")
        from .desktop import launch
        launch(args)
        return
    from .storage import Store
    from .session import Session
    store = Store(args.data_dir)
    if manage(args, store):
        return
    if args.dry_run and args.save_routine:
        raise ValueError("Remova --dry-run para autorizar salvar uma rotina.")
    session = Session(store, args.model)
    mic = None
    if (not args.text and not args.routine and not args.keyboard) or (args.voice_confirm and not args.dry_run):
        from .audio import Microphone
        mic = Microphone(args.voice_model, args.device)
    print("Assistente local. Ctrl+C encerra. Mova o mouse a um canto da tela principal para interromper ações.")
    print("Não use ações em terminais, consoles ou janelas com privilégios elevados.")
    print("Histórico de ações: " + ("ATIVADO" if args.history else "desativado"))
    while True:
        if args.routine:
            text = "executar rotina " + args.routine
        elif args.text:
            text = args.text
        elif args.keyboard:
            text = input("\nVocê (sair / nova conversa): ").strip()
        else:
            command = input("\nEnter para falar; ou escreva um pedido (sair para encerrar): ").strip()
            text = command or mic.listen()
        if not text:
            print("Não entendi nenhuma fala. Tente novamente.")
            continue
        if text.strip().casefold() in ("sair", "encerrar assistente"):
            return
        if text.strip().casefold() == "nova conversa":
            session.reset()
            print("Contexto temporário limpo.")
            if args.text:
                return
            continue
        print(f"Pedido: {text}")
        plan = None
        status = "proposed"
        try:
            from .conversation import review_plan
            plan = review_plan(store.routine(args.routine)) if args.routine else session.prepare(text, args.mode)
            print(plan["message"])
            for index, action in enumerate(plan["actions"], 1):
                print(f"  {index}. {LABELS[action['type']]}: {action['value']}")
            if args.speak:
                try:
                    from .speech import speak
                    speak(plan["message"])
                except Exception as exc:
                    print(f"Resposta falada indisponível: {exc}")
            if args.save_routine and plan["actions"]:
                if input(f"Salvar/substituir rotina '{args.save_routine}'? Digite salvar: ").strip().casefold() == "salvar":
                    store.save_routine(args.save_routine, plan)
                    print("Rotina salva. Isso não autoriza executar.")
            if args.dry_run:
                print(json.dumps(plan, ensure_ascii=False, indent=2))
            elif plan["actions"]:
                print("Revise todas as ações. Só prossiga se estiverem corretas.")
                if args.voice_confirm:
                    print("Diga apenas executar para confirmar. Qualquer outra fala cancela.")
                    answer = mic.listen(seconds=8)
                    print(f"Confirmação reconhecida: {answer!r}")
                else:
                    answer = input("Digite executar para confirmar; qualquer outra resposta cancela: ")
                if is_confirmed(answer):
                    from .executor import execute_plan
                    status = "failed"
                    execute_plan(plan)
                    status = "completed"
                    print("Plano concluído.")
                else:
                    status = "cancelled"
                    print("Plano cancelado. Nenhuma ação executada.")
        except Exception as exc:
            print(f"Operação interrompida: {exc}")
            print("Nenhuma ação adicional será tentada. Ações já realizadas não são desfeitas.")
            if args.text or args.routine:
                raise SystemExit(1) from exc
        finally:
            if plan and plan["actions"] and status in ("completed", "failed", "cancelled"):
                session.record_result(plan, status)
            if args.history and plan and plan["actions"] and not args.dry_run:
                store.log(text, plan, status)
        if args.text or args.routine:
            return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nAssistente encerrado.")
    except Exception as exc:
        raise SystemExit(f"Erro: {exc}") from exc
