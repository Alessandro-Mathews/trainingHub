# TH-25 — Autorização baseada em Perfil

## Escopo e responsabilidades

A TH-24 autentica credenciais e mantém uma sessão no servidor. A TH-25 revalida
essa identidade e decide quais operações ela pode executar. O projeto continua
usando C++20, Drogon 1.9.13, SQLite e sessões; não há JWT, OAuth, SuperAdmin,
permissões persistidas ou ACL dinâmica.

## Papéis e matriz

O único mapeamento de identidade de papel está em `security/Role.h`. A comparação
é exata, sem trim, normalização, aliases ou conversão de caixa:

| Nome em `perfil.nome` | Enum |
|---|---|
| Administrador | `Role::ADMIN` |
| Gestor | `Role::GESTOR` |
| Instrutor | `Role::INSTRUTOR` |
| Aluno | `Role::ALUNO` |

IDs não identificam papéis. `Admin`, `ADMIN`, `admin`, `administrador` e
`Administrador ` são perfis desconhecidos. Perfis não canônicos continuam
existindo e aceitam CRUD, mas recebem `Role::UNKNOWN`, sem acesso às operações
protegidas, inclusive `/api/auth/me`.

| Operação | ADMIN | GESTOR | INSTRUTOR | ALUNO |
|---|---|---|---|---|
| Consultar `/api/auth/me` | Sim | Sim | Sim | Sim |
| Consultar `/api/academias` | Própria academia | Não | Não | Não |
| Consultar `/api/perfis` e `/api/perfis/{id}` | Sim | Sim | Não | Não |
| Criar, alterar ou excluir perfis | Sim | Não | Não | Não |
| Listar e buscar usuários | Próprio tenant | Próprio tenant | Não | Não |
| Criar usuários | Próprio tenant | Próprio tenant | Não | Não |

Logout é público e idempotente. A política de atribuição é independente da
permissão de criar usuários:

| Ator | Papéis que pode atribuir |
|---|---|
| ADMIN | Gestor, Instrutor, Aluno |
| GESTOR | Instrutor, Aluno |
| Demais | Nenhum |

Nenhum ator pode criar um Administrador pela API comum. Atribuição de perfil
ativo desconhecido também retorna `403`. Perfis de destino inexistentes e
inativos mantêm os erros de validação de associação da TH-19 (`404` e `400`).

## Provisionamento reproduzível dos perfis

O projeto já usa migrations SQL explícitas, sem executor automático no startup.
`migrations/002_canonical_profiles.sql` segue essa infraestrutura. Execute-a
depois da criação do schema pela `001_initial_schema.sql`:

```text
sqlite3 CAMINHO_DO_BANCO < migrations/002_canonical_profiles.sql
```

A redireção acima é para shells que suportam `<`. No PowerShell, uma alternativa
com Python é:

```powershell
python -c "import sqlite3,pathlib,sys; c=sqlite3.connect(sys.argv[1]); c.executescript(pathlib.Path('migrations/002_canonical_profiles.sql').read_text(encoding='utf-8')); c.close()" CAMINHO_DO_BANCO
```

O operador deve escolher explicitamente o banco. A implementação e seus testes
não aplicam migrations nem escrevem em `data/traininghub.db`.

O seed insere somente nomes canônicos ausentes. `ON CONFLICT(nome) DO NOTHING`
preserva IDs, descrição e estado de registros existentes. Repetir não duplica
perfis nem reativa registros desativados fora da aplicação. O operador deve
investigar registros canônicos preexistentes antes de colocá-los em uso: a
igualdade exata do nome é a identidade de papel aprovada para esta etapa.

Não há usuário automático, email padrão, senha padrão ou credencial embutida.
O primeiro Administrador de cada academia exige provisionamento local controlado
pelo operador, com academia ativa, perfil canônico ativo e hash produzido pelo
`PasswordHasher` existente. A API comum não é mecanismo de bootstrap. Não exponha
um endpoint temporário nem armazene senha em texto puro para esse processo.

## Proteção dos perfis canônicos

`PerfilService` impede criação de nomes reservados pela API, renomeação de perfil
canônico, exclusão e desativação normal. Também impede transformar perfil não
canônico em papel canônico por renomeação. Essas tentativas retornam `403`.

PUT de perfil canônico pode alterar somente a descrição; deve manter o mesmo
nome exato e `ativo: 1`. A validação de PUT completo continua exigindo nome,
descrição e ativo. Perfis não canônicos mantêm validação, unicidade sensível a
caixa, exclusão protegida por FK e tratamento de conflitos anteriores.

