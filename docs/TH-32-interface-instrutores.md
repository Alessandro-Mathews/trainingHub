# TH-32 — Interface administrativa de Instrutores

## Objetivo e escopo

Disponibilizar a seção administrativa **Instrutores** no painel existente, com listagem,
cadastro, edição de nome/e-mail e ativação/desativação da conta associada. A implementação
segue o padrão visual, de navegação e de recuperação corrigido na TH-31.

Base de trabalho: `feature/TH-32-interface-instrutores`, inicialmente limpa, sobre
`94a1311` (merge da TH-31). Todas as mudanças ficam sem staging e sem commit.

Não foram alterados backend, migrations, banco persistente, CSS, contratos de API,
toolchain ou regras de autorização. Não foram adicionadas dependências.

## Navegação e apresentação

`public/index.html` contém a seção `#instrutores`, o item administrativo da sidebar
e três modais: cadastro, edição e confirmação de situação da conta.
`public/js/app.js` integra hash, `hidden`, `aria-current`, título da página, contexto
da topbar, foco do conteúdo e fechamento do offcanvas. O módulo só consulta recursos
de Instrutores após o sucesso de `/api/auth/me`.

A tabela apresenta nome, e-mail, situação da conta, data do cadastro como Instrutor
e ações. A data SQLite mantém sua representação de calendário, sem inferir fuso horário.
Loading, vazio com CTA funcional, erro, retry GET e feedback de sucesso são explícitos.

## Endpoints e join

| Operação | Endpoint | Contrato enviado |
| --- | --- | --- |
| Sessão | `GET /api/auth/me` | Nenhum body |
| Listagem autoritativa | `GET /api/instrutores` | Sem query/body |
| Contas da academia | `GET /api/usuarios?academia_id=<academiaId>` | Tenant da sessão |
| Perfil para cadastro | `GET /api/perfis` | Sem body |
| Nova conta | `POST /api/usuarios` | `academia_id`, `perfil_id`, `nome`, `email`, `senha` |
| Cadastro como Instrutor | `POST /api/instrutores` | Somente `usuario_id` |
| Edição da conta | `PUT /api/usuarios/{usuario_id}` | Somente `nome`, `email` |
| Situação da conta | `PUT /api/usuarios/{usuario_id}/status` | Somente `ativo`, boolean |

O join local usa `Map` com `Usuario.id` canônico como chave e `Instrutor.usuario_id`
como referência. Cada carregamento normal realiza um GET Instrutores e um GET Usuarios
em paralelo. Perfis é uma consulta independente de metadados. Não há N+1.

Instrutor é a fonte da tabela. Contas com perfil Instrutor sem esse registro não viram
linhas. Registros históricos continuam visíveis com conta inativa ou perfil posteriormente
alterado. Na ausência de Usuario, a linha permanece com “Dados do usuário indisponíveis”,
ações desabilitadas e opção de atualizar a listagem.

Snapshots inválidos, IDs duplicados, contas de outro tenant e tipos incompatíveis são
rejeitados. As duas consultas precisam terminar antes de liberar outra operação.

## Cadastro e elegibilidade

O perfil é descoberto por `nome === 'Instrutor' && ativo === 1`, sem ID fixo ou fallback.
Perfil ausente, inativo, incompatível ou indisponível bloqueia o cadastro, preservando a
listagem e as operações sobre contas já registradas.

No modo **Criar nova conta**, o módulo confirma o POST Usuario, conserva o ID exato
retornado e envia somente esse `usuario_id` ao POST Instrutor.

No modo **Vincular usuário existente**, exige seleção explícita de uma conta ativa da
academia autenticada, com o perfil Instrutor ativo e sem registro Instrutor existente.
Histórico Aluno não interfere nessa seleção. O módulo não consulta endpoints de Aluno
ou de vínculo Aluno–Instrutor. O backend revalida elegibilidade e autorização na escrita.

## Cadastro parcial e respostas ambíguas

Se a conta foi confirmada e o cadastro Instrutor não foi confirmado, somente o ID da conta
fica pendente em memória. O formulário oferece **Tentar concluir cadastro do instrutor**.
Essa ação consulta o snapshot antes de qualquer novo POST Instrutor: um registro já
existente conclui a recuperação sem escrita; uma conta inelegível apresenta feedback.
O POST Usuario não é repetido.

**Encerrar tentativa** elimina somente estado local do formulário. Não exclui ou desativa
a conta, não altera perfil, não faz compensação e não envia nenhuma requisição. Essa saída
permanece acessível quando a conta ficou inelegível ou leituras posteriores falharam (I1).
Incerteza sobre uma escrita permanece até uma leitura válida. Após reload, uma conta
ainda elegível aparece naturalmente no seletor.

Troca de modo, reconciliação e novo snapshot descartam a seleção de conta existente (I2).
O usuário precisa selecionar novamente; o módulo não associa contas por coincidência
de e-mail.

Timeout, transporte e resposta incompatível podem deixar o resultado desconhecido.
Não há retry automático de POST ou PUT. POST Usuario ambíguo exige atualização e escolha
explícita. POST Instrutor ambíguo exige reconciliação antes da nova tentativa manual.
PUT ambíguo mantém feedback e bloqueia outras escritas até atualizar a listagem.

## Edição, situação e histórico

Editar altera apenas `nome` e `email` da conta, usando `usuario_id`, nunca `Instrutor.id`.
Contas inativas ou com outro perfil atual continuam editáveis conforme a autorização
de Usuario/TH-63. A interface não altera academia, perfil, senha ou data de criação.

