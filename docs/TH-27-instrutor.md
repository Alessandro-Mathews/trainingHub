# TH-27 — Estrutura inicial do módulo Instrutor

## Objetivo e arquitetura

Instrutor é uma extensão de Usuario. O módulo segue a implementação final da
TH-26: `InstrutorController → InstrutorService → InstrutorRepository → SQLite`,
com callbacks assíncronos, SQL parametrizado e JSON somente no Controller.
Aluno e os demais Controllers permanecem inalterados.

O Model contém somente os dados aprovados:

```cpp
struct Instrutor
{
    std::int64_t id{};
    std::int64_t usuario_id{};
    std::string criado_em;
};
```

Não há nome, email, ativo, perfil, CREF ou especialidade duplicados. O cadastro
de Usuario não cria Instrutor automaticamente.

## Relacionamentos e migration

Cada Instrutor pertence exatamente a um Usuario. Cada Usuario pode ter zero ou
um registro Instrutor, com `usuario_id NOT NULL UNIQUE`.

**Instrutor não contém academia_id. A academia é derivada do Usuario relacionado.**
Criação e consultas usam exclusivamente o tenant do contexto validado, no SQL.

`migrations/004_instrutor.sql` cria:

```sql
CREATE TABLE instrutor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL UNIQUE,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuario(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);
```

A UNIQUE fornece o índice para `usuario_id`. O índice existente de Usuario
começa por `academia_id`, útil ao JOIN tenant-scoped. Não há índice redundante
nem alteração nas migrations 001, 002 e 003.

A migration é manual, aplicada uma vez depois de 001–003, ao banco escolhido
explicitamente pelo operador, com FKs habilitadas. Não há executor automático
ou backfill. Repetição da 004 informa tabela existente. Aplicar a migration antes
do novo executável; em rollback do executável, preservar tabela e registros.

FK RESTRICT impede excluir Usuario referenciado ou alterar seu ID. Não há
transferência entre Usuarios ou exclusão nesta API. Como a academia é derivada,
alterar `usuario.academia_id` externamente também altera o tenant do Instrutor.

## Endpoints e JSON

| Método | Rota | Request | Sucesso |
|---|---|---|---|
| POST | `/api/instrutores` | `{"usuario_id":42}` | 201, objeto criado |
| GET | `/api/instrutores` | Sem query/body | 200, array ordenado por ID |
| GET | `/api/instrutores/{id}` | Sem query/body | 200, objeto |

Objeto retornado:

```json
{
  "id": 7,
  "usuario_id": 42,
  "criado_em": "2026-11-07 12:00:00"
}
```

Lista vazia retorna `[]`. Nenhum dado pessoal ou credencial de Usuario integra
essa resposta. IDs usam `std::int64_t` e `Json::Int64`, positivos até
`9223372036854775807`. IDs de URL usam parsing completo com `std::from_chars`.

POST possui parser local com `Json::CharReaderBuilder::ecma404Mode` e
`CharReader::parse` sobre o body inteiro, preservando o limite de profundidade
do Drogon. Comentários, vírgula final, segundo documento e conteúdo adicional
são rejeitados. Whitespace válido antes/depois é permitido. Falhas de parsing,
inclusive exceções JsonCpp, retornam erro genérico 400.

A raiz deve ser objeto com somente `usuario_id`. Campos extras, booleanos,
strings, decimais, null, zero, negativos e overflow são rejeitados. A correção
estrita da TH-26 é mantida, sem configuração global ou parser manual.

Todas as rotas rejeitam query. GET também rejeita body. `academia_id` no body
ou query não seleciona tenant e recebe 400 para atores autorizados. O filtro
e o guard executam antes da validação HTTP; 401/403 têm precedência para
requisições sem autenticação/permissão.

## Autorização e multi-tenancy

Todas as rotas usam `AuthenticationFilter` e `AuthorizationGuard` da TH-25.
O Service também consulta a matriz central. As operações `InstrutoresCreate`
e `InstrutoresRead` foram acrescentadas ao fim do enum existente.

| Papel | Criar | Consultar |
|---|---|---|
| ADMIN | Próprio tenant | Próprio tenant |
| GESTOR | Próprio tenant | Próprio tenant |
| INSTRUTOR | Não | Não |
| ALUNO | Não | Não |
| UNKNOWN | Não | Não |

`ValidatedAuthContext.identity.academiaId` é a única autoridade. ADMIN não tem
bypass. Usuario externo na criação e Instrutor externo na busca são
indistinguíveis de recurso inexistente no tenant: ambos retornam 404.

