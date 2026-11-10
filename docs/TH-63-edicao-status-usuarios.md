# TH-63 — Edição e ativação/desativação de usuários

## Objetivo e contratos

Disponibilizar os contratos backend de edição e situação necessários à TH-31,
sem implementar frontend ou modificar os contratos anteriores de Usuario.

| Método | Rota | Body exato | Sucesso |
|---|---|---|---|
| PUT | `/api/usuarios/{id}` | `{"nome":"Novo Nome","email":"novo@example.com"}` | 200, Usuario público |
| PUT | `/api/usuarios/{id}/status` | `{"ativo":false}` ou `{"ativo":true}` | 200, Usuario público |

Edição exige ambos os campos. Situação aceita somente boolean JSON real, nunca
0/1, strings, NULL, arrays ou objetos. Ambas as rotas rejeitam qualquer query e
qualquer campo extra, incluindo id, academia_id, perfil_id, senha, senha_hash,
password e criado_em. Inputs específicos impedem mass assignment do model.

O parser segue o padrão estrito da TH-30: lê o documento inteiro, rejeita
comentários, vírgula final e documentos adicionais, e preserva o limite de
profundidade configurado no Drogon. Whitespace válido ao redor do JSON é aceito.
IDs de URL usam parsing completo com `std::from_chars`, positivo até
9223372036854775807, sem espaços, sinal `+`, decimais, sufixos ou overflow.

Todas as respostas novas, inclusive erros, usam `Cache-Control: no-store`.
O formato público permanece:

```json
{
  "id": 42,
  "academia_id": 1,
  "perfil_id": 17,
  "nome": "Novo Nome",
  "email": "novo@example.com",
  "ativo": false,
  "criado_em": "2026-11-09 12:00:00"
}
```

Senha e hash nunca integram a resposta. Os sete campos são retornados pela própria
escrita, sem leitura posterior. O mapper público não exige nem busca senha_hash;
o mapper anterior continua carregando hash nas operações existentes que precisam dele.

## Autorização e tenant

As Operations `UsuariosUpdate` e `UsuariosManageStatus` foram acrescentadas ao fim
do enum. Ambas permitem ADMIN/GESTOR e negam INSTRUTOR/ALUNO/UNKNOWN. As permissões
anteriores e a matriz de atribuição de perfis não mudam.

AuthenticationFilter revalida a sessão antes do handler. Controller aplica o guard;
Service também verifica identidade positiva e a Operation específica. O tenant vem
exclusivamente de `ValidatedAuthContext.identity.academiaId`, inclusive para ADMIN.
Usuario inexistente e Usuario externo recebem a mesma resposta 404.

ADMIN/GESTOR podem editar o próprio nome/email e enviar `ativo:true` para a própria
conta. Autodesativação retorna 403 no Service. O UPDATE de situação também contém
`AND (? = 1 OR id <> ?)`, com situação solicitada e ID do ator, preservando a
proteção mesmo se uma validação anterior regredir.

Não existe proteção de último ADMIN/GESTOR ou hierarquia adicional entre papéis
dos alvos. `canAssign` continua restrito à atribuição de perfis na criação.

## Validação e unicidade

Nome reutiliza exatamente a regra de criação: rejeitar vazio ou string formada
somente por `" \t\r\n\f\v"`. Não há trim, limite novo ou whitelist. Unicode e
espaços ao redor de nomes válidos são preservados.

Email reutiliza `validEmail`: exatamente um @ com conteúdo antes/depois, sem
whitespace ASCII ou NUL. Não há trim, lowercase, limite novo ou validação RFC
adicional. A comparação permanece sensível a caixa, conforme o schema existente.

`UNIQUE(academia_id,email)` é a proteção atômica contra duplicidade. Próprio email
atual é permitido; email de outra conta do mesmo tenant retorna 409; email de
outro tenant é permitido. Não há SELECT prévio para verificar duplicidade.

Usuario alvo inativo ou com Perfil inativo/ausente continua administrável. Reativar
Usuario não recupera Perfil inválido nem concede permissões. Academia do ator
inativa continua bloqueada pela autenticação existente.

## Persistência e concorrência

Repository executa um único UPDATE parametrizado por operação, com `id` e
`academia_id` no WHERE e `RETURNING` explícito dos sete campos públicos. Edição
altera somente nome/email; situação altera somente ativo, persistido como 0/1.
Resultado vazio retorna 404, exceto autodesativação previamente rejeitada com 403.

