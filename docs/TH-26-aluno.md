# TH-26 — Estrutura inicial do módulo Aluno

## Objetivo e arquitetura

Aluno é uma extensão de Usuario. O módulo mantém a arquitetura
`AlunoController → AlunoService → AlunoRepository → SQLite`, com callbacks
assíncronos, SQL parametrizado e JSON somente no Controller.

O Model é uma struct com campos públicos:

```cpp
struct Aluno
{
    std::int64_t id{};
    std::int64_t usuario_id{};
    std::string criado_em;
};
```

Não há campos específicos adicionais aprovados. Nome, email, perfil, estado
ativo e credenciais continuam pertencendo a Usuario.

## Relacionamentos e migration

A cardinalidade é `Usuario 1 → 0..1 Aluno`. Cada Aluno referencia exatamente um
Usuario, com `usuario_id NOT NULL UNIQUE` e FK para `usuario.id`.

**Aluno não contém academia_id. A academia é obtida pelo Usuario relacionado.**
Todas as consultas e a criação limitam o Usuario pela academia do contexto
validado. Não há busca global seguida de filtro em memória.

`migrations/003_aluno.sql` cria somente a tabela `aluno`:

```sql
CREATE TABLE aluno (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL UNIQUE,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuario(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);
```

A UNIQUE cria o índice de `usuario_id`. O índice existente
`usuario(academia_id, email)` também atende ao prefixo tenant das consultas.
Não há novos índices redundantes, alterações nas migrations 001/002 ou backfill.

A aplicação continua sem executor automático de migrations. O operador deve
aplicar 001, 002 e 003, nessa ordem, ao banco explicitamente escolhido, com FKs
habilitadas. A migration 003 deve ser aplicada uma vez; repetição informa que a
tabela já existe, sem esconder divergências de schema.

O rollout é aditivo: aplicar 003 antes de disponibilizar o novo executável. Os
módulos anteriores continuam usando suas tabelas. Em rollback do executável,
preservar a tabela e seus registros; não apagar dados para voltar à versão
anterior. Remover a tabela não faz parte desta entrega.

FKs RESTRICT impedem excluir Usuario referenciado ou alterar seu ID. Inativação
e mudança de perfil não apagam Aluno. Não há endpoint para excluir Aluno ou
transferi-lo entre Usuarios. Como a academia é derivada, uma alteração externa
de `usuario.academia_id` altera também o tenant do Aluno; a API atual não oferece
essa transferência.

## Endpoints e JSON

| Método | Rota | Request | Sucesso |
|---|---|---|---|
| POST | `/api/alunos` | `{"usuario_id":42}` | 201, objeto Aluno |
| GET | `/api/alunos` | Sem query ou body | 200, array ordenado por `id` |
| GET | `/api/alunos/{id}` | Sem query ou body | 200, objeto Aluno |

Objeto de criação e consulta:

```json
{
  "id": 7,
  "usuario_id": 42,
  "criado_em": "2026-11-07 12:00:00"
}
```

Listagem vazia retorna `[]`. IDs usam `std::int64_t` e `Json::Int64`. Aceitam
inteiros positivos até `9223372036854775807`. JSON rejeita strings, booleanos,
decimais, null, zero, negativos, overflow e campos extras. IDs de URL usam
parsing completo com `std::from_chars`, sem espaços, sinal `+` ou sufixos.

POST aceita exatamente `usuario_id` no objeto JSON. Query é rejeitada em todas
as rotas. GET também rejeita qualquer body. Portanto, `academia_id` no body ou
na query resulta em 400 para atores autorizados. O filtro e o guard são
executados antes da validação HTTP; requisições sem autenticação ou permissão
mantêm 401/403. Não são retornados dados de Usuario, senha ou hash.

## Autorização e isolamento

As três rotas declaram `AuthenticationFilter` da TH-25. O Controller usa
`AuthorizationGuard::require`; o Service também consulta a matriz central para
proteger chamadas internas. As operações novas são `AlunosCreate` e `AlunosRead`.

| Papel | Criar | Listar/buscar |
|---|---|---|
| ADMIN | Própria academia | Própria academia |
| GESTOR | Própria academia | Própria academia |
| INSTRUTOR | Não | Não |
| ALUNO | Não | Não |
| UNKNOWN | Não | Não |

Somente `ValidatedAuthContext.identity.academiaId` determina o tenant. ADMIN
não possui bypass. Usuario externo na criação e Aluno externo na consulta
recebem a mesma resposta 404 de um registro inexistente no tenant.

