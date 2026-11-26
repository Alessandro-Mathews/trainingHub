# TH-36 — Gestão de Planos

## Objetivo e arquitetura

Gerenciar os planos oferecidos por cada academia, com criação, consulta,
atualização e ativação/desativação. O módulo reutiliza C++20, Drogon ORM,
SQLite, sessões e a política central de autorização.

O caminho de cada operação é:

```text
HTTP → AuthenticationFilter → AuthorizationService::validate
     → ValidatedAuthContext → PlanoController → PlanoService
     → PlanoRepository → SQLite
```

O filtro revalida Usuario, Perfil e Academia. O Controller aplica a Operation
antes de interpretar o contrato. O Service recebe o contexto validado, repete
a autorização, valida o domínio e extrai o tenant. O Repository recebe IDs e
dados, executa SQL parametrizado e não conhece HTTP, sessão ou Role.

As respostas JSON são construídas somente no Controller. Os callbacks são
assíncronos, seguindo os módulos existentes. O model é header-only; não existe
`Plano.cpp`. O DTO `DadosPlano` expõe somente os quatro campos editáveis.

## Model e persistência

| JSON / SQLite | Campo C++ em Plano | Tipo e regra |
|---|---|---|
| `id` | `id` | INTEGER PK AUTOINCREMENT / int64; gerado, positivo e imutável |
| `academia_id` | `academiaId` | INTEGER NOT NULL / int64; FK e tenant do contexto |
| `nome` | `nome` | TEXT NOT NULL / string; não vazio ou somente whitespace ASCII |
| `descricao` | `descricao` | TEXT nullable / optional string; string, null ou omissão |
| `valor_centavos` | `valorCentavos` | INTEGER NOT NULL / int64; centavos inteiros, mínimo zero |
| `duracao_dias` | `duracaoDias` | INTEGER NOT NULL / int64; duração positiva em dias |
| `ativo` | `ativo` | INTEGER 0/1 / bool; nasce true |
| `criado_em` | `criadoEm` | DATETIME / string; DEFAULT CURRENT_TIMESTAMP, imutável |

Nome e descrição válidos são preservados, incluindo Unicode, espaços e descrição
vazia. Não há trim, normalização de caixa ou limites comerciais novos. O nome
rejeita vazio e conteúdo formado somente por `" \t\r\n\f\v"`, como Usuario.

Preço é armazenado em centavos, sem float/double. Zero representa plano gratuito.
Duração tem unidade explícita em dias. Os dois campos aceitam até
`9223372036854775807`; preço negativo e duração zero/negativa são inválidos.

A migration [006_plano.sql](../migrations/006_plano.sql) cria a tabela, a constraint
`UNIQUE(academia_id,nome)`, a FK com `ON DELETE RESTRICT ON UPDATE RESTRICT` e o
índice `idx_plano_academia_id`. CHECKs protegem atividade 0/1, valor não negativo
e duração positiva. Os CHECKs numéricos também exigem armazenamento do tipo integer:
a afinidade INTEGER do SQLite, sozinha, permitiria persistir valores REAL.

Mesmo nome exato na mesma academia gera 409. Mesmo nome em academias diferentes
é permitido. A comparação usa a collation padrão do SQLite, sensível a caixa.
A constraint UNIQUE é a proteção final sob concorrência, sem depender de SELECT
prévio. Todas as cinco queries usam tenant; operações por ID incluem o tenant no
próprio WHERE. Escritas usam RETURNING e projeção explícita dos oito campos.

## Endpoints e contratos

| Método e endpoint | Operation | Entrada | Sucesso |
|---|---|---|---|
| POST `/api/planos` | PlanosManage | Dados editáveis | 201, Plano completo |
| GET `/api/planos` | PlanosRead | Sem query/body | 200, array direto |
| GET `/api/planos/{id}` | PlanosRead | ID positivo int64; sem query/body | 200, Plano completo |
| PUT `/api/planos/{id}` | PlanosManage | ID e todos os dados obrigatórios editáveis | 200, Plano completo |
| PUT `/api/planos/{id}/status` | PlanosManage | ID e somente ativo boolean | 200, Plano completo |

POST e PUT de dados aceitam exatamente `nome`, `valor_centavos`, `duracao_dias`
e, opcionalmente, `descricao`:

```json
{
  "nome": "Mensal",
  "descricao": "Plano mensal da academia",
  "valor_centavos": 9990,
  "duracao_dias": 30
}
```

Descrição omitida ou null é persistida como NULL. PUT é completo para os campos
obrigatórios; omitir descrição no PUT substitui a descrição anterior por NULL.
Não existe PATCH. PUT preserva ID, tenant, atividade e data de criação.

Status aceita somente:

