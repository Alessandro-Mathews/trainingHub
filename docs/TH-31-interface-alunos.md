# TH-31 — Interface administrativa de Alunos

## Objetivo e arquitetura

Gerenciar os registros Aluno da academia autenticada, preservando a identidade
TH-21 e a autenticação TH-28. A implementação usa HTML, JavaScript ES Modules,
CSS existente e Bootstrap 5 local. Não há framework, CDN ou API externa nova.

`index.html` contém `section#alunos`, link na sidebar e três modais Bootstrap:
cadastro, edição e confirmação de status. O cadastro reúne os modos Criar nova
conta e Vincular usuário existente. `app.js` integra `#alunos` ao roteamento,
título/contexto, `aria-current`, sections, foco e fechamento do offcanvas.

`alunos.js` mantém snapshots, Map de Usuarios, join, renderização, estados e
operações. `api.js` concentra requests, parser, serializer e validação de IDs.
Não foram alterados backend, migrations, dependências, CMake ou banco local.

## Autenticação, tenant e contratos

A seção só consulta dados depois da validação de `GET /api/auth/me`, inclusive
em `/index.html#alunos`. O contexto fornece `userId`, `academiaId` e `perfilId`;
não contém Role. O frontend não infere permissões pelo ID do Perfil.

| Endpoint | Uso e contrato |
|---|---|
| `GET /api/alunos` | Array de Alunos; sem query/body |
| `GET /api/alunos/{id}` | Aluno individual; disponível no backend, dispensável na carga normal |
| `GET /api/usuarios?academia_id=...` | Contas administrativas do tenant autenticado |
| `GET /api/perfis` | Descoberta do Perfil canônico Aluno |
| `POST /api/usuarios` | `academia_id`, `perfil_id`, `nome`, `email`, `senha`; retorna Usuario público, HTTP 201 |
| `POST /api/alunos` | Somente `usuario_id`; retorna Aluno, HTTP 201 |
| `PUT /api/usuarios/{usuario_id}` | Somente `nome` e `email`; retorna Usuario público, HTTP 200 |
| `PUT /api/usuarios/{usuario_id}/status` | Somente `ativo` boolean; retorna Usuario público, HTTP 200 |

Aluno público contém `id`, `usuario_id` e `criado_em`. Usuario público contém
`id`, `academia_id`, `perfil_id`, `nome`, `email`, `ativo` e `criado_em`.
Perfil usa `ativo` inteiro 0/1; Usuario usa boolean. A busca do Perfil exige
exatamente `nome === 'Aluno'` e `ativo === 1`. Ausência, inatividade ou erro
de Perfis bloqueiam cadastro com feedback, preservando a listagem independente.

Backend autoriza ADMIN/GESTOR e restringe as operações ao tenant da sessão.
O parâmetro de consulta e o cadastro usam `academiaId` confirmado por `/me`.
O frontend também rejeita resposta Usuario de outra academia como incompatível.

401 oculta a aplicação, limpa a senha e redireciona para login. 403 apresenta
Sem permissão ou feedback da operação, sem redirecionamentos repetidos.

## Listagem e composição

A fonte autoritativa é Aluno, não uma filtragem de Usuarios pelo Perfil atual.
Cada carga faz um GET de Alunos e um GET de Usuarios, em paralelo, sem consulta
individual por linha. O Map usa `usuario.id` string e o join usa `aluno.usuario_id`.
Um GET independente de Perfis habilita o cadastro. Não há N+1.

A tabela mostra Nome, E-mail, Situação da conta, Cadastro como Aluno e Ações.
Ativo/Inativo derivam exclusivamente de `Usuario.ativo`. Contas inativas e
registros históricos continuam na lista. Não existem dados simulados, matrícula,
plano, mensalidade ou treino. `Aluno` é uma constante canônica do domínio;
nenhum ID de Perfil, tenant ou pessoa é fixado no produto.

Se faltar Usuario no join, a linha permanece com Dados do usuário indisponíveis.
Não se inventam nome, e-mail ou situação; ações dessa linha ficam bloqueadas.
Atualizar pode reconciliar a composição.

Datas SQLite `YYYY-MM-DD HH:mm:ss` são validadas por componentes, incluindo
ano bissexto, e apresentadas como `DD/MM/YYYY HH:mm`. Não se usa parsing Date
ou conversão de timezone. Datas inválidas mostram Data indisponível.

## Cadastro e recuperação

Criar nova conta solicita Nome, E-mail e Senha inicial. Academia vem da sessão;
Perfil vem da API. Não se pedem status, academia, Perfil ou Instrutor.
Senha usa `type=password` e `autocomplete=new-password`, sem transformação.
O input é limpo imediatamente após o envio, no encerramento e ao sair da página.
Senha não vai para logs, mensagens, URL, storage ou estado de recuperação.