A revalidação existente continua responsável pela sessão, Usuario do ator,
Perfil do ator e Academia. Academia/ator ausente ou inativo invalida a sessão
com 401; perfil do ator ausente/inativo e papel sem permissão recebem 403.

## Elegibilidade e concorrência

O Service valida a criação usando uma projeção mínima do Usuario no tenant,
sem selecionar `senha_hash`. Exige Usuario ativo, Perfil existente/ativo e
`roleFromName(perfil.nome) == Role::ALUNO`. O mapeamento central da TH-25 usa o
nome exato `Aluno`; IDs fixos, aliases e diferenças de caixa não são aceitos.
Também verifica associação existente e academia ativa.

O Repository faz `INSERT ... SELECT` condicionado a Usuario, tenant, estado
ativo de Usuario/Perfil/Academia e nome do Perfil já validado pelo Service.
A escrita reavalia essas condições no mesmo statement. `RETURNING` devolve
somente a linha criada, sem uma segunda leitura ou uso de insert ID antigo.
Nenhuma linha inserida após a validação representa conflito de relacionamento.

A UNIQUE é a garantia final contra duplicidade concorrente. Duas requisições
para o mesmo Usuario elegível produzem uma criação e um conflito, com somente
um registro persistido. Uma consulta prévia não substitui essa proteção.

Elegibilidade é requisito de criação. Consultas administrativas filtram por
tenant, sem filtrar estado ativo ou Perfil do Usuario relacionado. Aluno
continua consultável após inativação do Usuario, mudança de Perfil ou
inativação do Perfil. Isso não concede nem preserva permissões de Role::ALUNO.

## Erros

| Status | Condição |
|---|---|
| 200 | Consulta bem-sucedida |
| 201 | Aluno criado |
| 400 | Entrada inválida; Usuario inativo; Perfil ausente/inativo ou diferente de Aluno |
| 401 | Sessão/contexto inválido, conforme TH-25 |
| 403 | Ator sem permissão |
| 404 | Usuario ou Aluno inexistente no tenant |
| 409 | Associação duplicada; FK perdida ou elegibilidade/relacionamento alterado durante criação |
| 500 | Falha inesperada de banco ou conversão |

Erros do módulo usam `{"erro":"mensagem"}`. Erros do filtro/guard preservam
`{"message":"mensagem"}`. Exceções de banco são traduzidas no Service, sem
mensagens SQL, SQLite, schema, paths ou stack traces na resposta. Callbacks
copiam as dependências necessárias, sem capturar Services temporários por `this`.

## Testes e CI

`tests/aluno_integration.py` inicia servidor real com três conexões, autenticação
real e SQLite temporário com migrations 001, 002 e 003. Verifica:

- Matriz HTTP, sessão ausente e tenant de ADMIN/GESTOR.
- Criação válida, elegibilidade, Perfil ausente/inativo e nomes não canônicos.
- Lista vazia, ordem, busca por ID e persistência das consultas após mudanças.
- JSON inválido, campos extras, query/body inesperados e IDs int64 até o limite.
- Duplicidade, duas criações simultâneas e alterações concorrentes sob bloqueio de escrita.
- UNIQUE, NOT NULL, FK RESTRICT, perda de Usuario durante INSERT e rollback.
- Falhas de banco/conversão, respostas genéricas e ausência de credenciais.
- Hash inalterado do banco de desenvolvimento e encerramento do servidor isolado.

A matriz C++ existente foi ampliada sem remover permissões anteriormente
testadas. A CI mantém CTest e todas as regressões existentes e acrescenta
`python tests/aluno_integration.py`, sem mudar permissões do workflow.

Com o ambiente Windows/MSYS2 UCRT64 e DLLs existentes no PATH:

```text
cmake --build build --parallel 2
cmake --build build/security-tests --parallel 2
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python tests/aluno_integration.py
python tests/authorization_integration.py
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/auth_integration.py
python tests/interface_web.py
git diff --check
```

## Limitações

Não há criação automática de Aluno ao cadastrar Usuario, backfill, atualização,
exclusão, ativação, consulta do próprio Aluno ou interface. Não há vínculo com
Instrutor nem campos de módulos futuros. A criação não promete cancelar uma
request caso o ator seja revogado depois do snapshot validado da TH-25.
Mudanças SQL externas continuam exigindo responsabilidade do operador e FKs
habilitadas; a tabela não impõe Role::ALUNO como invariável permanente.

Esta entrega não aplica migrations nem provisiona perfis no banco local.
