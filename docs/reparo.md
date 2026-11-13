# Guia de Manutenção e Reparo Assistido por Canários (`MTTR <= 15 min`)

Quando qualquer seletor HTML do SIGAA ou dos portais da UFC sofrer alteração institucional:
1. Execute `uv run ufc-mcp diagnostico --json` para identificar qual canário (`C1` a `C8`) retornou `LAYOUT_MUDOU`.
2. Capture a página atualizada e anonimizada com `uv run ufc-mcp gravar`.
3. Ajuste exclusivamente o parser puro correspondente em `src/ufc_mcp/fontes/*/parser.py` e valide com `pytest`.

## Código de erro `ACESSO_AUTOMATIZADO_NEGADO`

Significa que o POST de login (`logar.do?dispatch=logOn`) devolveu a própria tela de login com a mensagem "Tentativa de acesso por aplicativo externo. Operação negada!". É um bloqueio deliberado do SIGAA a acesso automatizado: **não** é senha errada e **não** é mudança de layout (não rode o fluxo de reparo de seletores).

- Efeito: as ferramentas que exigem login ficam indisponíveis; RU, calendário e notícias (fontes públicas) continuam funcionando.
- Suspensão: o ufc-mcp cria o arquivo `login_suspenso` na pasta de configuração e não envia mais nenhuma requisição de login (nem a senha) enquanto ele existir. `status` mostra `suspenso: true` e `motivo_suspensao`.
- Como limpar: execute `ufc-mcp login` (ou `ufc-mcp login --so-sessao`), que remove a suspensão e tenta uma única vez; ou apague manualmente o arquivo `login_suspenso`.
- Não há reparo no código: o servidor não deve contornar o bloqueio (User-Agent, cabeçalhos ou emulação de navegador). Se o bloqueio persistir, use apenas as fontes públicas.
- Se a tela de login voltar sem essa mensagem (rejeição não reconhecida), o login também é suspenso e o erro é `LOGIN_SUSPENSO`, com mensagem indicando que o SIGAA devolveu a tela de login.
