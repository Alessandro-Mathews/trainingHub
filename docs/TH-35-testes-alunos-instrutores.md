# TH-35 — Testes dos módulos de Alunos, Instrutores e relacionamento

## Objetivo e escopo

A TH-35 consolida a cobertura automatizada dos fluxos principais de Aluno,
Instrutor e seu relacionamento. A auditoria da base `b5e2e50` identificou cobertura
existente para os nove critérios de aceite. Esta entrega reutiliza essas provas,
acrescenta reforços pontuais nas suítes responsáveis e registra sua rastreabilidade.

Não cria uma suíte geral, endpoints, regras de negócio, permissões, migrations ou
alterações de interface. As matrizes completas da TH-26, TH-27, TH-30, TH-34 e
TH-63 continuam nas suítes originais. O workflow existente já executa os arquivos
alterados e não precisa de modificação.

## Suítes reutilizadas

| Suíte | Responsabilidade relevante |
|---|---|
| [aluno_integration.py](../tests/aluno_integration.py) | Cadastro, listagem, detalhe, elegibilidade, int64, tenant, histórico, contratos, concorrência de criação e FK de Aluno |
| [instrutor_integration.py](../tests/instrutor_integration.py) | Cadastro, listagem, detalhe, elegibilidade, int64, tenant, histórico, duplicidade concorrente e FK de Instrutor |
| [aluno_instrutor_integration.py](../tests/aluno_instrutor_integration.py) | Definição, consulta, substituição, idempotência, histórico, concorrência, tenant e integridade do vínculo |
| [alunos_instrutores_authorization_integration.py](../tests/alunos_instrutores_authorization_integration.py) | TH-34: oito rotas, papéis, tenant bidirecional, revogação, sessão e snapshots de rejeições |
| [usuario_integration.py](../tests/usuario_integration.py) | TH-19/TH-63: cadastro da conta, edição, status, persistência, login e preservação das entidades especializadas |
| [authorization_integration.py](../tests/authorization_integration.py) | Permissões de Usuario, atribuição de perfil, tenant, revalidação e expiração |
| [auth_integration.py](../tests/auth_integration.py) | Login, sessão, logout, cookies, credenciais e revalidação de Usuario/Perfil/Academia |
| [alunos_interface.py](../tests/alunos_interface.py) | JavaScript/DOM e HTTP real de cadastro, consulta, edição, status e recuperação de Aluno |
| [instrutores_interface.py](../tests/instrutores_interface.py) | JavaScript/DOM e HTTP real de cadastro, consulta, edição, status e histórico de Instrutor |
| [aluno_instrutor_interface.py](../tests/aluno_instrutor_interface.py) | JavaScript/DOM do vínculo: seleção, histórico, int64, XSS, double-submit, reconciliação e respostas atrasadas |
| [authorization_tests.cpp](../tests/authorization_tests.cpp) | Matriz central de operações e atribuição de perfis; nomes canônicos |
| [security_tests.cpp](../tests/security_tests.cpp) | Argon2id, preservação da senha e comportamento de sessão nula |
| [sqlite_foreign_keys_tests.cpp](../tests/sqlite_foreign_keys_tests.cpp) | FKs e busy timeout nas seis conexões de dois pools SQLite em memória |

[interface_web.py](../tests/interface_web.py) complementa autenticação, contratos
HTTP e assets. Sua variante `--browser` executa [interface_web.mjs](../tests/interface_web.mjs)
para provas de navegador, layout, teclado e foco; ela é separada do gate atual.

## Matriz de rastreabilidade