Perfil é um catálogo global, sem `academia_id`, conforme a TH-20. ADMIN gerencia
esse catálogo compartilhado sob as restrições acima. Isso não concede acesso a
usuários ou academias de outros tenants. Não foi criada uma versão por academia
do catálogo de perfis.

## Arquitetura e contexto validado

1. A rota protegida declara `traininghub::security::AuthenticationFilter`.
2. O filtro lê `AuthSession` pela chave `traininghub.auth` da sessão Drogon.
3. `AuthorizationService::validate` usa `AuthContextRepository` assíncrono para
   reconsultar usuário, perfil e academia em um único SELECT com LEFT JOIN.
4. O Repository não seleciona senha, hash, email ou outros dados pessoais.
5. O contexto validado contém os três IDs e `Role`; fica somente nos atributos
   da request, sob `traininghub.validatedAuth`.
6. O Controller chama `AuthorizationGuard::require` com uma `Operation`.
7. O Service de negócio aplica tenant e regras de atribuição. Repository executa
   SQL parametrizado com o tenant validado.

A matriz estática pertence ao `AuthorizationService`, não aos Controllers.
Operação ou papel desconhecido nega acesso por padrão.

O formato persistido na sessão permanece somente:

```text
userId
academiaId
perfilId
```

Revalidação exige usuário ativo, academia ativa, perfil ativo e igualdade entre
os vínculos atuais do usuário e os IDs da sessão. Ausência ou estado inválido de
usuário/academia, IDs inválidos ou vínculos divergentes produzem `401` e removem
o contexto autenticado. Perfil ausente/inativo produz `403`. Falha de consulta ou
conversão produz `500`, sem liberar a execução do handler.

A consulta é por request, sem cache próprio. Ela oferece um snapshot consistente
dos registros; uma request já validada pode terminar se ocorrer revogação durante
sua execução. Não há promessa de cancelamento de operações em andamento.

## Multi-tenancy e mudanças de contrato

ADMIN não é SuperAdmin. ADMIN e GESTOR só operam usuários da academia presente na
sessão revalidada. Não existe parâmetro para escolher outro tenant nem bypass
administrativo.

Os contratos anteriores de usuários continuam exigindo `academia_id`: no body de
POST e na query dos GETs. A entrada deve ser um inteiro positivo de 64 bits e
coincidir com a academia validada. Divergência explícita retorna `403`; o SQL usa
o valor da sessão. A query rejeita ocorrências duplicadas de `academia_id`,
inclusive chaves codificadas, para não aceitar escopo ambíguo. Body de formulário
não substitui o parâmetro de query nos GETs.

Busca por ID usa simultaneamente tenant e ID. Recurso inexistente ou pertencente
a outra academia retorna `404` quando consultado dentro do tenant válido.

`GET /api/academias` antes retornava todas as academias publicamente. Agora exige
ADMIN e preserva o formato array e os campos existentes, mas retorna somente a
própria academia. Sessão de academia inativa ou inexistente recebe `401`.

Todas as rotas existentes de perfis e usuários passam a exigir sessão e papel
permitido. Requisições anônimas recebem `401` antes da validação de negócio.

## HTTP, login e logout

| Status | Situação |
|---|---|
| 400 | Entrada inválida; mantém validações de negócio existentes |
| 401 | Ausência de autenticação válida; usuário/academia ausente ou inativo; vínculos divergentes |
| 403 | Papel sem permissão ou desconhecido; perfil da sessão ausente/inativo; troca explícita de tenant; atribuição proibida; perfil canônico protegido |
| 404 | Recurso inexistente ou fora do tenant válido |
| 409 | Conflitos anteriores de unicidade e FK |
| 500 | Erro interno de banco ou conversão, sem detalhes sensíveis |

`POST /api/auth/login` continua público e verifica senha Argon2 como antes.
Após a verificação da senha, reutiliza a revalidação para impedir login com
usuário, perfil ou academia inexistente/inativo. A resposta de credenciais
inválidas continua genérica e retorna `401`. Falha interna retorna `500`.

Perfil ativo desconhecido pode autenticar credenciais, mas não recebe acesso às
rotas protegidas; `/me` retorna `403`. O login não transforma nomes desconhecidos
em papéis conhecidos.

`GET /api/auth/me` usa exclusivamente o contexto revalidado e retorna somente
`userId`, `academiaId` e `perfilId`. Respostas de autenticação e erros do guard
incluem `Cache-Control: no-store`.