Ativar/desativar envia um boolean real e aguarda resposta pública válida antes de atualizar
a apresentação definitiva. O Instrutor continua listado quando a conta é desativada.
A comparação exata entre `Usuario.id` e `authContext.userId` impede autodesativação na UI,
sem impedir edição. O backend mantém a decisão final.

## Segurança e int64

- Reutilização integral de `api.js`, sem mudanças no parser ou serializer da TH-31.
- IDs internos permanecem strings decimais canônicas positivas no intervalo int64.
  Payloads emitem os IDs como números JSON exatos, sem conversão para `Number`.
- Cobertura explícita: `1`, `1099511627776`, `9007199254740993`, `9223372036854775807`.
  Inclui sessão, join/Map, IDs Instrutor/Usuario, POST, URLs, PUT e autodesativação.
- API interna com sessão existente, sem JWT, armazenamento no navegador ou inferência
  de papel a partir de `perfilId`. Administrador/Gestor e tenant são validados pelo servidor.
- `401` oculta o painel e encaminha ao login; `403` apresenta erro sem loop.
- Dados externos entram no DOM por `textContent`, `createElement`, `replaceChildren`
  e `value`. Nomes/e-mails maliciosos não viram HTML executável.
- Senha inicial é removida do input imediatamente após despacho, inclusive em falhas,
  e também no fechamento do modal e em `pagehide`. Não é retida no estado do módulo.
- Travas de submissão/carregamento impedem double submit e atualização concorrente
  durante uma escrita. Modais não fecham no meio da submissão.

## Responsividade e acessibilidade

Foram reutilizados CSS e Bootstrap locais existentes. Desktop mantém tabela administrativa;
mobile usa `table-responsive` com rolagem horizontal local, sem redesign em cards.
Os cenários opcionais de navegador incluem desktop e viewport `375 × 812`, verificando
ausência de overflow horizontal global.

Labels associados, caption, headers com `scope`, região da tabela focalizável, `aria-live`,
`aria-busy`, feedback textual e botões reais seguem a TH-31. Os modais usam Bootstrap
para teclado/Escape e contenção de foco, com foco inicial e retorno ao acionador.

## Testes executados

| Verificação | Resultado local |
| --- | --- |
| `python tests/instrutores_interface.py` | 459 assertions JS/DOM e 42 requisições HTTP; aprovado |
| `python tests/alunos_interface.py` | 386 assertions JS/DOM e 26 requisições HTTP; aprovado |
| `python tests/interface_web.py` | TH-21/TH-28 JS/DOM, autenticação, HTML/assets e HTTP; aprovado |
| `python tests/instrutor_integration.py` | 154 verificações HTTP; aprovado |
| `python tests/usuario_integration.py` | 359 verificações HTTP, incluindo TH-63; aprovado |
| `python tests/perfil_integration.py` | 138 verificações HTTP; aprovado |
| `python tests/auth_integration.py` | Senhas, sessão e contratos HTTP; aprovado |
| `python tests/authorization_integration.py` | 247 verificações HTTP; aprovado |
| `python tests/aluno_integration.py` | 146 verificações HTTP; aprovado |
| `python tests/aluno_instrutor_integration.py` | 175 verificações HTTP; aprovado |
| `cmake --build build --parallel 2` | Aprovado; build atualizado, sem trabalho pendente |
| `cmake --build build/security-tests --parallel 2` | Aprovado; build atualizado, sem trabalho pendente |
| `ctest --test-dir build/security-tests --output-on-failure --no-tests=error` | 3/3 aprovados |
| `node --check public/js/instrutores.js` e `node --check tests/interface_web.mjs` | Aprovados |
| `python tests/interface_web.py --browser` | Falhou antes dos cenários visuais: `CDP timeout: Page.enable` |

A suíte TH-32 usa o JavaScript entregue, respostas textuais com IDs exatos, DOM de teste e
servidor real com SQLite temporário. Inclui I1/I2, respostas inválidas, histórico com Aluno,
edição/status de histórico e IDs de conta diferentes dos IDs de Instrutor. Fixtures com
INT64_MAX são inseridas somente depois das operações que precisam de AUTOINCREMENT.
Node ausente causa falha explícita nos checks críticos, sem sucesso silencioso.

O CI recebeu somente `python tests/instrutores_interface.py`; runner, MSYS2, GCC, Ninja,
vcpkg e triplet permanecem iguais. A execução remota do CI não foi realizada nesta tarefa.
`tests/alunos_interface.py` recebeu somente a resolução do novo import estático de `app.js`.

## Limitações e separação da TH-33

Não houve validação visual real nesta execução: o Chrome falhou no comando inicial
`Page.enable`. Os testes DOM não comprovam layout, foco real ou comportamento visual
do Bootstrap. Os cenários de navegador estão implementados para execução em ambiente funcional.

As duas escritas do cadastro não formam transação única; a recuperação parcial trata essa
característica existente. Snapshots das seções Alunos/Instrutores são independentes;
ao editar uma conta compartilhada entre históricos, use **Atualizar listagem** na outra
seção. Atualizar também reconcilia mudanças concorrentes feitas por outros administradores.

A TH-32 não implementa vínculo Aluno–Instrutor, atribuição ou troca de alunos, remoção de
vínculo ou painel de alunos do instrutor. Nenhum endpoint TH-30 foi integrado à interface.

O banco persistente manteve SHA-256
`10c935f52ad5feada7f2c25d9257ccbb01cc076d7afd1306518c98f5970baba8`.