| Critério TH-35 | Suíte(s) | Comportamento comprovado |
|---|---|---|
| Cadastro | aluno_integration, instrutor_integration, usuario_integration, alunos_interface, instrutores_interface | Criar conta e entidade especializada; verificar resposta, leitura, persistência e duplicidade |
| Consulta | aluno_integration, instrutor_integration, aluno_instrutor_integration, TH-34 | Listas vazias/múltiplas, detalhe correto, responsável nulo/existente, histórico e recursos indisponíveis |
| Atualização | usuario_integration, alunos_interface, instrutores_interface, aluno_instrutor_integration | Nome/email e status da conta associada; alteração do responsável; persistência e campos preservados |
| Validações | aluno_integration, instrutor_integration, aluno_instrutor_integration, usuario_integration | Contratos JSON, tipos, campos, IDs positivos int64, elegibilidade e duplicidade |
| Relacionamento Aluno–Instrutor | aluno_instrutor_integration, aluno_instrutor_interface, usuario_integration | Definir, consultar, substituir, repetir, preservar histórico e integridade; concorrência e ausência de unlink |
| Isolamento entre academias | TH-34, suítes de domínio, usuario_integration, authorization_integration | Listagens filtradas, alvos externos ocultos/rejeitados e escritas condicionadas pelo tenant |
| Autorização | TH-34, authorization_integration, usuario_integration, authorization_tests.cpp | Operações permitidas por papel, acesso próprio negado quando aplicável, sessão e revalidação |
| Cenários de erro | Suítes de domínio, TH-34, usuario_integration, auth_integration, authorization_integration | 400/401/403/404/409/500 conforme o contrato; respostas seguras e preservação do estado verificado |
| Banco de testes isolado | Fixtures das suítes HTTP, sqlite_foreign_keys_tests.cpp e comparação SHA-256 | SQLite/configuração/servidor temporários, migrations no fixture, teardown e banco persistente preservado |

## Cadastro, consulta e validações

| Fluxo | Endpoint | Provas principais |
|---|---|---|
| Cadastrar Aluno | `POST /api/alunos` | `usuario_id` elegível, resposta 201, duplicidade 409 e ausência de criação em rejeições verificadas |
| Cadastrar Instrutor | `POST /api/instrutores` | Mesmo contrato especializado, exigindo perfil exatamente Instrutor |
| Listar/detalhar Aluno | `GET /api/alunos`, `GET /api/alunos/{id}` | Conteúdo exato, lista vazia/múltipla, histórico, tenant e recurso inexistente |
| Listar/detalhar Instrutor | `GET /api/instrutores`, `GET /api/instrutores/{id}` | Conteúdo exato, histórico independente do perfil atual e isolamento |
| Consultar responsável | `GET /api/alunos/{alunoId}/instrutor` | ID persistido ou null; vínculo órfão/externo retorna 404 |

Os POSTs especializados aceitam somente `usuario_id` inteiro positivo até
`9223372036854775807`. JSON inválido, campos ausentes/extras, strings, booleanos,
floats, zero, negativos e overflow são rejeitados. Consultas não aceitam query ou
body. O tenant vem da sessão validada, não do payload.

Novo cadastro exige Usuario ativo, Perfil ativo e nome canônico correspondente.
Usuario externo/inexistente retorna 404; alvo inelegível retorna 400; cadastro
duplicado elegível retorna 409. Leituras administrativas preservam os registros
históricos após mudança de atividade ou perfil do alvo.

O reforço TH-35 envia `{"usuario_id":202}` com `Content-Type: text/plain`, usando
sessão ADMIN e conta elegível ainda sem cadastro. Ambos os POSTs retornam 400.
Snapshots completos da tabela especializada comprovam ausência de criação ou
alteração. O cadastro válido posterior da mesma conta permanece na suíte, como
controle positivo. Os controllers não foram modificados.

## Atualização do cadastro associado

| Alteração | Endpoint real | Cobertura |
|---|---|---|
| Nome/email | `PUT /api/usuarios/{usuario_id}` | TH-63 verifica valores no SQLite, resposta pública e preservação dos campos protegidos |
| Desativação/reativação | `PUT /api/usuarios/{usuario_id}/status` | TH-63 verifica persistência, idempotência, login e invalidação da sessão utilizada durante a inatividade |
| Responsável | `PUT /api/alunos/{alunoId}/instrutor` | TH-30 verifica resposta, SQLite e consulta posterior |