Após POST Usuario confirmado, o ID retornado fica em memória. Em seguida, o
frontend envia apenas POST Aluno. Falha nessa segunda etapa preserva o ID e
mostra a situação parcial com Tentar concluir cadastro do aluno. Não há exclusão
compensatória ou repetição de POST Usuario.

A conclusão manual consulta Alunos/Usuarios primeiro. Se o Aluno já existir,
confirma conclusão sem novo POST. Caso contrário, somente envia POST Aluno
se a conta ainda for elegível. Backend revalida elegibilidade e concorrência.

Uma pendência oferece Encerrar tentativa, inclusive quando a conta perde
elegibilidade. A ação abandona somente o estado local: não executa request,
não exclui ou altera a conta e não repete POST Usuario. Limpa formulário,
seleção e mensagens da tentativa, permitindo cadastrar outra pessoa sem reload.
O acesso à pendência permanece disponível se uma consulta posterior falhar.
Se o resultado de uma escrita ainda for incerto, continua necessário atualizar
os dados antes de outra escrita; encerrar não transforma incerteza em sucesso.

Timeout, falha de transporte, resposta incompatível ou erro interno de escrita
podem deixar resultado desconhecido. Não há retry automático de POST/PUT.
No POST Usuario, a UI informa que não pôde confirmar a criação e exige GET
antes de outra escrita. Após reconciliação, mostra o modo de Usuario existente,
sem selecionar automaticamente uma conta por coincidência de e-mail.
Qualquer seleção anterior é descartada na troca de modos e na reconciliação
de criação ambígua. O botão de vínculo fica indisponível até nova escolha
explícita de uma conta elegível, mesmo após fechar e reabrir o modal.

Vincular usuário existente lista somente contas do tenant, ativas, com o Perfil
Aluno descoberto e sem registro Aluno no snapshot. Esse fluxo também recupera
contas parciais depois de reload. Não há persistência local do fluxo nem página
genérica para editar Usuarios sem Aluno.

## Edição e status

Edição preenche somente Nome e E-mail. O path usa `usuario_id`, não `aluno.id`.
O DTO não inclui senha, status, academia, Perfil ou campos imutáveis. Falhas
recuperáveis preservam o formulário. Sucesso substitui o Usuario no Map pela
resposta autoritativa, sem GET completo desnecessário.

Ativar/Desativar abre confirmação. Desativação explica que impede login e
preserva Aluno. A UI aguarda a resposta antes de mudar situação; contas inativas
continuam listadas e oferecem Ativar. A própria conta tem Desativar desabilitado
com explicação acessível, sem substituir o 403 autoritativo do backend.

Resultado PUT desconhecido mantém a última informação confirmada, acompanhada
de aviso de incerteza. Novas escritas ficam bloqueadas até Atualizar. A UI não
afirma que o estado antigo continua verdadeiro no servidor.

## Int64 sem perda

IDs internos são strings decimais canônicas positivas na faixa
`1..9223372036854775807`. `parseId` rejeita Number, zeros iniciais, sinal,
espaços, fração, expoente e overflow. BigInt é usado somente na validação.
Comparações, Map keys, valores de select e URLs usam as strings exatas.

`parseJson` lê o texto da resposta e percorre a gramática JSON: objetos, arrays,
strings/escapes, booleanos, null e números. Antes de converter um token numérico,
reconhece as propriedades `id`, `academia_id`, `perfil_id`, `usuario_id`,
`instrutor_id`, `aluno_id`, `userId`, `academiaId` e `perfilId`. IDs positivos
viram strings sem passar por Number; `instrutor_id` também aceita null.
Outros números mantêm a semântica nativa. JSON/IDs incompatíveis são rejeitados.
Existe limite de profundidade de 128; propriedades como `__proto__` permanecem
dados próprios, sem alterar o protótipo do objeto.

Não há regex global substituindo texto. Regex locais reconhecem tokens apenas
na posição atual da gramática. Strings e escapes são validados pelo parser nativo.

`serializeBody` aceita DTOs rasos com escalares. Campos ID exigem strings
validadas e saem como números JSON crus. Demais campos usam JSON.stringify.
Exemplo de body exato: `{"usuario_id":9223372036854775807}`. IDs não são
emitidos entre aspas e não passam por Number. O login preserva sua emissão
numérica existente e reutiliza a validação de ID. Academias foi adaptado à
representação compartilhada sem mudar a interface.

## Requests, estados e segurança

O wrapper preserva timeout de 15 segundos, signal de abort,
`credentials: same-origin` e `cache: no-store`. HTTP é verificado antes do body:
400/401/403/404/409/500 mantêm seu status. Falha de fetch/leitura, AbortError,
TypeError e TimeoutError resultam em status 0. JSON inválido em 2xx resulta em
502. Os PUTs TH-63 retornam `Cache-Control: no-store` no servidor.

