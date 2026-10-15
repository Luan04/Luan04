"""Política independente do modelo para conversa e confirmação por voz."""
import re
import unicodedata

from .planner import validate_plan

HISTORY_MESSAGES = 24
HISTORY_CHARACTERS = 24000
PERSONALITY = """Converse em português brasileiro de forma natural, direta e acolhedora.
Você é um assistente de software, não uma pessoa. Não simule consciência, emoções ou vigilância.
Responda ao que a pessoa realmente disse, aproveitando o contexto e suas preferências.
Em geral use de duas a quatro frases; aprofunde quando pedirem. Evite listas e jargão sem necessidade.
Se faltar um detalhe necessário, faça uma pergunta curta em vez de inventar ou recusar tudo.
Nem toda fala é um comando. Saudações, comentários, ideias e perguntas merecem conversa, sem ações.
Não prometa funções que não possui. Nunca diga que fez uma ação sem um resultado do executor.
Planos são propostas; escrever um plano NÃO executa nada. Não repita ações antigas sem novo pedido.
"""


def normalized(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))
    return ' '.join(text.strip(' .!?').split())


def review_plan(plan):
    validate_plan(plan)
    if not plan['actions']:
        return plan
    # Uma mensagem gerada não pode afirmar sucesso antes da execução.
    return {"message": "Preparei o pedido. Ainda não executei; falta sua autorização.",
            "actions": [dict(a) for a in plan['actions']]}


def quick_plan(text):
    """Somente pedidos completos e inequívocos. Negativas e perguntas usam a IA."""
    value = normalized(text)
    value = re.sub(r'^por favor[, ]+|[, ]+por favor$', '', value)
    apps = {"calculadora": "calculadora", "bloco de notas": "bloco_de_notas",
            "explorador": "explorador", "explorador de arquivos": "explorador",
            "chrome": "chrome", "edge": "edge", "firefox": "firefox"}
    match = re.fullmatch(r'(?:abra|abrir|abre) (?:o |a )?(.+)', value)
    if match and match[1] in apps:
        return review_plan({"message": "", "actions": [{"type": "open_app", "value": apps[match[1]]}]})
    volumes = {"aumente o volume": "aumentar", "aumentar o volume": "aumentar",
               "diminua o volume": "diminuir", "diminuir o volume": "diminuir",
               "silencie o som": "silenciar"}
    if value in volumes:
        return review_plan({"message": "", "actions": [{"type": "volume", "value": volumes[value]}]})
    return None


def describe(plan):
    validate_plan(plan)
    labels = {"open_app": "abrir", "open_site": "abrir o site", "search_web": "pesquisar na internet",
              "type_text": "digitar", "shortcut": "usar o atalho", "volume": "ajustar o volume para"}
    return '; '.join(f"{labels[a['type']]} {a['value'].replace('_', ' ')}" for a in plan['actions'])


def action_policy(plan, allow_simple=False):
    validate_plan(plan)
    actions = plan['actions']
    if not actions:
        return 'reply'
    # Nunca separe um plano misto para autorizar só parte dele.
    if any(a['type'] in ('type_text', 'shortcut') for a in actions) or len(describe(plan)) > 900:
        return 'manual'
    if allow_simple and all(a['type'] in ('open_app', 'volume') for a in actions):
        return 'automatic'
    return 'confirm'


def voice_confirmed(text):
    return normalized(text) == 'confirmar execucao'


def voice_stop(text):
    return normalized(text) in ('parar assistente', 'encerrar conversa', 'parar conversa')
