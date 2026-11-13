# Diário de Decisões de Engenharia e Arquitetura (`D1` a `D16`)

Registro das decisões humanas de projeto consolidadas na Especificação Unificada v2.2:
- **D1 a D3:** Escopo de equipe discente da UFC (auto-estudo instrumental sob o Art. 2º, XIII da Resolução CNS nº 510/2016), Categoria III e articulação entre Eixo I (Ética e Governança) e Eixo III (Inovação Pedagógica).
- **D4 a D6:** Python 3.11+, arquitetura tripla de cofre (`CofreSistema`, `CofreSessao`, `CofreArquivo`) e Perfil B Educado Estrito ($\Delta t \ge 1{,}0\text{ s}$, serialização por `asyncio.Lock` para proteger o `javax.faces.ViewState` do JSF 1.x).
- **D7 e D8:** Exclusão de 18 grupos de escrita e de ações de emissão de documentos (`atestadoMatricula`, `historico`, `declaracaoVinculo`) para preservar o invariante de zero mutação no banco de dados da UFC.
- **D15 e D16:** Sandbox local paginada para leitura de PDFs de aula (`baixar`) e suporte a dois perfis de catálogo (`completo` com 36 ferramentas e `essencial` com 16 ferramentas).
