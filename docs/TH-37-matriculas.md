# TH-37 — Matrículas

## Objetivo e arquitetura

Matrícula registra uma contratação histórica entre Aluno e Plano. A implementação
segue Controller → Service → Repository → SQLite, sem mudanças funcionais nos
módulos anteriores, na autenticação ou no frontend.

- `MatriculaController`: contrato HTTP, guard antes do parsing, JSON estrito e respostas sem cache.
- `MatriculaService`: autorização, tenant autenticado, resolução e elegibilidade dos recursos, erros de domínio.
- `MatriculaRepository`: SQL parametrizado, projeções explícitas, mapeamento seguro e callbacks assíncronos.
- `Matricula`: struct header-only, com IDs, valor e duração em `std::int64_t` e textos/datas em `std::string`.

## Migration e modelo

`007_matricula.sql` é posterior à `006_plano.sql`. Migrations 001–006 permanecem
inalteradas. A migration cria apenas tabela e índices; não altera nem transforma
registros existentes. Testes comparam as tabelas anteriores antes/depois de aplicar 007.

| Campo público/SQLite | Tipo | Origem |
| --- | --- | --- |
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | SQLite |
| `academia_id` | INTEGER NOT NULL | Contexto autenticado |
| `aluno_id` | INTEGER NOT NULL | `Aluno.id` validado |
| `plano_id` | INTEGER NOT NULL | `Plano.id` validado |
| `nome_plano_contratado` | TEXT NOT NULL | `Plano.nome` no INSERT |
| `valor_contratado_centavos` | INTEGER NOT NULL | `Plano.valor_centavos` no INSERT |
| `duracao_contratada_dias` | INTEGER NOT NULL | `Plano.duracao_dias` no INSERT |
| `data_inicio` | DATETIME NOT NULL | SQLite `datetime('now')` |
| `data_fim` | DATETIME NOT NULL | Início acrescido da duração contratada |
| `criado_em` | DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | SQLite |

`aluno_id` é **Aluno.id**, nunca Usuario.id. A academia é obtida exclusivamente de
`ValidatedAuthContext.identity.academiaId`, após AuthenticationFilter e AuthorizationGuard.
Snapshot e academia nunca vêm do cliente.

As três FKs referenciam `academia(id)`, `aluno(id)` e `plano(id)`, com **ON DELETE
RESTRICT e ON UPDATE RESTRICT**. Não há CASCADE, UNIQUE comercial ou triggers de produção.
CHECKs exigem valor inteiro não negativo, duração inteira positiva, datas canônicas
com 19 caracteres reconhecidas pelo SQLite e `data_fim > data_inicio`.

Índices não únicos:

- `idx_matricula_academia_id (academia_id)`;
- `idx_matricula_aluno_academia (aluno_id, academia_id)`;
- `idx_matricula_plano_id (plano_id)`.

As FKs simples não demonstram que os três pais pertencem à mesma academia. Essa
invariante é garantida pela escrita condicionada da API. Não foram introduzidas FKs
compostas nos módulos Aluno e Plano. Alterações diretas por SQL exigem essa mesma disciplina.

## Snapshot, vigência e cardinalidade

O próprio `INSERT ... SELECT ... RETURNING` copia nome, valor em centavos e duração
do Plano e gera as datas a partir do estado efetivo da escrita. Nenhum preço é
convertido para ponto flutuante. O retorno representa o registro persistido.

Datas usam UTC do SQLite, com formato `YYYY-MM-DD HH:MM:SS` e precisão de segundos.
Não há fuso por academia, agendamento ou retroatividade. O início é inclusivo e o
fim exclusivo: `[data_inicio, data_fim)`. O cálculo usa dias do SQLite; 30 dias
significam intervalo exato de 30 dias, não um mês de calendário.

Quando `datetime('now', '+' || duracao_dias || ' days')` não produz uma data válida
posterior ao início, a criação retorna **400**, sem escrita parcial. Plano continua
aceitando o contrato int64 da TH-36; não se restringe sua duração nesta TH.

Nome, preço, duração e datas contratadas são imutáveis pela API. Alterações futuras
no Plano, inclusive inativação, não recalculam nem ocultam o histórico. O mesmo vale
para inativação do Usuario do Aluno e mudança ou inativação do seu Perfil.