As consultas fazem JOIN entre Instrutor e Usuario e aplicam tenant no WHERE.
Não há busca global seguida de filtro em memória. A revalidação de ator,
sessão, Perfil e Academia permanece na infraestrutura existente.

## Elegibilidade, concorrência e histórico

O Service exige Usuario existente no tenant, ativo, com Perfil existente/ativo
e `roleFromName(perfil.nome) == Role::INSTRUTOR`. Não compara IDs de perfil nem
aceita nomes não canônicos, aliases ou diferenças de caixa. Academia deve estar
ativa e o Usuario não pode possuir outro registro Instrutor.

O Repository consulta uma projeção mínima, sem selecionar senha/hash. O INSERT
usa SELECT condicionado ao Usuario, tenant, estados ativos de Usuario/Perfil/
Academia e nome do Perfil validado. A operação final reavalia as condições no
banco. Se nenhuma linha for criada após a validação, retorna conflito de
relacionamento. `RETURNING` devolve somente a linha inserida.

`UNIQUE(usuario_id)` protege contra duplicidade concorrente. Duas requisições
simultâneas para o mesmo Usuario elegível geram uma resposta 201 e uma 409,
persistindo exatamente um registro. Consulta prévia não substitui a UNIQUE.

Elegibilidade é exigida somente na criação. GETs administrativos não filtram
Usuario ativo, Perfil atual ou estado do Perfil. Instrutor continua consultável
após inativação ou mudança de perfil, respeitando sempre o tenant.

Um Usuario pode manter registros históricos em Aluno e Instrutor. A existência
desses registros não concede dois papéis: autorização depende somente do perfil
atual revalidado. Não existe exclusividade entre tabelas nem vínculo
Aluno–Instrutor nesta issue.

## Erros e callbacks

| Status | Condição |
|---|---|
| 200 | Consulta bem-sucedida |
| 201 | Instrutor criado |
| 400 | Entrada inválida; Usuario inativo; Perfil ausente/inativo ou não Instrutor |
| 401 | Sessão/contexto inválido conforme TH-25 |
| 403 | Ator sem permissão |
| 404 | Usuario ou Instrutor inexistente no tenant |
| 409 | Duplicidade; FK/relacionamento perdido durante criação |
| 500 | Falha inesperada de banco ou conversão |

Erros do módulo usam `{"erro":"mensagem"}`; filtro/guard preservam
`{"message":"mensagem"}`. Detalhes SQL, SQLite, schema, paths, stack traces e
credenciais não são expostos. O Service traduz exceções para erros de domínio.
Callbacks copiam contextos e dependências; não capturam `this` temporário.

## Testes e CI

`tests/instrutor_integration.py` usa servidor real, sessões reais, SQLite
temporário, migrations 001–004 e três conexões. Cobre matriz de autorização,
elegibilidade, papéis incorretos/nomes não canônicos, cross-tenant, consultas
administrativas após mudanças, JSON estrito sem persistência indevida, int64
até o limite, UNIQUE concorrente, FK RESTRICT, perda de relacionamento e erros
genéricos de banco/conversão.

A concorrência usa duas threads, barreira e sessões separadas. Verifica
explicitamente os status `[201, 409]` e a quantidade no banco.

O cenário histórico cria Aluno pela API real, muda o Perfil somente no banco
temporário e cria Instrutor pela API. Confirma ambos os registros e nega acesso
administrativo ao Usuario convertido. Nenhum endpoint especial foi criado.

A matriz C++ passou de 5×8 para 5×10, preservando as 40 células anteriores. A CI
acrescenta somente o script Instrutor; mantém CTest e os seis scripts HTTP
anteriores, incluindo Aluno, sem alterar permissões ou dependências.

Validação no ambiente Windows/MSYS2 UCRT64 existente, com DLLs no PATH:

```text
cmake --build build --parallel 2
cmake --build build/security-tests --parallel 2
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python tests/instrutor_integration.py
python tests/aluno_integration.py
python tests/authorization_integration.py
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/auth_integration.py
python tests/interface_web.py
git diff --check
```

Os testes comparam SHA-256 do banco local antes/depois e encerram servidor e
recursos temporários. A implementação não aplica migrations ao banco local.

## Limitações

Somente criação e consulta administrativa. Não há atualização, exclusão,
ativação, consulta própria, interface, CREF ou especialidade. Não há associação
Aluno–Instrutor, campos ou tabelas de módulos futuros. Requests já validadas
mantêm a limitação de revogação em andamento documentada na TH-25. Operações SQL
externas exigem responsabilidade do operador e FKs habilitadas.