```json
{"ativo": false}
```

Reativar usa true. Repetir dados ou status válidos retorna 200. A alteração de
status preserva todos os demais campos. Não há proteção de autodesativação de
Plano: essa regra pertence exclusivamente ao módulo Usuario.

Resposta pública consistente:

```json
{
  "id": 42,
  "academia_id": 1,
  "nome": "Mensal",
  "descricao": "Plano mensal da academia",
  "valor_centavos": 9990,
  "duracao_dias": 30,
  "ativo": true,
  "criado_em": "2026-11-26 12:00:00"
}
```

O timestamp é ilustrativo; a API preserva o texto gerado pelo SQLite. Descrição
NULL sempre aparece como `"descricao":null`. Valores int64 são números JSON,
conforme o contrato aprovado. Todas as respostas das cinco rotas, incluindo erros,
usam `Cache-Control: no-store`.

Listagem retorna somente o tenant atual, ordenada por ID, incluindo ativos e
inativos; sem registros retorna `[]`. Plano inativo continua consultável e editável
administrativamente. Não existem filtros, paginação, ordenação configurável ou DELETE.

## Autorização e isolamento

`PlanosRead` e `PlanosManage` foram acrescentadas ao final de Operation, preservando
as posições e a política das operações anteriores.

| Papel | PlanosRead | PlanosManage |
|---|---|---|
| ADMIN | Próprio tenant | Próprio tenant |
| GESTOR | Próprio tenant | Próprio tenant |
| INSTRUTOR | 403 | 403 |
| ALUNO | 403 | 403 |
| UNKNOWN | 403 | 403 |
| Sem sessão válida | 401 | 401 |

Tenant nunca vem do cliente. `academia_id` e `academiaId` em body ou query recebem
400 para atores autorizados. ADMIN não possui bypass global. Plano externo e
inexistente retornam o mesmo 404 genérico. As listagens e os UPDATEs filtram tenant
no SQL, sem busca global seguida de filtro em memória.

Não se antecipam permissões de catálogo para Aluno/Instrutor. A revalidação mantém
a semântica atual: revogar um ator após o snapshot do filtro não promete cancelar
uma operação já iniciada.

## Validações e erros

POST/PUT exigem Content-Type application/json, aceitando parâmetros válidos como
charset. O parser estrito lê o documento inteiro e rejeita comentários, vírgula
final e documentos adicionais. Mantém o limite de profundidade do Drogon.

Campos desconhecidos ou protegidos (`id`, `academia_id`, `academiaId`, `ativo`,
`criado_em`) são rejeitados nas rotas de dados. Todas as queries são proibidas.
GET não aceita body. Status exige um único campo boolean, nunca número, string,
null, array ou objeto. Valores/durações exigem tokens JSON inteiros int64, nunca
floats, booleanos ou strings. Path usa parsing completo com from_chars, sem sinal
positivo, espaços, sufixos, decimais, zero, negativos ou overflow.

| HTTP | Condição |
|---|---|
| 200 | Consulta, PUT ou status válidos, inclusive idempotentes |
| 201 | Criação |
| 400 | JSON, Content-Type, query/body, campo, tipo, ID ou domínio inválido |
| 401 | Sessão/identidade inválida ou ator/Academia indisponíveis conforme autenticação existente |
| 403 | Papel proibido ou Perfil do ator inativo |
| 404 | Plano inexistente ou externo |
| 409 | Nome duplicado no tenant ou violação referencial esperada |
| 500 | Falha inesperada de persistência/conversão |

Controller e Service traduzem erros sem expor SQL, schema, paths ou credenciais.
Falha inesperada de CHECK após validação não é tratada artificialmente como
duplicidade. O mapper rejeita atividade persistida diferente de 0/1, sem normalizar
o banco. Não há optimistic locking; escritas válidas concorrentes podem serializar.

## Migration, rollout e rollback

Aplicar 001–006 em ordem, no banco de destino explicitamente escolhido pelo
operador, com FKs habilitadas. Aplicar 006 antes de disponibilizar as novas rotas.
Não existe executor automático no startup. Esta implementação não aplica migration
ao banco persistente de desenvolvimento e não modifica 001–005.

A expansão é aditiva. O teste aplica 006 sobre registros existentes e compara
Academia, Perfil, Usuario, Aluno e Instrutor antes/depois. O executável anterior
pode continuar usando essas tabelas. Em rollback do executável, preservar tabela
Plano e seus dados; não existe migration down automática.

Fixtures antigas que aplicam somente migrations anteriores continuam suficientes
para suas rotas: os novos controllers não consultam Plano no startup. Fixtures que
aplicam todas as migrations também exercitam 006, inicialmente sem planos.

## Testes e CI

