# TH-34 — Autorização dos endpoints de Alunos e Instrutores

## Objetivo e escopo

A TH-34 consolida e comprova a política já implementada pela TH-25, TH-26, TH-27 e
TH-30. Esta entrega acrescenta uma suíte HTTP dedicada, esta documentação e sua
execução no CI. Não modifica backend, frontend, migrations, guards ou permissões.

ADMIN e GESTOR podem administrar os recursos da própria academia. INSTRUTOR,
ALUNO e UNKNOWN não podem executar as oito operações administrativas abaixo.
O ticket não amplia essas permissões nem introduz self-access.

Frontend não é barreira de segurança. O backend é a autoridade de autorização,
tenant e elegibilidade, independentemente de botões ou validações da interface.

## Arquitetura e sessão

As oito rotas declaram `AuthenticationFilter`. A sessão no servidor mantém
`AuthSession` com `userId`, `academiaId` e `perfilId`; não recebe Role do frontend.

A cada request protegido, `AuthContextRepository` consulta Usuario, Academia e
Perfil atuais. `AuthorizationService::validate` verifica atividade, existência e
correspondência da identidade atual com a sessão. A Role deriva do nome atual do
Perfil. O resultado é publicado como `ValidatedAuthContext` nos atributos do request.

O controller usa `AuthorizationGuard::require` antes do parsing de contrato. O
service também consulta a matriz central usando o contexto validado. Isso protege
as duas camadas sem manter políticas divergentes. Os repositories recebem a academia
do contexto e a aplicam no SQL, sem busca global seguida de filtro no frontend.

Sessão ausente, cookie desconhecido, expiração e logout resultam em 401. Logout
remove a identidade e rotaciona o ID da sessão. Perfil atual inativo ou Role sem
permissão resulta em 403. A validação não congela permissões no momento do login.

## Perfis canônicos

| Nome exato em `perfil.nome` | Role |
|---|---|
| Administrador | ADMIN |
| Gestor | GESTOR |
| Instrutor | INSTRUTOR |
| Aluno | ALUNO |

A comparação é exata e sensível a caixa. Não há aliases, trim ou IDs mágicos.
Por exemplo, `Administrador ` é UNKNOWN, mesmo quando está ativo. O fluxo atual
pode estabelecer sessão para esse Perfil; as operações administrativas continuam
negadas com 403.

IDs de Perfil servem para identidade e associação, não para determinar permissão.
A fixture TH-34 usa Aluno com ID 1, Administrador com 4294967297, Gestor com
1099511627793 e Instrutor com 37. O seed canônico preserva esses IDs.

## Oito rotas e matriz

`P` significa permitido no tenant autenticado. `N` significa negado com 403 para
sessão válida. Sem sessão válida, qualquer linha resulta em 401.

| Método e path | Operation | ADMIN | GESTOR | INSTRUTOR | ALUNO | UNKNOWN |
|---|---|---|---|---|---|---|
| GET `/api/alunos` | AlunosRead | P | P | N | N | N |
| GET `/api/alunos/{id}` | AlunosRead | P | P | N | N | N |
| POST `/api/alunos` | AlunosCreate | P | P | N | N | N |
| GET `/api/instrutores` | InstrutoresRead | P | P | N | N | N |
| GET `/api/instrutores/{id}` | InstrutoresRead | P | P | N | N | N |
| POST `/api/instrutores` | InstrutoresCreate | P | P | N | N | N |
| GET `/api/alunos/{alunoId}/instrutor` | AlunosInstrutorRead | P | P | N | N | N |
| PUT `/api/alunos/{alunoId}/instrutor` | AlunosInstrutorManage | P | P | N | N | N |

Não há self-access: Aluno consultando seu próprio `Aluno.id` recebe 403. Instrutor
consultando seu próprio `Instrutor.id` também recebe 403. Existência do registro
especializado não concede permissão. As fixtures usam registros próprios existentes
e IDs distintos entre Usuario, Aluno e Instrutor, sem substituir autorização por 404.

## Tenant e criação

`ValidatedAuthContext.identity.academiaId` é a única autoridade para academia.
ADMIN não possui bypass global. Aluno e Instrutor pertencem à academia do Usuario
associado; não possuem tenant independente informado pelo cliente.

Listagens aplicam tenant no SQL e retornam somente registros da academia autenticada.
Detalhes externos e inexistentes recebem o mesmo 404 genérico. A suíte verifica
conteúdo das listagens e igualdade das respostas de erro em ambos os sentidos A/B,
para ADMIN e GESTOR.

POST Alunos e Instrutores aceitam somente `{"usuario_id":123}`. O valor representa
`Usuario.id`. O Usuario precisa existir no tenant, estar ativo e possuir Perfil
ativo exatamente Aluno ou Instrutor, conforme o cadastro. Usuario externo não é
criado, transferido ou reutilizado entre academias: recebe 404. Duplicidade elegível
recebe 409; perfil alvo incorreto recebe 400.

As escritas existentes revalidam tenant e elegibilidade no SQL condicionado. A TH-34
não altera essa implementação nem replica seus testes completos de concorrência.

## Vínculo Aluno–Instrutor

O path usa `Aluno.id`. GET retorna 200 com `instrutor_id` ou null, sem query/body.
PUT aceita somente `{"instrutor_id":123}`, usando `Instrutor.id`, nunca Usuario.id.
Não aceita tenant, null ou DELETE. Sucesso do PUT retorna 200 com o ID persistido.

