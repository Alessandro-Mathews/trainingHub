# TH-38 — Regras de negócio do ciclo de vida da Matrícula

## Estados e vigência

`MatriculaService::determinarSituacao(matricula, agoraUtc)` recebe um instante
explícito, sem consultar relógio global. A situação é derivada, nunca persistida:

- `CANCELADA`: `cancelado_em` preenchido, com precedência sobre o tempo.
- `ATIVA`: sem cancelamento e `data_inicio <= agoraUtc < data_fim`.
- `INATIVA`: sem cancelamento e fora da vigência, inclusive antes do início.

TH-37 continua criando contratos de início imediato. Tempo torna a matrícula
inativa; cancelamento de ativa a torna cancelada. Cancelamento é terminal.
Não existe reativação ou renovação da mesma linha. Novas contratações criam novas
linhas, sem exclusividade por Aluno, Plano ou período.

## Persistência e representação

`008_matricula_cancelamento.sql` acrescenta somente `cancelado_em DATETIME NULL`.
Migrations 001–007 permanecem intactas. O ADD COLUMN inclui CHECK nullable para
timestamp reconhecido e canônico, com 19 caracteres, maior ou igual ao início e
menor que o fim. Cancelamento no segundo da criação é permitido. Não há trigger,
reconstrução de tabela, boolean de atividade, enum persistido ou job de expiração.

O Model usa `std::optional<std::string>`. O mapper preserva validações anteriores
e rejeita cancelamento vazio, data inválida ou cancelamento fora da vigência.
POST, três GETs e cancelamento retornam todos os campos da TH-37 e acrescentam:

```json
{"cancelado_em": null, "situacao": "ATIVA"}
```

Após cancelamento, o timestamp aparece como texto UTC e a situação é `CANCELADA`.
Esta ampliação exige atualização de consumidores que validem chaves exatas.

## Relógio e responsabilidades

SQLite é a única autoridade temporal. Datas usam `YYYY-MM-DD HH:MM:SS`, UTC,
precisão de segundos e intervalo `[inicio,fim)`. POST usa o instante de início
retornado pelo INSERT. Consultas materializam um único instante SQLite em CTE,
compartilhado por todas as linhas da resposta. Nenhuma situação HTTP depende do
relógio C++.

Repository transporta registro e instante; Service classifica e valida transições;
Controller serializa o resultado classificado e mapeia HTTP. O predicado repetido
no SQL protege atomicidade, enquanto a decisão funcional permanece no Service.

## Cancelamento HTTP

`PUT /api/matriculas/{id}/cancelamento` não recebe query nem body, incluindo `{}`.
Não exige Content-Type. ID deve ser inteiro positivo int64. Cliente não fornece
timestamp, situação, tenant, snapshot ou datas. Autorização antecede parsing.

Reutiliza `MatriculasManage`: ADMIN/GESTOR podem cancelar no tenant autenticado;
INSTRUTOR/ALUNO/UNKNOWN recebem 403. Sessão ausente ou inválida recebe 401.
AuthorizationService e valores das Operations permanecem inalterados.

| Cenário | HTTP | Efeito |
| --- | --- | --- |
| Ativa local | 200 + objeto completo | Primeiro timestamp persistido |
| Cancelada ou inativa | 409 | Nenhuma alteração |
| Inexistente ou externa | 404 indistinguível | Nenhuma alteração |
| ID inválido, query ou body | 400 | Nenhuma alteração |
| Falha interna inesperada | 500 sanitizado | Não converter genericamente para conflito |

Respostas mantêm JSON e `Cache-Control: no-store`.

## Atomicidade, concorrência e histórico

Service consulta matrícula local com instante SQLite, determina situação e só
solicita cancelamento de ativa. UPDATE ... RETURNING restringe ID, tenant,
ausência de cancelamento, vigência e consistência dos pais com a academia.
O timestamp e a vigência são avaliados no instante efetivo da escrita.

Se o estado mudar ou a vigência terminar entre leitura e escrita, UPDATE não
retorna linha e Service responde 409. Não reutiliza instante antigo para prolongar
vigência. Duas tentativas concorrentes produzem um 200 e um 409, sem sobrescrever
o primeiro timestamp. Repetição mantém efeito idempotente, com resposta 409.

Cancelamento modifica somente `cancelado_em`. IDs, academia, snapshot comercial,
`data_inicio`, `data_fim` e `criado_em` permanecem intactos. `data_fim` representa
vigência originalmente contratada. GET individual e listas geral/por Aluno
continuam expondo histórico, inclusive após vencimento, cancelamento ou mudanças
de atividade dos pais. Relações inconsistentes entre tenants não são expostas.

## Testes e operação

`tests/matricula_ciclo_vida_tests.cpp` verifica fronteiras e precedência da função
do Service com instantes fixos. Não usa framework novo ou relógio real para esses
casos. Registro no CTest reutiliza a execução existente no CI.
O mesmo executável exercita o Repository real em SQLite em memória com migrations
007–008: após uma leitura ativa, a fixture altera a vigência para encerrada e prova
que a escrita recusa o cancelamento. Também verifica tenant e rejeição de segunda
escrita, mantendo o primeiro timestamp.

`tests/matricula_integration.py` preserva regressão TH-37 e amplia cobertura para
migration aditiva com linha anterior, NULL, CHECKs, situações, cancelamento,
timestamp servidor, histórico, tenants, Roles, contratos HTTP e concorrência.
A fixture aplica até 006, prova 007 e aplica posteriores em ordem. Campos públicos,
persistidos e datas obrigatórias são tratados separadamente.

Expiração e início futuro usam datas controladas em banco temporário. Não há sleep
para acertar fronteiras nem hook de produção. A janela HTTP exata entre pré-leitura
e vencimento não é forçada; o UPDATE condicionado protege a fronteira.

Build, CTest e regressões HTTP devem executar antes da revisão. Testes usam bancos
isolados e verificam SHA-256 de `data/traininghub.db`; migrations não são aplicadas
automaticamente nesse banco. CI e CMake principal não precisam mudar.

Validação local em 2026-11-28, branch `feature/TH-38-regras-matricula`, base
`1c2ae59`: build limpo da aplicação e dos testes aprovado; CTest 4/4. O novo alvo
cobre oito casos determinísticos do Service e três grupos de proteção do Repository.
Matrícula passou com 324 verificações HTTP, preservando as 231 da TH-37 e
acrescentando 93. Regressões aprovadas: Plano 397, Aluno 147, Instrutor 155,
vínculo 212, TH-34 865, Authorization 247, Usuario/TH-63 379, Perfil 138 e Auth.
As quatro suítes de interface existentes no CI também passaram.

Comandos de build: `cmake -S tests -B build/security-tests`,
`cmake --build build --clean-first --parallel 2` e
`cmake --build build/security-tests --clean-first --parallel 2`.
Validação usa `ctest --test-dir build/security-tests --output-on-failure --no-tests=error`
e as mesmas entradas Python do CI, com PATH para UCRT64 e dependências locais.

SHA-256 do banco persistente antes e depois:
`10C935F52AD5FEADA7F2C25D9257CCBB01CC076D7AFD1306518C98F5970BABA8`.

## Limites

Sem frontend, `api.js`, pagamentos, cobranças, parcelas, inadimplência, estornos,
trancamento, DELETE, reativação, scheduler ou self-read. Cancelamento não implica
operação financeira. TH-40 tratará interface administrativa; TH-41, consulta do Aluno.
