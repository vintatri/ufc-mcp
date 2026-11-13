# Instalação e primeiro uso

1. Instale as dependências: `uv sync`
2. (Opcional) Guarde a senha do SIGAA no chaveiro do sistema: `uv run ufc-mcp login --cofre sistema`. Sem isso, as fontes públicas (RU, calendário, notícias e ofertas) continuam funcionando.
3. Informe seu curso e seu restaurante: `uv run ufc-mcp configurar --curso <id-do-curso> --restaurante <nome>`. Se preferir, o próprio assistente pergunta isso na primeira conversa.
4. Gere a configuração do cliente MCP: `uv run ufc-mcp instalar --cliente claude-desktop`
