# Assistente PC — voz, memória e rotinas locais 🇧🇷

Assistente pessoal para **Windows 10/11**, com interface de desktop, reconhecimento de fala em português, IA via **Ollama**, memória explícita e execução supervisionada de ações. Sem chave de API e sem assinatura. Projeto em desenvolvimento: teste em ambiente não sensível antes de usar no trabalho.

> Ele aprende preferências que você salva e reutiliza rotinas que você ensina. **Não se treina sozinho, não monitora seu computador e não tem autonomia irrestrita.** A qualidade das respostas depende do modelo, do microfone e do hardware.

## Capacidades

| Recurso | Comportamento |
|---|---|
| Voz em português | Vosk local; captura somente ao clicar em Falar ou pressionar Enter no terminal |
| Interface de desktop | Pedidos por texto/voz, revisão do plano, confirmação e botão Parar |
| Conversa | Contexto temporário das últimas 3 trocas, sem salvar a conversa em disco pelo aplicativo |
| Memórias | Até 50 preferências explícitas, consultáveis, editáveis e apagáveis |
| Rotinas | Salve um plano com nome e recupere com “executar rotina começar trabalho” |
| Sugestões | Com histórico habilitado, identifica planos concluídos pelo menos 3 vezes e sugere rotinas; não as cria automaticamente |
| Documentos | Importação explícita de TXT, Markdown e PDF com texto; respostas com caminhos, páginas e trechos recuperados |
| Resposta falada | Voz de português instalada no Windows, opcional, sem serviço de nuvem |
| Segurança | Lista de ações, validação antes da execução, confirmação e restrições à janela de destino |

### Ações disponíveis

- Abrir Calculadora, Bloco de Notas, Explorador, Edge, Chrome e Firefox instalados.
- Abrir Google, YouTube, GitHub e Wikipédia; pesquisar no Google com o navegador padrão.
- Digitar texto Unicode **somente em Bloco de Notas, Word ou WordPad**, quando instalados e selecionados.
- Atalhos predefinidos: copiar, colar, selecionar tudo, desfazer, salvar, alternar janela e mostrar área de trabalho. Os atalhos de edição exigem um dos editores acima, Chrome, Edge, Firefox ou Explorador.
- Aumentar/diminuir volume ou alternar silêncio.

## 1. Instalação no Windows