Um Aluno pode ter várias Matrículas, inclusive várias para o mesmo Plano. Duas
contratações simultâneas válidas são aceitas. Não existe exclusividade temporal,
situação persistida, enum de situação ou boolean `ativo` na Matrícula.

## Endpoints e autorização

| Método | Rota | Operation | Sucesso |
| --- | --- | --- | --- |
| POST | `/api/matriculas` | `MatriculasManage` | 201 + objeto |
| GET | `/api/matriculas` | `MatriculasRead` | 200 + array direto |
| GET | `/api/matriculas/{id}` | `MatriculasRead` | 200 + objeto |
| GET | `/api/alunos/{alunoId}/matriculas` | `MatriculasRead` | 200 + array direto |

`MatriculasRead` e `MatriculasManage` foram acrescentadas ao final de Operation.
As 16 Operations anteriores mantêm valores e comportamento. Matriz passa a 18.

| Role | Read | Manage |
| --- | --- | --- |
| ADMIN | Permitido | Permitido |
| GESTOR | Permitido | Permitido |
| INSTRUTOR | 403 | 403 |
| ALUNO | 403 | 403 |
| UNKNOWN | 403 | 403 |

Sessão ausente, inválida ou forjada recebe 401 pela infraestrutura existente.
Todas as quatro rotas usam AuthenticationFilter e `Cache-Control: no-store`.
O guard antecede parsing de body, query e path. A rota por Aluno é administrativa,
inclusive quando a sessão ALUNO corresponde ao próprio Aluno. Self-read fica para TH-41.

### Criação

Content-Type deve ser `application/json` (charset JSON admitido). Corpo exato:

```json
{"aluno_id": 10, "plano_id": 20}
```

Ambos os campos são obrigatórios, inteiros JSON positivos representáveis em int64.
Float, string, bool, null, array, objeto e overflow são rejeitados. Não se aceitam
query, campos extras, chaves duplicadas, comentários, vírgula final ou documentos
adicionais. Isso inclui tenant, IDs de Matrícula, snapshots, datas, situação e atividade.

Resposta consistente nas quatro rotas:

```json
{
  "id": 1,
  "academia_id": 1,
  "aluno_id": 10,
  "plano_id": 20,
  "nome_plano_contratado": "Mensal",
  "valor_contratado_centavos": 9990,
  "duracao_contratada_dias": 30,
  "data_inicio": "2026-11-26 12:00:00",
  "data_fim": "2026-12-26 12:00:00",
  "criado_em": "2026-11-26 12:00:00"
}
```

### Consultas

GET não aceita query nem body. IDs de path exigem parsing completo, inteiro
positivo int64, sem sufixo, sinal positivo, espaço ou overflow. Listas são ordenadas
por ID e incluem todo o histórico, sem filtros, paginação ou seleção de vigentes.

Academia sem Matrículas recebe `[]`. Aluno local existente sem Matrículas recebe
`[]`; Aluno inexistente ou externo recebe 404 indistinguível. Matrícula inexistente
ou externa também recebe 404 indistinguível.

Todas as consultas aplicam tenant no SQL. Leituras verificam consistência entre
academia da Matrícula, Usuario do Aluno e Plano. Relações inconsistentes após
alterações externas não são expostas. Leituras não exigem atividade ou Perfil
atual dos pais, preservando o histórico administrativo.

## Elegibilidade e escrita atômica

A pré-validação resolve Aluno e Plano exclusivamente no tenant. Recursos externos
e inexistentes compartilham resposta 404, antes de avaliar elegibilidade local.
Aluno precisa ter Usuario correspondente, ativo, na academia, e Perfil existente,
ativo, com nome canônico exatamente `Aluno`. Plano precisa estar ativo na mesma
academia. Recurso local inelegível recebe 400.

A escrita repete IDs, tenant de ambos os recursos, atividade de Usuario, Perfil,
Academia e Plano, nome canônico do Perfil e validade da data final no mesmo SQL.
Assim, nenhuma decisão depende exclusivamente do SELECT anterior. Snapshot e datas
provêm da linha efetiva de Plano usada no INSERT, mesmo se o Plano foi editado
entre pré-validação e escrita.

Se a pré-validação passou e a escrita condicionada não retorna linha, a resposta
é 409. Violação de FK esperada também é traduzida para 409. Falhas inesperadas
retornam 500 sanitizado. Não há 409 por duplicidade comercial.