`POST /api/auth/logout` continua público e retorna `200`, mesmo sem sessão ou
com usuário/perfil/academia desativado. Remove a autenticação e solicita rotação
do identificador, preservando o comportamento da TH-24. Drogon 1.9.13 mantém
temporariamente o identificador anterior ligado ao mesmo objeto de sessão;
remover o contexto também remove a autenticação desse objeto compartilhado.

## Rotas públicas e frontend

Continuam públicos login, logout, `/api/health`, `/api/health/database`, `/`,
`/index.html`, CSS, JavaScript, Bootstrap, logo e demais arquivos de `public`.
Nenhum filtro global foi instalado. A configuração de cookies permanece a da
TH-24: sessão em memória, timeout de 1800 segundos, SameSite Strict e defaults
do Drogon para o ambiente HTTP local.

O health de banco mantém `status: error`, `database: disconnected` e HTTP 500 em
falhas, mas sua mensagem pública agora é genérica. Detalhes ficam no log.

TH-25 não implementa TH-28. A interface pública da TH-21 pode receber `401` ou
`403` ao consultar APIs administrativas e já apresenta seu estado genérico de
erro. Na TH-28, `401` deverá indicar autenticação necessária e `403` usuário
autenticado sem permissão. Nenhuma tela de login foi acrescentada.

## Como proteger novos endpoints

Declare o `AuthenticationFilter` no registro da rota. Defina a operação explícita
no enum `Operation` e sua matriz em `AuthorizationService::allows`. No handler,
chame `AuthorizationGuard::require` antes da operação. Obtenha a identidade por
`AuthorizationGuard::context(req)` e passe o tenant validado ao Service.

Se o contrato receber academia do cliente, valide o formato e use
`AuthorizationGuard::tenant` antes de executar a operação com o ID da sessão.
Consultas por recurso devem incluir tenant no WHERE. Não introduza comparações
com IDs fixos ou exceções para ADMIN. Adicione testes negativos de acesso e
cross-tenant junto dos testes de sucesso. Não foram criadas operações de módulos
futuros nesta issue.

## Testes e CI

`authorization_tests.cpp` verifica os nomes exatos, a matriz completa de acesso,
a matriz de atribuição e negação de operação desconhecida.
`authorization_integration.py` inicia servidor e banco novos, aplica o seed duas
vezes e verifica roles com IDs arbitrários/64 bits, matriz HTTP, atribuição,
proteção canônica, tenant, revalidação, login, logout, cookie desconhecido,
expiração, arquivos públicos e falhas de banco sem fail-open.

Os testes TH-19/20 usam atores administrativos autenticados e separados dos
registros sob teste, inclusive nas requisições concorrentes. As validações,
Argon2, IDs de 64 bits, UNIQUE, FK, NULL, PUT completo e falhas de banco continuam
cobertos. A listagem vazia de academia deixou de ser um estado válido para um
ator autenticado: academia ausente/inativa agora invalida a sessão.

O teste TH-21 preserva HTTP real e arquivos públicos; usa ADMIN para consultar
somente sua academia. O teste opcional de navegador recebe um cookie real via
CDP. Casos de renderização de lista vazia, campos NULL e academia inativa usam
respostas controladas no navegador, sem criar bypass na API.

Todos os testes HTTP usam SQLite temporário e verificam que o hash do banco local
não mudou. A CI preserva CTest e os quatro scripts anteriores e acrescenta
`authorization_integration.py`.

Com o ambiente Windows/MSYS2 e builds configurados:

```text
cmake --build build --parallel 2
cmake --build build/security-tests --parallel 2
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python tests/authorization_integration.py
python tests/auth_integration.py
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/interface_web.py
git diff --check
```

Navegador opcional: `python tests/interface_web.py --browser`, com Chrome/Chromium
funcional e Node 22+. `TH21_CHROME` seleciona outro executável instalado.
A limitação ambiental de `CDP timeout: Page.enable` já registrada na TH-21 pode
impedir essa validação antes da navegação. Não equivale a aprovação do teste UI.

### Validação local em 2026-11-02

- Build da aplicação e dos testes: aprovado.
- CTest: 3/3 (`authorization`, `security`, `sqlite_foreign_keys`).
- `authorization_integration.py`: 221 verificações HTTP aprovadas.
- `usuario_integration.py`: 149 verificações HTTP aprovadas.
- `perfil_integration.py`: 138 verificações HTTP aprovadas.
- `auth_integration.py` e `interface_web.py` sem browser: aprovados.
- Bancos temporários isolados; verificações de hash confirmaram banco local intacto.
- Navegador opcional: tentou executar, mas falhou em `CDP timeout: Page.enable`,
  antes da navegação e das novas verificações de autenticação. Essa falha já
  estava registrada na documentação da TH-21.