Recomendado: Python **3.11 de 64 bits**, com **Tcl/Tk** incluído no instalador, e um microfone. Instale o [Ollama para Windows](https://ollama.com/download/windows) e mantenha-o aberto. Como ponto de partida, 8 GB de RAM podem servir para um modelo pequeno; 16 GB ou mais dão mais margem. GPU é opcional e a velocidade varia bastante.

No PowerShell, dentro da pasta do projeto:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:7b
```

Não precisa ativar o ambiente virtual nem alterar a política de execução. Se `ollama` não for encontrado, reabra o terminal após instalar. Se o serviço não estiver ativo, rode `ollama serve` em outro terminal — não abra uma segunda instância se já estiver rodando.

### Modelo de reconhecimento de fala

Na [lista oficial Vosk](https://alphacephei.com/vosk/models), baixe **vosk-model-small-pt-0.3** e extraia para:

```text
models/
└── vosk-model-small-pt-0.3/
    ├── am/
    ├── conf/
    └── ...
```

Evite uma pasta duplicada dentro da outra. Outro modelo Vosk em português pode ser escolhido com `--voice-model CAMINHO`. Em **Configurações → Privacidade e segurança → Microfone**, permita acesso para aplicativos da área de trabalho. O modelo de voz não é necessário para usar só o teclado.

### Voz de resposta (opcional)

Instale uma voz de português nas configurações de idioma/fala do Windows. O botão **Ouvir resposta** usa SAPI5 via `pyttsx3`; se não houver voz de português compatível, mostrará uma orientação. A leitura fica limitada aos primeiros 3000 caracteres.

## 2. Abrir a interface

Dê dois cliques em **`iniciar.bat`**, ou rode:

```powershell
.\.venv\Scripts\python.exe -m assistente_pc --gui --model qwen2.5:7b
```

1. Escolha o modo: **assistente** (ações e respostas), **conversa** (somente respostas) ou **documentos** (somente consulta à base autorizada).
2. Digite um pedido ou clique em **Falar**. A transcrição aparece no campo para revisão; clique em **Enviar**.
3. Para ações, revise o plano. Nada é executado só por enviar o pedido.
4. Clique em **Executar plano** e confirme a lista de ações.
5. Para digitação/atalhos, confirme a pausa adicional e selecione a janela correta em até cinco segundos.

Comece com “abra a calculadora”. Para digitação: “abra o bloco de notas e digite olá, tudo bem”. **Salvar rotina** deve ser usado enquanto o plano está pendente, antes de executá-lo. Uma autorização de execução não pode ser reutilizada por duplo clique.

### Ensinar preferências e rotinas

- **Memórias → Adicionar / atualizar**: salve, por exemplo, `profissão = designer` ou `navegador preferido = firefox`. Isso fornece contexto ao modelo, mas não instala aplicativos nem amplia permissões. Não salve senhas ou segredos.
- Prepare “abra o bloco de notas e a calculadora”. Clique em **Salvar rotina** e dê o nome `começar trabalho`.
- Depois, peça **“executar rotina começar trabalho”**, ou carregue pela lista de Rotinas. O plano salvo será apresentado novamente e ainda exigirá confirmação.
- Marque **Salvar histórico de ações** se quiser registrar resultados. Em **Histórico**, veja sugestões baseadas em repetições de planos concluídos. Não há observação de hábitos fora do assistente.

### Consultar seu trabalho

Em **Documentos**, escolha e autorize um arquivo. Selecione o modo **documentos** e faça uma pergunta com termos presentes no texto.

- A base guarda uma **cópia do texto**; não acompanha alterações do arquivo. Importe novamente para atualizar.
- A busca é **lexical**, com normalização de acentos, não busca semântica por embeddings. Consulta até 5 trechos por pergunta.
- Fontes são conferidas contra os IDs recuperados, mas isso **não garante que a resposta da IA seja correta ou sustentada**. Confira os trechos e os originais.
- Para TXT/MD, “página 1” representa o arquivo inteiro. Para PDF, indica a página física do arquivo.
- Limites: 20 MB, 500 mil caracteres e 200 páginas por arquivo; até 100 documentos e 5000 trechos na base.
- TXT/MD devem estar em UTF-8. PDFs digitalizados sem camada de texto precisam de OCR externo. PDFs criptografados não são suportados.
- Documentos não são enviados ao planejador de ações. Instruções contidas neles são tratadas como dados; o modo documentos não executa ferramentas.

## 3. Terminal e exemplos

```powershell
# Diagnóstico e planejamento sem executar
.\.venv\Scripts\python.exe -m assistente_pc --check
.\.venv\Scripts\python.exe -m assistente_pc --text "abra a calculadora" --dry-run

# Conversa contínua pelo teclado / voz sob demanda
.\.venv\Scripts\python.exe -m assistente_pc --keyboard --mode conversa
.\.venv\Scripts\python.exe -m assistente_pc

# Confirmar ações por voz; opcionalmente ler respostas
.\.venv\Scripts\python.exe -m assistente_pc --voice-confirm --speak

# Preferências explícitas (salvam/substituem diretamente)
.\.venv\Scripts\python.exe -m assistente_pc --remember profissao "Designer"
.\.venv\Scripts\python.exe -m assistente_pc --list-memories
.\.venv\Scripts\python.exe -m assistente_pc --forget profissao

# Ensinar um plano; salvar e executar têm confirmações separadas
.\.venv\Scripts\python.exe -m assistente_pc --text "abra a calculadora" --save-routine "calcular"
.\.venv\Scripts\python.exe -m assistente_pc --routine "calcular"
.\.venv\Scripts\python.exe -m assistente_pc --list-routines
.\.venv\Scripts\python.exe -m assistente_pc --delete-routine "calcular"

# Importação explícita (autoriza copiar o texto para a base)
.\.venv\Scripts\python.exe -m assistente_pc --import-file "C:\Trabalho\notas.txt"
.\.venv\Scripts\python.exe -m assistente_pc --text "Qual o prazo do projeto Aurora?" --mode documentos
.\.venv\Scripts\python.exe -m assistente_pc --list-documents
# Use o ID real mostrado no comando anterior:
.\.venv\Scripts\python.exe -m assistente_pc --remove-document 1

# Histórico opt-in e gerenciamento
.\.venv\Scripts\python.exe -m assistente_pc --keyboard --history
.\.venv\Scripts\python.exe -m assistente_pc --show-history
.\.venv\Scripts\python.exe -m assistente_pc --suggestions
.\.venv\Scripts\python.exe -m assistente_pc --clear-history
.\.venv\Scripts\python.exe -m assistente_pc --clear-data
```

No terminal, diga/digite **sair** para encerrar e **nova conversa** para limpar o contexto. A confirmação por voz aceita somente a transcrição exata **executar**, nunca “não executar”. Prefira confirmação digitada em ambientes ruidosos ou compartilhados.

Para escolher microfone, use `--list-devices` e depois `--device N` com o índice exibido. Para outro modelo, baixe-o com `ollama pull` e use `--model NOME` ou o campo da interface. Um modelo maior pode melhorar o entendimento, mas exige mais memória; um modelo menor pode errar mais. Trocar o nome no campo não baixa o modelo.

## Privacidade e controle

- Banco SQLite padrão: **`%LOCALAPPDATA%\AssistentePC\assistant.sqlite3`**. `--data-dir CAMINHO` permite escolher outra pasta. Mantenha-a fora de repositórios e de pastas sincronizadas se não quiser cópias externas.
- **Sem criptografia própria**: proteja sua conta/disco Windows. Memórias, rotinas, textos importados e histórico habilitado ficam legíveis para quem tem acesso aos dados.
- Histórico vem **desligado**, guarda no máximo 200 tentativas de execução e exibe as últimas 50. Inclui pedido, plano, data UTC e resultado; pode conter texto sensível. Rotinas e documentos são armazenados mesmo sem histórico quando você pede para salvá-los.
- Conversa recente fica em RAM. **Nova conversa** limpa contexto e plano pendente. Ao esquecer uma preferência, reinicie a conversa se o valor já apareceu nas respostas. Outras instâncias abertas também precisam ser reiniciadas após limpar dados.
- Não salva gravações. O microfone fica ativo apenas durante a captura solicitada. Não há palavra de ativação, captura de tela ou monitoramento de programas.
- O texto necessário é enviado ao Ollama em **`127.0.0.1:11434`**, no mesmo computador. Use modelos locais. Logs e configurações do Ollama são independentes deste projeto.
- Downloads iniciais exigem internet; IA, reconhecimento, fala e ações locais podem funcionar offline depois. Abrir sites/pesquisar requer internet, e a consulta é enviada ao site escolhido.
- Em **Privacidade**, apague histórico ou todos os dados. Os arquivos originais dos documentos não são apagados. Exclusão não remove backups nem garante apagamento forense do disco.

## Limites de segurança e estado do projeto

- Até cinco ações por plano. Sem `eval`, execução arbitrária de shell, comandos gerados pela IA, instalação de programas ou exclusão de arquivos.
- Digitação exige processo autorizado e verifica mudança de janela durante o envio. Terminais e IDEs não estão na lista permitida. Isso **não é um sandbox**: o nome do processo não comprova sua autenticidade e o programa não identifica o campo interno em foco. Atalhos podem afetar arquivos ou formulários. Nunca use em consoles de desenvolvedor, janelas administrativas, sistemas financeiros ou formulários sensíveis.
- O assistente **não vê a tela**, não confirma visualmente resultados e não garante que um aplicativo terminou de abrir. Pausas e verificações de processo reduzem, mas não eliminam, erros de foco. “Concluído” significa que as chamadas retornaram sem erro, não que o resultado foi verificado visualmente.
- **Parar** interrompe captura, pausas e execução nos pontos de verificação. Descarta uma resposta pendente da IA, mas não aborta imediatamente a requisição HTTP (timeout de 180s), importação ou leitura falada. A interface aguarda a operação terminar. O contexto temporário pode conter a resposta descartada; use Nova conversa para limpá-lo.
- **Ctrl+C** encerra no terminal. Mover o mouse para um canto da tela principal aciona o fail-safe do PyAutoGUI na próxima verificação. Não há rollback: ações já feitas não são desfeitas.
- Não é totalmente mãos livres; não faz treinamento contínuo, visão computacional, cliques arbitrários, navegação autônoma ou rotinas agendadas. Essas são evoluções futuras que exigem permissões, testes e limites próprios.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

A suíte usa a biblioteca padrão e simulações para testar validação, memória, retenção, rotinas, contexto, consulta a documentos de texto, fontes, cancelamento e restrições de destino. **Não substitui teste real de Tkinter, microfone, Vosk, PDFs, Ollama, SAPI5 e automação no Windows.**

Checklist manual no Windows:

1. `--check`, depois `--text "abra a calculadora" --dry-run`.
2. Abrir interface, testar os três modos e cancelar um plano sem executar.
3. Autorizar somente abrir a Calculadora; verificar que ela abriu.
4. Testar digitação com acentos no Bloco de Notas; trocar de janela durante a digitação e verificar interrupção.
5. Testar bloqueio de digitação no terminal; testar Parar durante a contagem de cinco segundos.
6. Salvar preferência e rotina, reiniciar e conferir persistência; apagar e conferir remoção.
7. Importar um TXT e um PDF de teste; conferir trechos, atualizar e remover sem alterar o original.
8. Conferir que histórico desligado não cria registros; ativar e testar limpeza.
9. Capturar fala com microfone e ouvir resposta com voz portuguesa instalada.

### Organização

`audio.py` captura · `planner.py` Ollama/validação · `executor.py` ações Windows · `storage.py` SQLite · `session.py` contexto · `knowledge.py` documentos · `speech.py` voz de saída · `desktop.py` interface · `__main__.py` terminal.
