"""Conversa half-duplex: ouvir → pensar → falar → ouvir, sempre opt-in."""
from .conversation import action_policy, describe, review_plan, voice_confirmed, voice_stop
from .executor import ExecutionCancelled, execute_plan


class LiveConversation:
    def __init__(self, session, microphone, speaker, cancel, emit,
                 allow_simple=False, history=False, mode='assistente', executor=execute_plan):
        self.session, self.mic, self.speaker = session, microphone, speaker
        self.cancel, self.emit, self.executor = cancel, emit, executor
        self.allow_simple, self.history, self.mode = allow_simple, history, mode

    def say(self, text):
        if self.cancel.is_set():
            return
        self.emit('status', 'Falando · microfone desligado · botão Parar interrompe')
        self.speaker(text, cancel=self.cancel)
        # Evita abrir o microfone sobre o fim da própria reprodução.
        self.cancel.wait(0.4)

    def hear(self, confirmation=False):
        if self.cancel.is_set():
            return ''
        self.emit('status', 'Ouvindo confirmação por até 8s…' if confirmation else
                  'Ouvindo · fale naturalmente; diga “parar assistente” para encerrar')
        return self.mic.listen(seconds=8 if confirmation else 15, cancel=self.cancel)

    def run(self):
        # Falha da voz de saída encerra antes de ouvir ou executar qualquer pedido.
        self.say('Estou ouvindo. Pode conversar comigo. Para encerrar, diga parar assistente.')
        silent = 0
        while not self.cancel.is_set():
            text = self.hear()
            if self.cancel.is_set():
                return
            if not text:
                silent += 1
                if silent >= 8:
                    self.emit('message', 'Conversa pausada após cerca de dois minutos sem fala reconhecida.')
                    return
                continue
            silent = 0
            self.emit('heard', text)
            if voice_stop(text):
                self.say('Tudo bem. Desliguei a conversa por voz.')
                return
            self.emit('status', 'Pensando · microfone desligado · Parar descarta a resposta')
            plan = self.session.prepare(text, self.mode)
            if self.cancel.is_set():
                return
            policy = action_policy(plan, self.allow_simple) if plan['actions'] else 'reply'
            if policy == 'reply':
                self.emit('reply', plan['message'])
                reply = plan['message']
                self.say(reply if len(reply) <= 1500 else reply[:1400] + ' O restante está na tela.')
                continue
            plan = review_plan(plan)
            if policy == 'manual':
                self.emit('plan', (text, plan))
                self.say('Esse pedido envolve digitação, atalhos ou um plano longo. '
                         'Deixei o plano na tela para você revisar. Vou pausar a conversa.')
                return
            summary = describe(plan)
            self.emit('message', 'Pedido reconhecido. Plano ainda não executado: ' + summary)
            if policy == 'confirm':
                self.say('Posso ' + summary + '? Diga confirmar execução para autorizar. Outra resposta cancela.')
                answer = self.hear(confirmation=True)
                if self.cancel.is_set():
                    return
                self.emit('heard', answer or '(sem confirmação)')
                if voice_stop(answer):
                    self.say('Pedido cancelado. Conversa encerrada.')
                    return
                if not voice_confirmed(answer):
                    self.session.record_result(plan, 'cancelled')
                    if self.history:
                        self.session.store.log(text, plan, 'cancelled')
                    self.emit('message', 'Pedido cancelado. Nenhuma ação deste plano foi executada.')
                    self.say('Cancelei o pedido. Pode continuar falando.')
                    continue
            else:
                self.say('Vou ' + summary + '.')
            if self.cancel.is_set():
                return
            self.emit('status', 'Executando · microfone desligado')
            status = 'failed'
            try:
                self.executor(plan, cancel=self.cancel,
                              on_progress=lambda value: self.emit('message', value))
                status = 'completed'
            except ExecutionCancelled:
                status = 'cancelled'
                raise
            finally:
                self.session.record_result(plan, status)
                if self.history:
                    self.session.store.log(text, plan, status)
            self.emit('reply', 'Execução concluída sem erro. Não verifico visualmente o resultado.')
            self.say('Executei o pedido. Pode continuar falando.')