Ambos os alvos precisam pertencer ao tenant autenticado. Aluno externo, Instrutor
externo e recurso inexistente não podem ser usados para contornar o contexto. GET
administrativo mantém a leitura histórica conforme TH-30; autorização do ator é
independente da elegibilidade atual do registro alvo.

## Academia maliciosa e precedência

Os oito endpoints não aceitam query. GET também não aceita body. POST e PUT aceitam
somente os campos documentados. Assim, `academia_id` e `academiaId` em query ou body
recebem 400 para ADMIN/GESTOR, sem trocar o tenant da operação.

A autenticação/autorização precede validação de payload: os mesmos inputs recebem
401 sem sessão e 403 para Role sem permissão. A suíte também envia JSON malformado
nessas matrizes para comprovar que parsing não substitui a decisão de acesso.

## Revogação após login

Cada cenário usa oito sessões de Gestor independentes, criadas antes da alteração.
Uma sessão é destinada a cada rota. Isso evita que o primeiro 401, que limpa a
sessão, mascare falta de revalidação nas outras sete rotas.

| Mudança na fixture após login | Próxima chamada em cada rota |
|---|---|
| Trocar `Usuario.perfil_id` para Aluno | 401 |
| Desativar o Perfil atual | 403 |
| Desativar o Usuario | 401 |
| Desativar a Academia | 401 |
| Alterar nome do Perfil para desconhecido, mantendo o ID | 403 |

As alterações SQL simulam revogação externa somente no banco temporário e são
restauradas entre cenários. Não acrescentam endpoints de transferência ou edição
de perfil ao produto. Logout e expiração também são testados nas oito rotas, com
sessões independentes. Somente a fase de expiração reinicia o servidor com timeout
de dois segundos e aguarda sua expiração; demais matrizes mantêm o timeout normal.

## HTTP status

| Status | Significado neste contrato |
|---|---|
| 200 | Consulta ou definição/alteração permitida |
| 201 | Criação permitida |
| 400 | Contrato inválido ou alvo inelegível |
| 401 | Sessão ausente/inválida/expirada, logout ou identidade revogada |
| 403 | Role sem permissão ou Perfil do ator inativo/desconhecido |
| 404 | Recurso inexistente ou indisponível no tenant |
| 409 | Duplicidade/conflito quando aplicável |
| 500 | Falha interna controlada; cobertura específica permanece nas suítes anteriores |

Erros preservam objetos genéricos `erro` ou `message`. A suíte não aceita exposição
de credenciais ou detalhes de banco e não usa status 404 como substituto de 403.

## Testes e provas de segurança

Execute, com aplicação/testes C++ previamente compilados e DLLs no PATH:

```text
python tests/alunos_instrutores_authorization_integration.py
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python tests/authorization_integration.py
python tests/auth_integration.py
python tests/aluno_integration.py
python tests/instrutor_integration.py
python tests/aluno_instrutor_integration.py
```

A suíte TH-34 inicia servidor real em porta livre com SQLite, configuração e log
temporários sob `build/`. Aplica migrations somente à fixture. Antes/depois de cada
request esperado como rejeitado, compara Alunos, Instrutores e identidade/tenant/
atividade dos Usuarios. Isso inclui 400, 401, 403, 404 e 409, inclusive escritas negadas.
O SHA-256 de `data/traininghub.db` é comparado antes/depois, inclusive em falhas.

São 14 matrizes completas das oito rotas: ADMIN, GESTOR, INSTRUTOR, ALUNO, UNKNOWN,
sem sessão, cookie inválido, logout, expiração e os cinco cenários de revogação.
A suíte verifica conteúdo permitido, não apenas o código de sucesso. Não substitui
`authorization_tests.cpp`, que mantém a matriz central de cinco Roles por Operation.

Não há mutação automática de fontes C++: essa abordagem exigiria editar/copiar e
recompilar produção, ampliando o escopo desta entrega. As seguintes provas HTTP
estruturadas cobrem os comportamentos que mutações de segurança tentariam violar:

| Defeito representativo | Prova comportamental |
|---|---|
| A — ausência de proteção de sessão | Oito rotas exigem 401 sem sessão/cookie válido e após logout/expiração |
| B — permitir INSTRUTOR | Oito rotas exigem 403, incluindo Instrutor próprio existente |
| C — permitir ALUNO | Oito rotas exigem 403, incluindo Aluno próprio existente |
| D — confiar em academia do cliente | Snake/camel em query/body, rejeição e snapshots sem escrita |
| E — remover isolamento | Listagens exatas e recursos externos/inexistentes equivalentes em ambos os sentidos |
| F — permitir UNKNOWN | Perfil ativo não canônico estabelece sessão, mas recebe 403 nas oito rotas |
| G — usar IDs mágicos de Perfil | Aluno com ID 1 e administradores com IDs maiores que 32 bits |
| H — congelar Perfil no login | Cinco alterações após login, com uma sessão independente por rota |

Essas provas verificam o comportamento externo; não afirmam matar todo mutante
possível de cada camada redundante. Remover apenas um guard pode ser neutralizado
por outra camada. Corridas entre validação e escrita condicionada permanecem nas
suítes TH-26/TH-30. A TH-34 não duplica schema, Argon2, int64 ou validação visual.

## CI e limitações

CI acrescenta somente `python tests/alunos_instrutores_authorization_integration.py`
ao bloco existente de integrações. Não remove testes nem altera infraestrutura.

A revalidação ocorre por request, sem garantia de revogação transacional de uma
operação já iniciada. A suíte não cria política nova para INSTRUTOR/ALUNO, não
implementa self-access e não modifica as interfaces TH-31/32/33. Qualquer ampliação
de permissões exige decisão funcional explícita fora desta consolidação.