Não existem `PUT /api/alunos/{id}` ou `PUT /api/instrutores/{id}`. A interface
edita a conta associada pelo `Usuario.id`, não pelo ID da entidade especializada.
O vínculo usa `Aluno.id` no path e `Instrutor.id` no body.

O bloco `management_checks` de `usuario_integration.py` inclui Usuarios associados
a Aluno e Instrutor, com vínculo existente. Verifica edição, desativação/reativação,
preservação das tabelas especializadas e do responsável. Também cobre email
duplicado, Usuario externo, autodesativação, autorização, sessão, tenant e payload
inválido. As duas suítes de interface comprovam o consumo desses endpoints.

## Relacionamento, concorrência e ausência de unlink

O contrato permite zero ou um responsável por Aluno e vários Alunos por Instrutor.
GET retorna `{"instrutor_id":null}` quando não há responsável. PUT define ou
substitui o responsável e retorna 200, inclusive ao repetir o mesmo Instrutor.

A suíte TH-30 já verifica elegibilidade dos dois alvos, perfis incorretos/inativos,
Usuarios inativos, recursos externos/inexistentes, histórico e vínculos
inconsistentes. Nove cenários existentes exercitam perda de elegibilidade durante
uma escrita bloqueada. Também há provas de FK RESTRICT e rollback após perda de FK.

O novo cenário `concurrent_replace` parte de um responsável X e dispara dois PUTs
para Y e Z, ambos válidos, no mesmo Aluno. Usa duas sessões independentes e uma
`threading.Barrier(2)`, sem novos sleeps. As duas respostas devem ser 200 e conter
o ID solicitado. Depois da conclusão de ambas, GET e SQLite devem concordar sobre
um dos IDs confirmados. A prova também verifica tenant dos dois lados, FKs,
preservação dos demais vínculos, dos dados do Aluno e da tabela de Instrutores.
Depois das verificações, restaura X pela API para preservar a fixture do cenário
posterior de perda de FK, sem deixar uma referência adicional ao Instrutor 1.

Não existe optimistic locking ou vencedor fixo: as escritas válidas podem
serializar, e a última efetivada determina o valor final. O helper `put`, que
compara SQLite imediatamente após cada request, não é usado pelos concorrentes:
outro PUT pode legitimamente substituir o valor antes daquela leitura.

Não existe operação de unlink. Null no PUT já é rejeitado. Um probe com sessão
autorizada confirmou que `DELETE /api/alunos/{alunoId}/instrutor` retorna 404 HTML
do Drogon 1.9.13. O novo teste fixa o status 404, verifica segurança da resposta,
compara o snapshot dos vínculos e confirma o mesmo responsável por GET. A resposta
do framework é verificada separadamente do helper de contratos JSON de negócio.

### Corrida de elegibilidade no cadastro de Instrutor: limite documentado

Não foi adicionado um teste específico para a janela entre validação no Service
e INSERT no Repository. O teste equivalente de Aluno mantém um writer lock e usa
`time.sleep(0.3)` antes do commit; ele aceita 400/409 ou 404/409 conforme a mudança.
O sleep não comprova que o SELECT de elegibilidade ocorreu antes do commit.

Os mecanismos disponíveis na fixture não fornecem um sinal de conclusão daquele
SELECT. Uma barreira ou Event no cliente comprovaria apenas o início da request,
não a passagem pela validação interna. Copiar o sleep ou exigir 409 adicionaria
dependência de timing. Um teste que aceitasse a validação anterior ao INSERT
rejeitando o alvo não provaria especificamente a revalidação da escrita.

