# TH-30 — Vínculo entre Aluno e Instrutor

## Escopo e persistência

Cada Aluno pode ter zero ou um Instrutor responsável. Um Instrutor pode acompanhar
vários Alunos. O vínculo atual fica em `aluno.instrutor_id`, nullable, sem tabela
intermediária, histórico ou unicidade sobre o Instrutor.

`migrations/005_aluno_instrutor.sql` acrescenta a coluna com `ALTER TABLE ADD COLUMN`
e FK para `instrutor(id)`, com `ON DELETE RESTRICT` e `ON UPDATE RESTRICT`. Alunos
anteriores permanecem com os mesmos IDs, Usuarios e datas, recebendo NULL nessa
coluna. Não há backfill, recriação de tabela ou edição das migrations 001–004.

Excluir ou alterar o ID de um Instrutor referenciado falha por FK. Nunca ocorre
exclusão em cascata de Alunos nem desassociação automática.

## API e autorização

| Método | Endpoint | Entrada | Resposta |
|---|---|---|---|
| GET | `/api/alunos/{alunoId}/instrutor` | Sem query/body | 200, `{"instrutor_id":123}` ou `{"instrutor_id":null}` |
| PUT | `/api/alunos/{alunoId}/instrutor` | Somente `{"instrutor_id":123}` | 200, `{"instrutor_id":123}` |

PUT associa ou substitui o responsável. Repetir o mesmo Instrutor é idempotente
e retorna 200. NULL não é aceito na escrita. Não existe DELETE do vínculo.

As Operations `AlunosInstrutorRead` e `AlunosInstrutorManage` foram acrescentadas
ao fim do enum. Ambas permitem somente ADMIN e GESTOR. INSTRUTOR, ALUNO e UNKNOWN
recebem 403. Permissões anteriores e regras de atribuição de perfis permanecem
inalteradas. A matriz C++ cobre 5×12 operações e mantém 5×5 atribuições.

Ambas as rotas usam AuthenticationFilter, AuthorizationGuard e autorização no
Service. Todas as respostas novas usam `Cache-Control: no-store`. Respostas não
incluem Usuario, dados pessoais, senha ou hash. Os contratos anteriores de Aluno
e seu model de três campos permanecem inalterados.

## Tenant e elegibilidade

A única autoridade para academia é `ValidatedAuthContext.identity.academiaId`.
Aluno e Instrutor continuam derivados de Usuario; não recebem academia própria.
ADMIN não possui bypass. Queries novas e consultas reutilizadas filtram tenant
no SQL. Body com `academia_id`, `usuario_id` ou outros campos e qualquer query
recebem 400 para atores autorizados.

PUT busca Aluno no tenant, verifica a projeção existente de elegibilidade de seu
Usuario, busca Instrutor no mesmo tenant e verifica a projeção correspondente.
Exige Usuarios ativos com valor 1, Perfis existentes e ativos com valor 1, nomes
exatos reconhecidos por `roleFromName` como ALUNO e INSTRUTOR, e Academia ativa.
IDs de Perfil não identificam papéis. Registro especializado existente não prova
que o perfil atual permanece elegível.

GET preserva a consulta administrativa após inativação de Usuario/Perfil ou
mudança de perfil. A leitura usa um único snapshot e só devolve o ID do responsável
quando o Instrutor e seu Usuario ainda existem no mesmo tenant. Vínculo órfão ou
externo retorna 404 genérico; não é apresentado como ausência de vínculo.

## Camadas e concorrência

AlunoController reutiliza os parsers locais: path decimal positivo com
`std::from_chars`, JSON estrito com `CharReaderBuilder::ecma404Mode`, leitura sem
query/body. Body exige tipo inteiro positivo aceito por `isInt64()`. Strings,
floats, booleanos, NULL, zero, negativos, overflow, comentários e documentos
adicionais são rejeitados. IDs percorrem `std::int64_t` e `Json::Int64`, incluindo
`9223372036854775807`, sem conversão intermediária para int32 ou double.

AlunoService recebe AlunoRepository e InstrutorRepository. Reutiliza
`buscarPorId` e `buscarUsuarioParaCriacao` existentes para validar ambos os alvos;
não reaplica a rejeição de registro especializado já existente usada na criação.
Callbacks copiam dependências e valores, sem capturar Services temporários.