| HTTP | Condição |
| --- | --- |
| 200 | Consulta válida |
| 201 | Criação persistida |
| 400 | Contrato, IDs, JSON, Content-Type, query/body, inelegibilidade local ou vigência irrepresentável |
| 401 | Sessão/identidade inválida |
| 403 | Role sem autorização |
| 404 | Recurso inexistente ou externo |
| 409 | Relação deixou de satisfazer escrita condicionada ou integridade de FK esperada |
| 500 | Falha interna inesperada, sem SQL, schema, caminhos ou credenciais na resposta |

## Testes e operação

`tests/matricula_integration.py` aplica migrations 001–007 em SQLite temporário,
configura porta dinâmica e inicia servidor real. Config, logs e banco ficam em
diretório temporário. Teardown termina o processo e força encerramento se necessário;
SHA-256 do banco persistente é comparado em `finally`.

A suíte cobre criação ADMIN/GESTOR, persistência e representação completa,
Aluno.id distinto de Usuario.id, snapshots após edição e inativação do Plano,
UTC e duração exata, duração int64 irrepresentável, histórico após mudanças de
Usuario/Perfil, isolamento A/B nos dois sentidos, quatro rotas por Role,
contratos estritos, IDs e centavos int64, duplicidade permitida, criações concorrentes
legítimas, FKs, RESTRICT, CHECKs, `PRAGMA foreign_key_check`, ausência de escrita
parcial e 500 com apenas tabela Matrícula indisponível.

Um trigger **exclusivamente no banco de teste** remove um Plano durante INSERT,
produzindo falha de FK determinística após pré-validação. O teste exige 409 e rollback
do Plano e da Matrícula. O trigger é removido em `finally`; não integra a migration.

Limitação de cobertura: desativar Plano ou tornar Aluno inelegível exatamente entre
pré-validação e escrita não é forçado por HTTP. Não existe ponto de sincronização
determinístico no servidor. Não foram adicionados hooks de produção nem sleeps para
abrir essa janela. As condições são repetidas no próprio INSERT; concorrência de
duas criações válidas é exercitada com barreira, sem exigir rejeição por duplicidade.

Build mantém dependências existentes e acrescenta apenas os três `.cpp` de Matrícula.
CI mantém job, SO, toolchain e todas as suítes anteriores, acrescentando apenas
`python tests/matricula_integration.py`.

Validação local em 2026-11-26, sobre `feature/TH-37-matriculas`, base `f582d32`:
build limpo da aplicação e dos testes aprovado; CTest 3/3; Matrícula 231 verificações
HTTP; Plano 397; Aluno 147; Instrutor 155; vínculo 212; TH-34 865 (14 matrizes e
768 rejeições); Authorization 247; Usuario 379; Perfil 138; Auth aprovado.
As 16 Operations anteriores e suas células de autorização foram comparadas com
HEAD. CI recebeu exatamente uma linha adicional. Staging permaneceu vazio.
SHA-256 antes e depois do banco persistente:
`10C935F52AD5FEADA7F2C25D9257CCBB01CC076D7AFD1306518C98F5970BABA8`.

O banco persistente não é migrado automaticamente nem utilizado nos testes.
Aplicar migrations ao ambiente real e seu backup continua sendo uma operação separada.
Rollback de schema, se necessário antes de adoção, exige descartar explicitamente
os dados e a tabela nova; não há downgrade destrutivo automático.

## Limites e tarefas futuras

Na entrega original da TH-37 não existiam PUT, PATCH, DELETE, status, cancelamento,
renovação, trancamento, pagamento, inadimplência, carência ou transições de situação.
A TH-38 acrescenta situação derivada e cancelamento histórico por PUT, conforme
`TH-38-regras-matricula.md`, preservando os contratos históricos descritos acima.
TH-40 poderá consumir as quatro
rotas administrativas; TH-41 tratará self-read do Aluno.

Frontend e `api.js` permanecem inalterados. Futuras tarefas precisam tratar precisão
JavaScript: `plano_id`, `matricula_id`/`id` e `valor_contratado_centavos` podem exceder
`Number.MAX_SAFE_INTEGER`; o contrato backend continua int64. O mesmo cuidado vale
para outros IDs e números int64 retornados pela API.