Por isso, esta entrega não apresenta essa corrida como nova prova automatizada.
O INSERT condicionado existente foi inspecionado, mas essa inspeção não substitui
o teste ausente. Permanecem as provas de elegibilidade, duplicidade concorrente,
rollback por perda de FK e isolamento. Uma prova determinística dessa janela
exige mecanismo de observação/sincronização apropriado, fora desta alteração
restrita a testes e documentação. Nenhuma alteração de produção foi feita.

## Isolamento e autorização reutilizados

[TH-34](TH-34-autorizacao-alunos-instrutores.md) é a referência para as oito rotas
administrativas. Sua suíte executa 865 verificações HTTP, 14 matrizes completas e
768 rejeições com snapshots preservados. ADMIN/GESTOR operam no próprio tenant;
INSTRUTOR/ALUNO/UNKNOWN não recebem acesso administrativo por possuir entidade
especializada. Sessão, revogação e precedência da autorização sobre parsing também
estão cobertas.

A mesma suíte verifica listagens exatas, recursos externos/inexistentes
indistinguíveis e tentativas de injeção de `academia_id`/`academiaId` em ambos os
sentidos A/B. TH-63 e `authorization_integration.py` complementam edição/status de
Usuario externo. Esta entrega não replica essas matrizes. A verificação de tenant
do novo cenário concorrente é apenas uma invariante daquela escrita.

## Cenários de erro e efeitos colaterais

| HTTP | Escopo real | Suítes de referência |
|---|---|---|
| 400 | Contrato, Content-Type incompatível, ID inválido, alvo inelegível, nome/email/status inválido | Aluno, Instrutor, vínculo e Usuario |
| 401 | Sessão ausente/inválida/expirada, logout, Usuario do ator ou Academia inativos | TH-34, autenticação, autorização e Usuario |
| 403 | Papel proibido, Perfil do ator inativo e autodesativação | TH-34, autorização e Usuario |
| 404 | Recurso externo/inexistente; responsável inconsistente; DELETE não registrado | Domínio, TH-34 e Usuario; DELETE tem resposta do framework |
| 409 | Duplicidade de entidade/email, perda de FK ou conflito da escrita condicionada | Aluno, Instrutor, vínculo e Usuario |
| 500 | Falha controlada de schema, banco ou conversão | Suítes de domínio, autenticação, autorização e Usuario |

Não se exige cada status em cada endpoint. Duas substituições válidas concorrentes
retornam 200; esse teste não inventa conflito 409.

As respostas são verificadas contra exposição de credenciais e detalhes internos.
TH-34 compara entidades e identidade dos Usuarios; vínculo compara relacionamentos;
TH-63 compara o Usuario alvo e, em cenários específicos, as tabelas especializadas.
Triggers existentes verificam rollback de alterações referenciais. Os novos casos
de Content-Type e DELETE acrescentam comparação explícita do estado relevante.

## Banco isolado e execução

Cada suíte HTTP cria SQLite, configuração, log e servidor temporários sob `build/`.
O `filename` da configuração aponta para a fixture e o processo recebe esse
diretório como `cwd`. O backend não aplica migrations automaticamente no banco
persistente. As fixtures aplicam explicitamente as migrations do seu escopo:

| Suíte | Migrations |
|---|---|
| Aluno | 001–003 |
| Instrutor | 001–004 |
| Vínculo | 001–005, verificando preservação ao aplicar 005 |
| Usuario | 001 inicialmente; 002–005 para TH-63 |
| TH-34 e interfaces Aluno/Instrutor | Todas as migrations atuais |
| Autenticação / autorização | 001 / 001–002 |

As portas são obtidas por bind em `127.0.0.1:0`. Os processos são encerrados e
aguardados no teardown; as suítes de domínio possuem fallback de kill. As conexões
Python de corrupção deliberada pertencem somente à fixture. O teste C++ usa
`:memory:` para verificar foreign keys e busy timeout por conexão.