[plano_integration.py](../tests/plano_integration.py) cria SQLite, configuração,
log e servidor temporários sob build/, aplica 001–006 e usa porta dinâmica e
sessões reais. Configura três conexões. Teardown encerra/aguarda o processo, com
fallback de kill; SHA-256 do banco persistente é comparado em finally.

A suíte cobre:

- Cadastro por ADMIN/GESTOR, descrição presente/null/omitida/vazia, gratuidade,
  Unicode, espaços preservados, resposta pública e leitura SQL dos valores.
- Listagem vazia, um/múltiplos registros, ordem, ativos/inativos e detalhes.
- PUT completo, descrição para NULL, idempotência e preservação de campos protegidos.
- Desativação/reativação e repetição de ambos os estados, com preservação dos dados.
- Contratos inválidos de POST/PUT/status, Content-Type, query/body, tipos e overflow.
- Valores monetários, duração e IDs até INT64_MAX, sem conversão para double.
- As cinco rotas para os cinco papéis, ausência de sessão e cookie inválido.
- Academias A/B com Admin/Gestor, listagens exatas, 404 externo/inexistente
  indistinguível, estado externo preservado e injeção snake/camel em ambos os sentidos.
- UNIQUE concorrente com duas sessões e barreira, sem sleep de sincronização:
  exatamente um 201, um 409 e uma linha persistida.
- FK, RESTRICT, UNIQUE e CHECK por persistência direta, com snapshots e foreign_key_check.
- Rollback de perda de Academia dentro do INSERT, inclusive remoções feitas pelo trigger.
- Atividade corrompida somente na fixture, com falha segura de conversão.
- 500 determinístico tornando somente Plano indisponível, sem remover as tabelas de autenticação.

Pedidos rejeitados com tabela disponível comparam snapshots completos de Plano.
A falha de schema é comparada após restauração da tabela. Essas provas têm escopo
definido; não afirmam ausência de todo efeito imaginável em qualquer falha interna.

O teste central [authorization_tests.cpp](../tests/authorization_tests.cpp) cobre
5×16 operações e 5×5 atribuições, além de nomes canônicos e operação desconhecida.
O [CI existente](../.github/workflows/ci.yml) acrescenta somente a chamada da nova
suíte, sem alterar job, SO, toolchain ou dependências.

Com aplicação/testes C++ compilados e DLLs no PATH:

```text
cmake --build build --parallel 2
cmake --build build/security-tests --parallel 2
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python -B tests/plano_integration.py
python -B tests/authorization_integration.py
python -B tests/usuario_integration.py
python -B tests/perfil_integration.py
python -B tests/auth_integration.py
python -B tests/aluno_integration.py
python -B tests/instrutor_integration.py
python -B tests/aluno_instrutor_integration.py
python -B tests/alunos_instrutores_authorization_integration.py
```

## Validação local

Na branch `feature/TH-36-planos`, sobre a base `b5e2e50`, os builds da aplicação
e dos testes C++ passaram. CTest aprovou 3/3 testes, incluindo a matriz central
estendida de autorização. A nova suíte concluiu 397 verificações HTTP.

Também passaram as regressões de authorization, Usuario/TH-63, Perfil, auth,
Aluno, Instrutor, vínculo, TH-34 e as quatro suítes de interface sem navegador.
Foram 13 suítes Python ao todo, incluindo Plano. Nenhum arquivo de frontend foi
alterado e nenhuma variante de browser foi executada.

O SHA-256 de `data/traininghub.db` foi idêntico antes e depois das execuções:

```text
10C935F52AD5FEADA7F2C25D9257CCBB01CC076D7AFD1306518C98F5970BABA8
```

A migration 006 foi aplicada somente nas fixtures temporárias. O banco persistente
não foi migrado. `git diff --check` passou e staging permaneceu vazio.

## Limitações e próximas entregas

Não implementa Matrícula, frontend, snapshots comerciais ou novas permissões para
Aluno/Instrutor. TH-37 deve garantir igualdade de tenant ao referenciar Plano;
uma FK simples para plano.id, isoladamente, não comprova essa igualdade. Plano
inativo permanece existente para referências históricas.

TH-39 deverá tratar `valor_centavos` sem perda acima de Number.MAX_SAFE_INTEGER.
O contrato numérico também permite `duracao_dias` int64. O parser atual de api.js
protege apenas chaves de ID; ele não é solução pronta para esses dois campos.
Esta TH não altera api.js nem restringe silenciosamente o domínio ao safe integer.

A obtenção de porta livre possui a janela usual entre fechar o socket de reserva
e iniciar o servidor. Os únicos sleeps da nova suíte pertencem ao polling de
readiness; concorrência usa barreira. Não há prova de layout/navegador nesta TH.