AlunoRepository oferece `buscarInstrutor` e `definirInstrutor`, com resultado
específico do vínculo. A escrita usa UPDATE parametrizado com EXISTS para ambos
os alvos, repetindo tenant, atividade, perfis e Academia ativa. `RETURNING` devolve
o ID persistido sem consulta posterior. Nenhuma linha após validação significa
conflito. Uma escrita é atômica e dispensa transação explícita adicional.

Duas substituições válidas usam a última escrita efetivada. Revogação do ator
depois do snapshot de autenticação mantém a limitação existente da TH-25.
Transferências externas de tenant ou mudanças posteriores de perfil não são
impedidas por uma FK simples. A API não oferece essas transferências; a leitura
recusa vínculos que tenham passado a cruzar tenants.

## Erros

| HTTP | Condição |
|---|---|
| 200 | Consulta, associação, substituição ou repetição válida |
| 400 | Contrato/ID inválido; Usuario alvo inativo; Perfil alvo ausente, inativo ou incorreto |
| 401 | Sessão inválida/expirada; ator ou Academia ausente/inativo, conforme autenticação existente |
| 403 | Ator sem permissão ou Perfil do ator ausente/inativo |
| 404 | Aluno/Instrutor ausente no tenant; vínculo inconsistente na consulta |
| 409 | FK perdida ou estado alterado entre validação e escrita condicionada |
| 500 | Falha inesperada de banco ou conversão |

Filtro e guard precedem parsing. Erros de negócio usam `erro`; autenticação e
autorização preservam `message`. SQL, paths, schema, stack traces e credenciais
não são enviados ao cliente nem registrados pelos caminhos novos.

## Testes e CI

`tests/aluno_instrutor_integration.py` usa TemporaryDirectory, SQLite/config próprios,
porta livre, servidor e sessões reais, três conexões e migrations 001–005. Cria
Alunos antes da 005 e confirma preservação completa com responsável NULL.

A suíte verifica autorização, sessão desconhecida, logout, expiração, nomes não
canônicos, N:1, substituição, idempotência, ambos os sentidos de tenant, elegibilidade
atual e consultas administrativas posteriores. Cobre contrato estrito, int64,
falhas de banco/conversão, FK RESTRICT e perda de Instrutor durante UPDATE.

Nove cenários concorrentes mantêm um bloqueio de escrita enquanto os SELECTs
observam o estado anterior; o UPDATE aguarda e rejeita o estado agora inelegível
com 409. Abrangem atividade, tenant e perfil dos dois Usuarios, atividade dos dois
Perfis e da Academia. Consultas diretas confirmam persistência, ausência de alterações
nos pedidos recusados e `foreign_key_check` vazio.

Respostas brutas, JSON decodificado e logs são verificados contra senha correta,
senha incorreta sentinela, hash e detalhes internos. Uma falha controlada de login
produz mensagem genérica conhecida para comprovar captura do log. Saída do servidor
usa arquivo, sem PIPE; encerramento e inspeção do log preservam a exceção principal.
SHA-256 do banco local é comparado antes/depois.

CI acrescenta somente `python tests/aluno_instrutor_integration.py` ao step existente,
depois de Instrutor. CMake permanece inalterado; Python roda separado do CTest.

Validação no ambiente Windows/MSYS2 UCRT64, com DLLs no PATH e `PYTHONUTF8=1`:

```text
cmake --build build --parallel 2
cmake --build build/security-tests --parallel 2
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python tests/auth_integration.py
python tests/authorization_integration.py
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/aluno_integration.py
python tests/instrutor_integration.py
python tests/interface_web.py
python tests/aluno_instrutor_integration.py
git diff --check
```

## Rollout e limites

O operador deve aplicar 001–005, em ordem e uma vez cada migration estrutural,
ao banco de destino explicitamente escolhido, com FKs habilitadas. Aplicar 005
antes de disponibilizar o executável que oferece as rotas novas. Não há executor
automático. Em rollback do executável, preservar coluna e vínculos.

Implementação e testes não aplicam migrations em `data/traininghub.db`. Validação
de sintaxe e constraints acontece no banco temporário, inclusive pelo SQLite do
servidor real. A infraestrutura existente habilita FKs por conexão e configura
`busy_timeout=5000`.

Não inclui UI, desassociação, histórico, múltiplos responsáveis, área do Instrutor,
treinos ou funcionalidades de issues posteriores. Browser/CDP não é requisito.
