# Guia de Adaptação para Outras IFES que Utilizam SIGAA

Para adaptar o `ufc-mcp` a outra universidade federal:
1. Atualize `HOSTS_PERMITIDOS` em `src/ufc_mcp/nucleo/http.py` com o domínio institucional.
2. Ajuste as constantes regimentais em `servicos/notas_ufc.py` e `servicos/faltas.py`.
3. Reexecute os canários `C5` a `C8` com `ufc-mcp diagnostico`.