Loading apresenta spinner, texto e aria-busy; Atualizar fica desabilitado.
Lista vazia apresenta Nenhum aluno cadastrado e CTA quando cadastro disponível.
Erros usam mensagens locais, sem SQL, stack, path ou body bruto. GET tem retry
manual. Escritas não têm retry automático.

Flags impedem cargas simultâneas, submit duplo e refresh durante escrita.
Escrita não começa durante GET da listagem; uma resposta antiga dessa carga não
pode sobrescrever mutação posterior. Snapshots Aluno/Usuario são publicados juntos.

Toda informação externa usa createElement, textContent, replaceChildren ou
value. Não há innerHTML com dados externos, inclusive no nome da confirmação.
Não existem acesso a cookies, Role inferida ou storage próprio.

## Responsividade e acessibilidade

Foram reutilizados sidebar, topbar, panels, botões, badges, tabela e breakpoints
existentes. Nenhuma alteração em style.css foi necessária para a implementação.
A tabela fica em table-responsive; ações usam flex-wrap. Os modais usam
modal-dialog-scrollable. Não se adicionou biblioteca externa.

Labels têm associação explícita; a tabela tem caption, scope e região focável
nomeada. Mensagens usam aria-live; operações usam aria-busy; campos inválidos
usam aria-invalid e aria-describedby. Ativo/Inativo possuem texto. Botões de
linha identificam a conta no nome acessível. Bootstrap fornece foco preso e
Escape; eventos cuidam do foco inicial e retorno ao acionador ou fallback.
Fechamento durante escrita é bloqueado, preservando feedback do resultado.

## Testes e resultados locais

Base: branch `feature/TH-31-interface-alunos`, merge TH-63 `07fedc9`.

| Verificação | Resultado |
|---|---|
| Build aplicação | Aprovado |
| Build testes C++ | Aprovado |
| CTest | 3/3 aprovados |
| auth_integration.py | Aprovado |
| authorization_integration.py | 247 checks HTTP aprovados |
| usuario_integration.py | 359 checks HTTP aprovados |
| perfil_integration.py | 138 checks HTTP aprovados |
| aluno_integration.py | 146 checks HTTP aprovados |
| instrutor_integration.py | 154 checks HTTP aprovados |
| aluno_instrutor_integration.py | 175 checks HTTP aprovados |
| interface_web.py | TH-21/TH-28 HTTP, markup e JavaScript aprovados |
| alunos_interface.py | 386 asserções JS/DOM e 26 requests HTTP aprovados |
| interface_web.py --browser | Falhou antes da navegação: `CDP timeout: Page.enable` |

`alunos_interface.py` usa HTML real, módulos entregues, fetch controlado e DOM
simulado para listagem, join sem N+1, histórico/inativos, inconsistências,
loading/vazio/erro/retry, 401/403, Perfil dinâmico/ausente/inativo, cadastro,
parcial/recuperação, timeout, 409, edição/status e proteção contra submit duplo.
Também verifica XSS em nome/e-mail/confirmação e ordenação de autenticação.
As regressões I1/I2 falharam antes da correção e passaram depois: saída explícita
de pendência inelegível sem escrita, cadastro subsequente de outra conta,
recuperação após falhas de leitura e descarte de seleção antiga após timeout.

IDs 1, 1099511627776, 9007199254740993 e 9223372036854775807 são exercitados
no parser, contexto, domínio, serializer, requests, URLs, Map e comparações.
O teste real HTTP aceita bodies int64 gerados pelo JavaScript em SQLite temporário.
Node ausente faz essa suíte falhar explicitamente; checks críticos nunca são
silenciosamente pulados. Não há npm ou dependência nova instalada pelo teste.

O workflow existente recebeu somente a chamada `python tests/alunos_interface.py`.
Runner, MSYS2, toolchain, vcpkg, build e CMake permanecem preservados.

`interface_web.mjs` foi ampliado para desktop e 375 × 812, navegação direta,
modais, foco/Escape/retorno, cadastro, edição, status, XSS, ausência de N+1,
loading/vazio/erro/retry e overflow. Esses cenários ainda não foram executados
com sucesso: Chrome iniciou DevTools, mas CDP não respondeu a Page.enable.
Não se considera layout, foco real, teclado ou acessibilidade do navegador
validados pelo DOM simulado. Validação visual permanece pendente.

Os testes usam bancos temporários. SHA-256 do banco de desenvolvimento antes
e depois: `8371d9074d2691bfe0008f7844378479023f0c9c1616ff3c30f30564393ba929`.

## Separação TH-33 e revisão

TH-31 não mostra Instrutor, não consulta vínculo por linha e não chama endpoints
TH-30. Seleção, associação, troca e remoção de Instrutor continuam fora do escopo.

Alterações ficam unstaged para revisão. Não foram feitos add, commit, push,
merge ou rebase. Antes da aprovação visual final, executar em ambiente CDP
funcional: `python tests/interface_web.py --browser`.
