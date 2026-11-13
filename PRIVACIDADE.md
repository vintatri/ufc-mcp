# Governança de Dados, LGPD e Transparência sobre Provedores de IA em Nuvem (`A6`)

## 1. Isolamento de Credenciais (Art. 28 da PoSIC/UFC)
- A senha institucional do SIGAA **jamais** é exposta a ferramentas MCP, logs ou modelos de linguagem.
- No modo recomendado `ufc-mcp login --so-sessao` (`CofreSessao`), a senha é descartada da memória imediatamente após o login inicial, mantendo-se apenas o cookie temporário de sessão.

## 2. Transparência sobre o Fluxo de Dados para o Provedor do LLM (Ameaça `A6`)
Embora a senha nunca saia da máquina local, **os dados JSON retornados pelas ferramentas MCP são enviados pelo cliente MCP (ex.: Claude Desktop, Cursor, Gemini CLI) ao provedor do modelo de IA em nuvem** (salvo quando o estudante utiliza um LLM 100% local via Ollama/llama.cpp).

Por essa razão, em conformidade com o **princípio da minimização (Art. 6º, III da LGPD)**, o `ufc-mcp` aplica por padrão (`identificadores = False`):
1. Supressão automática de nome civil, número de matrícula, CPF, RG, telefone e e-mail nos retornos do Portal do Discente, Pendências e Listagens;
2. Bloqueio estrutural de acesso ao cadastro socioeconômico (PRAE), dados de saúde e lista de participantes/colegas da Turma Virtual (`Participantes`).
