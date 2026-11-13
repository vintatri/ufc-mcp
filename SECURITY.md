# Política de Segurança e Modelo de Ameaças (`A1` a `A12`)

## 1. Topologia de Execução Exclusivamente Local (`stdio`)
O `ufc-mcp` executa **exclusivamente como subprocesso local via `stdio`** na máquina do próprio estudante (titular dos dados). É expressamente proibido hospedar este servidor em nuvem ou em modo multiusuário compartilhado (Ameaça `A11`).

## 2. Defesa em dois níveis contra injeção indireta de prompt
1. **Nível 1 (redução de obediência):** Todo texto proveniente de terceiros (notícias, avisos da Turma Virtual, descrições de tarefas e PDFs) passa por `nucleo/higiene.py` (remoção de `<script>`, `<style>` e categorias Unicode `Cc`, `Cf`, `Co`, `Cs`) e é encapsulado em `TextoExterno` com guarda explícita no topo do `Envelope`.
2. **Nível 2 (contenção das consequências: nenhuma escrita no SIGAA):** A segurança efetiva não depende das anotações MCP (`readOnlyHint` é só uma dica para a interface). O módulo `nucleo/risco.py` bloqueia estruturalmente qualquer ação fora de `ACOES_MENU_PERMITIDAS` (22 consultas) e `POSTBACKS_PERMITIDOS` (12 postbacks), impedindo trancamentos, supressões, alterações cadastrais, envios de tarefas ou emissão de documentos com código de verificação.