Mesmos valores retornam 200, inclusive ativo já false/true. Escritas válidas
concorrentes usam a última escrita efetivada. UNIQUE resolve disputa pelo mesmo
email. Remoção ou transferência externa do alvo antes da escrita resulta em 404.
Não há optimistic locking, SELECT de elegibilidade ou transação adicional.

As condições de autorização do ator mantêm o snapshot existente da TH-25:
revogação posterior não promete cancelar requests que já passaram pelo filtro.

## Autenticação, reativação e relações

AuthService, AuthenticationFilter, SessionManager e AuthContextRepository permanecem
inalterados. Usuario inativo não faz novo login. No próximo request protegido,
a sessão existente é revalidada, recebe 401 e perde a identidade autenticada.
Reativação permite novo login, desde que Perfil/Academia também sejam válidos.
Sessão que já foi invalidada não recebe identidade novamente pela reativação.

Não existe revogação global permanente de todos os cookies: uma sessão não usada
durante o período inativo pode continuar válida após reativação se não expirou.
Isso preserva o comportamento existente; não há restauração explícita de sessões.

Mudança de email preserva a sessão atual por IDs. Novo login exige o novo email
e a mesma senha; o email antigo deixa de localizar essa conta.

Editar/desativar/reativar Usuario preserva Aluno, Instrutor e `aluno.instrutor_id`.
GET administrativo do vínculo mantém o comportamento da TH-30 após inativação.
Nenhum model ganha propriedade ou estado próprio.

## Erros e segurança

| HTTP | Condição |
|---|---|
| 200 | Atualização válida ou idempotente |
| 400 | Contrato, JSON, query, campo, tipo, ID ou nome/email inválido |
| 401 | Sessão/identidade inválida ou ator/Academia inativo, conforme fluxo existente |
| 403 | Sem permissão, Perfil do ator inválido/inativo ou autodesativação |
| 404 | Usuario inexistente ou externo |
| 409 | Email duplicado ou violação referencial esperada |
| 500 | Falha inesperada de banco/conversão |

Filtro e guard têm precedência sobre parsing. Erros de autorização preservam
`message`; erros de negócio usam `erro`. Não registrar bodies ou exceções SQL
brutas. Não expor hash, paths, SQL, stack traces ou detalhes internos. Nome/email
continuam dados textuais, sem sanitização HTML no banco; TH-31 deve renderizá-los
com segurança e preservar IDs int64 sem perda no JavaScript.

## Testes, CI e ausência de migration

`authorization_tests.cpp` cobre 5×14 acessos e mantém 5×5 atribuições: 95 células,
além de nomes canônicos e operação desconhecida. `authorization_integration.py`
inclui as duas rotas na matriz HTTP, com permissão, tenant e expiração.

`usuario_integration.py` mantém a TH-19 e acrescenta TH-63 com servidor real, sessões
reais, três conexões, SQLite/config temporários e migrations até 005 para fixtures
de Aluno/Instrutor. Cobre contratos, validação, int64 até INT64_MAX, duplicidade,
idempotência, autoedição, autodesativação, situação do alvo e falhas seguras.

Consultas diretas confirmam nome/email/ativo e preservação de id, academia_id,
perfil_id, senha_hash e criado_em. Pedidos recusados preservam estado. Fixtures
de corrupção usam conexões separadas; não alteram o banco de desenvolvimento.

O fluxo de login é comprovado pela nova API: desativação impede novo login e
sessões existentes; reativação permite novo login sem restaurar sessão invalidada.
Mudança de email é testada com a mesma senha. Aluno/Instrutor/vínculo permanecem.

Concorrência usa sessões separadas e barreiras para email UNIQUE e situação.
Uma transação externa controla a transferência de tenant antes da escrita, com
Event de início da request, sem sleep como sincronização desses cenários.

Respostas brutas, JSON decodificado e logs são verificados contra senhas sentinela,
hashes e detalhes internos. Log em arquivo contém mensagem genérica controlada;
cleanup preserva a exceção principal. SHA-256 do banco local é comparado antes/depois.

CI e CMake permanecem intactos: as suítes estendidas já são executadas no workflow
existente. Não há migration 006, alteração das migrations 001–005 ou rollout de
schema. Basta disponibilizar o executável atualizado sobre o schema existente.

Validação no ambiente MSYS2 UCRT64 com DLLs no PATH e `PYTHONUTF8=1`:

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

Não inclui frontend, exclusão, alteração de academia/perfil/senha ou gerenciamento
de vínculos. TH-31 pode consumir as respostas públicas e tratar os status acima.
