# ufc-mcp

Assistente acadêmico para estudantes da UFC, que funciona dentro do seu cliente de IA (Claude, Codex, Cursor e outros). Você pergunta em linguagem natural e o `ufc-mcp` consulta o SIGAA e as fontes públicas da UFC. Ele só lê dados e roda inteiramente no seu computador.

Exemplos de perguntas:

- "Onde e a que horas é minha aula hoje? Algum aviso do professor?"
- "Quantas faltas ainda posso ter em cada disciplina?"
- "Quanto preciso tirar na AP3 para passar direto?"
- "O que tem no RU hoje? Tem opção vegetariana?"
- "Me ajude a estudar para a prova de Fenômenos de Transporte."
- "Quais disciplinas posso pegar no semestre que vem sem choque de horário?"

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Licença MIT](https://img.shields.io/badge/licença-MIT-green)
![MCP](https://img.shields.io/badge/protocolo-MCP%20(stdio)-purple)
![Somente leitura](https://img.shields.io/badge/SIGAA-somente%20leitura-informational)

> Projeto independente, sem vínculo oficial com a UFC. Foi feito para o estudante usar com a própria conta. O SIGAA pode recusar acesso automatizado (veja [Limitações](#limitações)). Use com moderação e nunca compartilhe sua senha ou sessão.

## Primeiro uso

Nenhum dado pessoal vem configurado no código. Na primeira conversa, o assistente pergunta:

1. o **id numérico do seu curso** (o mesmo usado no calendário público do SIGAA);
2. o **nome do restaurante universitário** que você usa (por exemplo, Fortaleza, Pici, Quixadá ou Sobral; a ferramenta `restaurantes` lista as unidades).

Ele grava as respostas com a ferramenta `configurar`. Você também pode fazer isso pelo terminal:

```bash
ufc-mcp configurar --curso <id-do-curso> --restaurante <nome>
```

Sem esses dados, as ferramentas que dependem deles respondem `CONFIGURACAO_PENDENTE` e indicam o que falta.

## Ferramentas

O perfil `completo` expõe as 36 ferramentas. O perfil `essencial` expõe 16, as marcadas com ★, que cabem melhor em modelos menores.

### Painel do estudante

| Ferramenta | Para que serve |
|---|---|
| ★ `aula` | Bloco, sala e horário da aula, cruzados com avisos recentes do professor, plano de curso e feriados. |
| ★ `alertas` | Riscos acadêmicos: limite de 25% de faltas (Art. 113 do Regimento Geral) e notas necessárias para aprovação ou avaliação final (Art. 114). |
| `faltas` | Faltas e encontros restantes por disciplina. |
| `dia` | Aulas, prazos, eventos e cardápio do RU em uma resposta. |
| `semana` | O mesmo que `dia`, para sete dias seguidos. |
| ★ `estudo` | Roteiro de estudo: situação de notas, cronograma do professor e materiais da turma. |
| ★ `grade` | Até três sugestões de grade sem choque de horário, validadas contra pré-requisitos e co-requisitos. |
| `matricula` | Disciplinas elegíveis, bloqueadas por pré-requisito e o que cada uma libera. |
| `ics` | Exporta grade e calendário para um arquivo `.ics` (RFC 5545). |

### SIGAA (conta do estudante)

| Ferramenta | Para que serve |
|---|---|
| ★ `portal` | Curso, situação, integralização, turmas do semestre e atividades próximas. |
| ★ `turmas` | Turmas matriculadas, com local e horários. |
| `horario` | Grade semanal, de segunda a sábado. |
| `agenda` | Agenda consolidada das turmas. |
| ★ `progresso` | Integralização e grafo de pré-requisitos do currículo. |
| `ira` | Evolução do IRA por semestre, comparada com a média do curso. |
| `pendencias` | Carga horária pendente, ENADE e biblioteca. |
| `biblioteca` | Empréstimos e situação na biblioteca. |
| `listagem` | Telas de listagem do portal (ênfases, trancamentos, mobilidade, bolsas e outras). |
| ★ `ofertas` | Turmas ofertadas no semestre, com horários, locais, docentes e vagas. |

### Turma Virtual

| Ferramenta | Para que serve |
|---|---|
| ★ `turma` | Tópicos de aula e materiais anexados, com o `id_material` de cada arquivo. |
| ★ `notas` | Notas por unidade, média parcial, faltas e situação. |
| `frequencia` | Mapa de presença e total de faltas. |
| `tarefas` | Tarefas com prazo e situação de envio. |
| `avaliacoes` | Datas de provas e avaliações. |
| `avisos` | Avisos publicados pelo professor. |
| ★ `plano` | Metodologia, avaliação, cronograma e bibliografia. |
| ★ `baixar` | Baixa slides e listas para uma pasta local e extrai o texto (PDF, TXT, MD). |

### Fontes públicas (não precisam de login)

| Ferramenta | Para que serve |
|---|---|
| ★ `cardapio` | Cardápio do RU, com opções vegetarianas e alertas de glúten e lactose. |
| `cardapio_semana` | Cardápios de segunda a sexta. |
| `restaurantes` | Unidades do RU (Fortaleza, Russas, Quixadá, Crateús e Sobral). |
| ★ `calendario` | Feriados, recessos e prazos do Calendário Universitário. |
| `calendario_curso` | Períodos de matrícula e processamento do seu curso. |
| `noticias` | Avisos da UFC Informa, PROGRAD e PRAE. |

### Sistema

| Ferramenta | Para que serve |
|---|---|
| ★ `status` | Estado do cofre, da sessão, dos limites de taxa e dos dados pendentes. Nunca devolve senha nem cookie. |
| ★ `configurar` | Grava curso e restaurante no primeiro uso. |
| `diagnostico` | Verifica se o layout do SIGAA mudou e se algum parser quebrou. |

## Instalação

Requisitos: [`uv`](https://docs.astral.sh/uv/), que instala o Python 3.11+ se necessário, e um cliente MCP.

### 1. Instalar

```bash
uv tool install git+https://github.com/vintatri/ufc-mcp
```

O comando `ufc-mcp` fica no seu `PATH` (normalmente em `~/.local/bin`). Para atualizar: `uv tool upgrade ufc-mcp`.

Para trabalhar com o código-fonte:

```bash
git clone https://github.com/vintatri/ufc-mcp.git
cd ufc-mcp
uv sync
uv run ufc-mcp --help
```

### 2. Guardar a senha do SIGAA (opcional)

Sem login, as fontes públicas (RU, calendário, notícias e ofertas do curso) funcionam normalmente. Para as ferramentas do SIGAA e da Turma Virtual, rode:

```bash
ufc-mcp login --cofre sistema
```

O programa pede usuário e senha por prompt oculto. A senha nunca é aceita como argumento, então não fica no histórico do shell. Escolha o modo de armazenamento:

| Modo | Comando | Onde fica |
|---|---|---|
| Chaveiro do sistema (recomendado) | `ufc-mcp login --cofre sistema` | Cofre do seu sistema operacional (GNOME Keyring, KWallet, Chaveiro do macOS ou Gerenciador de Credenciais do Windows). |
| Arquivo criptografado | `ufc-mcp login --cofre arquivo` | `cofre.bin`, com AES-256-GCM e chave derivada da frase-mestra por Argon2id. Para o servidor abri-lo, defina `UFC_MCP_FRASE_MESTRA` no ambiente do cliente. |
| Só sessão | `ufc-mcp login --so-sessao` | A senha é descartada logo após o login. Fica apenas o cookie temporário, válido por cerca de 1h30. |

Comandos úteis: `ufc-mcp status` mostra o estado do cofre e da sessão. `ufc-mcp logout` apaga credenciais, sessão e caches.

### 3. Conectar ao cliente

**Claude Code**

```bash
claude mcp add --scope user ufc-mcp -- ufc-mcp servir
```

Confira com `claude mcp list` ou com `/mcp` dentro do Claude Code. Para o perfil reduzido, acrescente `--perfil essencial` depois de `servir`.

**Codex**

```bash
codex mcp add ufc-mcp -- ufc-mcp servir
```

Ou edite `~/.codex/config.toml`:

```toml
[mcp_servers.ufc-mcp]
command = "ufc-mcp"
args = ["servir", "--perfil", "completo"]
```

Se o Codex não encontrar o comando, use o caminho absoluto (`which ufc-mcp`) em `command`.

**Claude Desktop, Cursor, VS Code e Gemini CLI**

O programa gera o bloco de configuração. Ele imprime o JSON, ou grava no arquivo do cliente com backup se você pedir:

```bash
ufc-mcp instalar --cliente claude-desktop           # só imprime o JSON
ufc-mcp instalar --cliente cursor --aplicar         # grava no arquivo do cliente
```

Clientes aceitos: `claude-desktop`, `claude-code`, `cursor`, `vscode` e `gemini`. Rode `instalar` depois do `uv tool install`, porque ele registra o caminho do Python usado, que precisa ser permanente.

Reinicie o cliente e faça a primeira pergunta. O assistente vai pedir curso e restaurante.

## Configuração

Os dados pessoais são gravados no `config.toml` da pasta de configuração do usuário (no Linux, `~/.config/ufc-mcp/config.toml`). Também é possível usar variáveis de ambiente `UFC_MCP_*`, que têm prioridade.

| Chave no `config.toml` | Variável de ambiente | Padrão | Uso |
|---|---|---|---|
| `curso` | `UFC_MCP_CURSO` | não definido | Id numérico do seu curso no portal público do SIGAA. Preenchido no primeiro uso. |
| `restaurante` | `UFC_MCP_RESTAURANTE` | não definido | Unidade do RU usada quando você não informa outra, pelo nome (ex.: `Fortaleza`, `Pici`, `Quixadá`). Preenchido no primeiro uso. |
| `identificadores` | `UFC_MCP_IDENTIFICADORES` | `false` | Se `true`, mostra nome e matrícula nas respostas. |
| `perfil` | `UFC_MCP_PERFIL` | `completo` | `completo` (36 ferramentas) ou `essencial` (16). |
| `desativadas`, `grupos_desativados` | — | `[]` | Desliga ferramentas ou grupos específicos. |
| `nivel_log` | `UFC_MCP_NIVEL_LOG` | `INFO` | Nível de log. O log vai para stderr. |

## Segurança e privacidade

- **A senha não chega ao modelo.** Ela é lida só no formulário de login do SIGAA. Nenhuma ferramenta devolve senha, cookie ou token. O `status` mostra apenas o estado do cofre.
- **Nunca por argumento.** Senha e frase-mestra são lidas por prompt oculto e não passam pelo histórico do shell nem pela lista de processos.
- **Armazenamento cifrado.** Use o chaveiro do sistema ou o cofre AES-256-GCM com Argon2id. O cofre em arquivo é gravado com permissão `0600`, recusa frase errada e detecta adulteração. Chaveiros que guardam texto puro são recusados.
- **Sem vazamento em logs.** O log vai para stderr e passa por um filtro que remove senhas, cookies, e-mails e números de matrícula ou CPF. Os objetos de credencial não mostram a senha em `repr`.
- **Rede restrita.** Só HTTPS, e só para domínios da UFC: `si3.ufc.br`, `ufc2012.ufc.br`, `ufcinforma.ufc.br`, `prograd.ufc.br`, `prae.ufc.br` e `dados.ufc.br`. Redirecionamentos são seguidos um a um e validados, com verificação de certificado.
- **Somente leitura.** Só são permitidas 22 ações de menu e 12 postbacks de consulta. Trancamento, supressão, envio de tarefa, alteração cadastral e emissão de documentos são bloqueados pelo código.
- **Texto de terceiros é dado.** Avisos, fóruns, notícias e PDFs passam por sanitização (HTML executável e caracteres Unicode invisíveis são removidos) e vêm marcados como `texto_externo`. O modelo deve tratá-los como conteúdo, nunca como instrução.
- **Acesso moderado.** Há pausa mínima entre requisições e limites por minuto, hora e dia. O `User-Agent` se identifica como cliente pessoal, sem fingir ser navegador.

**Dados enviados ao modelo.** A senha fica no seu computador. As respostas das ferramentas, porém, passam pelo seu cliente MCP até o provedor do modelo (Anthropic, OpenAI e outros), a menos que você use um modelo totalmente local. Por isso, nome, matrícula, CPF, telefone e e-mail vêm omitidos por padrão, a lista de colegas da Turma Virtual é bloqueada e qualquer tela fora da lista de leitura é recusada. Detalhes em [`PRIVACIDADE.md`](PRIVACIDADE.md) e [`SECURITY.md`](SECURITY.md).

Para apagar tudo: `ufc-mcp logout`.

## Limitações

- **O SIGAA pode bloquear login automatizado.** Nesse caso, as ferramentas que exigem login ficam suspensas com o erro `ACESSO_AUTOMATIZADO_NEGADO`. O `ufc-mcp` não tenta contornar o bloqueio, e as fontes públicas continuam funcionando. Em caso de dúvida sobre o uso recorrente, consulte a STI/UFC. Veja [`docs/reparo.md`](docs/reparo.md).
- O SIGAA não tem API pública. Os dados vêm da leitura das páginas. Quando a UFC muda o layout, algum parser pode falhar. O `ufc-mcp diagnostico` indica qual.
- O uso é local e individual (`stdio`). Não há suporte para hospedar o servidor na nuvem nem para compartilhá-lo entre pessoas.

## Desenvolvimento

```bash
git clone https://github.com/vintatri/ufc-mcp.git && cd ufc-mcp
uv sync --extra dev
uv run ruff check src       # lint
uv run mypy src             # tipagem
uv run ufc-mcp diagnostico  # canários das fontes públicas
```

Documentação: [`docs/instalacao.md`](docs/instalacao.md) · [`docs/decisoes.md`](docs/decisoes.md) · [`docs/reparo.md`](docs/reparo.md) · [`docs/telas-turma-virtual.md`](docs/telas-turma-virtual.md) · [`docs/adaptar-outra-instituicao.md`](docs/adaptar-outra-instituicao.md)

## Licença

[MIT](LICENSE).