Antes e depois das regressões, comparar SHA-256 de `data/traininghub.db`. A base
auditada possui o hash abaixo; a propriedade essencial é a igualdade antes/depois,
mesmo que o banco legítimo de outro ambiente tenha conteúdo diferente:

```text
10C935F52AD5FEADA7F2C25D9257CCBB01CC076D7AFD1306518C98F5970BABA8
```

Com binários compilados e DLLs no PATH, executar:

```text
python -B tests/aluno_integration.py
python -B tests/instrutor_integration.py
python -B tests/aluno_instrutor_integration.py
python -B tests/alunos_instrutores_authorization_integration.py
python -B tests/usuario_integration.py
python -B tests/authorization_integration.py
python -B tests/auth_integration.py
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python -B tests/alunos_interface.py
python -B tests/instrutores_interface.py
python -B tests/aluno_instrutor_interface.py
```

No Windows/MSYS2 UCRT64, usar Python real, `PYTHONUTF8=1` e os diretórios de DLLs
no PATH. `-B` evita arquivos de bytecode. Não executar `--browser` apenas para
aumentar o volume de regressões: ele também grava screenshots em diretório fixo.

## Validação desta entrega

Regressões executadas em 26/11/2026, usando os binários locais existentes e Python
MSYS2 UCRT64 com `-B`. Nenhuma recompilação foi necessária para as alterações de
teste. Todos os comandos abaixo concluíram com sucesso:

| Suíte | Resultado |
|---|---|
| Aluno | 147 verificações HTTP |
| Instrutor | 155 verificações HTTP |
| Vínculo, incluindo restauração da fixture após concorrência | 212 verificações HTTP |
| TH-34 | 865 verificações HTTP; 14 matrizes; 768 rejeições com snapshots |
| Usuario/TH-63 | 379 verificações HTTP |
| Authorization | 247 verificações HTTP |
| Auth | Regressões HTTP e verificação de segurança aprovadas |
| CTest | 3/3: authorization, security e sqlite_foreign_keys |
| Interface Aluno | 386 asserções JS/DOM; 26 chamadas HTTP |
| Interface Instrutor | 473 asserções JS/DOM; 42 chamadas HTTP |
| Interface vínculo | 257 asserções JS/DOM; oito mutantes existentes rejeitados em memória |

O SHA-256 externo de `data/traininghub.db`, antes e depois de todos os testes,
foi idêntico ao hash registrado acima. O navegador não foi executado. A verificação
`git diff --check` passou; staging permaneceu vazio. Não houve alteração de backend,
frontend funcional, migrations ou CI.

## Limitações e CI

- O navegador não é gate do CI. Os testes JS/DOM usam doubles para DOM/fetch e não
  comprovam layout, APIs de acessibilidade ou comportamento completo do navegador.
- Existe fluxo integrado na variante de navegador, mas não uma única prova HTTP
  dos doze passos da auditoria sobre o mesmo agregado recém-criado. Isso não é um
  requisito adicional dos nove critérios nem motivo para duplicar as suítes.
- Versões de migrations por suíte são intencionais e adequadas ao escopo; TH-34 e
  interfaces também exercitam o schema completo atual.
- Snapshots comprovam somente o estado consultado em cada cenário. Não demonstram
  ausência de todo efeito imaginável em toda falha interna.
- Existe uma janela entre liberar a porta reservada e iniciar o servidor. Algumas
  suítes de interface não têm fallback de kill; algumas verificações SHA internas
  não ficam em finally. A comparação externa antes/depois complementa essa prova.
- Os cenários antigos de corrida que usam sleeps não foram reescritos nesta TH.
  A corrida específica de elegibilidade de Instrutor permanece sem prova controlada
  da janela entre SELECT e INSERT, conforme justificativa acima.
- Os reforços executam nas três suítes já listadas em
  [ci.yml](../.github/workflows/ci.yml). Não há nova suíte geral, nova matriz de
  autorização/tenant ou alteração do workflow.
