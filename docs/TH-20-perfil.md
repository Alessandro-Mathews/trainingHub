# TH-20 — Contrato do módulo Perfil

O módulo mantém Controller → Service → Repository → SQLite. As cinco operações
usam callbacks assíncronos do Drogon. O Controller valida o formato do JSON e
converte resultados em HTTP. O Service valida nome, ativo e IDs, decide os
resultados de negócio e traduz exceções de persistência. O Repository mantém SQL
parametrizado e conversão dos registros.

## Rotas e respostas

| Método | Rota | Sucesso |
|---|---|---|
| GET | `/api/perfis` | 200, array ordenado por ID, incluindo inativos |
| GET | `/api/perfis/{id}` | 200, perfil completo |
| POST | `/api/perfis` | 201, mensagem e ID |
| PUT | `/api/perfis/{id}` | 200, mensagem e ID |
| DELETE | `/api/perfis/{id}` | 200, mensagem e ID |

Erros: 400 para entrada inválida; 404 para ID positivo inexistente; 409 para nome
duplicado ou exclusão de perfil utilizado; 500 com mensagem genérica para falhas
inesperadas de banco. Detalhes de falhas inesperadas ficam no log.

As rotas antigas `/perfis` não têm aliases. A busca no repositório antes da
alteração encontrou somente suas declarações no Controller, sem consumidores.

## Criação e atualização

- O corpo deve ser um objeto JSON.
- `nome` é obrigatório e deve ser string com ao menos um caractere que não seja
  espaço ASCII, tabulação ou quebra de linha. Não há limite de tamanho adicional.
- O nome é preservado exatamente, sem trim, normalização ou conversão de caixa.
  A constraint existente diferencia `Admin` de `admin`.
- `ativo` aceita somente os inteiros JSON 0 e 1. Booleanos, strings e números com
  ponto decimal são rejeitados.
- `descricao` aceita string ou null. String vazia permanece string vazia. Null é
  persistido como SQL NULL, sem conversão para string vazia.
- POST pode omitir `ativo` (padrão 1) e `descricao` (SQL NULL).
- PUT exige os três campos editáveis: `nome`, `ativo` e `descricao`. Omissão
  retorna 400 antes de executar SQL. Para limpar a descrição, envie null.
- IDs devem ser positivos e usam 64 bits. ID e data de criação não são editáveis.

Exemplo de PUT completo:

```json
{"nome": "Aluno", "ativo": 0, "descricao": null}
```

`UNIQUE(perfil.nome)` continua sendo a proteção final, inclusive sob concorrência.
O Service traduz `drogon::orm::UniqueViolation` em conflito de negócio; o
Controller responde 409. Não há SELECT prévio usado como garantia de unicidade.

## Exclusão e integridade

DELETE mantém a exclusão física já existente. A FK impede excluir um perfil
referenciado por qualquer usuário, inclusive inativo. O Service traduz
`ForeignKeyViolation` em conflito e o Controller responde 409. A decisão é
atômica no banco, sem uma janela entre consulta prévia e exclusão.

Desativação continua disponível pelo PUT completo com `ativo: 0`. A tarefa não
altera o efeito de perfis inativos sobre login ou sessões; essa regra não foi
adicionada à TH-24. Autorização por perfil permanece fora deste escopo (TH-25).

## Inicialização do SQLite

O Drogon 1.9.13 instalado não expõe no DbClient um inicializador público por
conexão SQLite. `SqliteConfig` registra um inicializador com
`sqlite3_auto_extension`, antes de criar os clientes da aplicação. O SQLite chama
esse inicializador em cada nova conexão, inclusive em outros pools e clientes.

O inicializador configura `SQLITE_DBCONFIG_ENABLE_FKEY`, verifica que o resultado
é 1 e recusa a abertura se não conseguir habilitar a proteção. Também configura
`busy_timeout` de 5000 ms por conexão para tolerar bloqueios breves de escrita.
A espera ocorre no worker SQLite; os handlers HTTP continuam assíncronos.
Bloqueios que excedam esse prazo ainda podem resultar em erro de banco.

Há uma exigência de ordem específica dessa versão: Drogon chama
`sqlite3_config(SQLITE_CONFIG_MULTITHREAD)` na primeira criação de conexão.
Registrar a extensão antes inicializaria SQLite cedo demais e causaria
`SQLITE_MISUSE`. Por isso, a função primeiro abre e fecha um cliente Drogon em
memória, somente para essa configuração inicial. Esse cliente não toca o banco
local nem atende requisições. Depois registra a extensão e inicia os clientes
reais. O SELECT síncrono desse bootstrap ocorre antes de iniciar o servidor.

Não há PRAGMA por requisição, alteração da migration ou alteração dos componentes
de autenticação. A inicialização pressupõe a mesma biblioteca SQLite usada pelo
Drogon, vinculada explicitamente pelo target `SQLite3_lib` fornecido por ele.

Referências: [sqlite3_auto_extension](https://www.sqlite.org/c3ref/auto_extension.html)
e [SQLITE_DBCONFIG_ENABLE_FKEY](https://www.sqlite.org/c3ref/c_dbconfig_defensive.html).
Ao atualizar Drogon, reavaliar a ordem de inicialização e executar os testes de
múltiplas conexões.

## Validação

No ambiente Windows/MSYS2 existente, disponibilize `C:/msys64/ucrt64/bin` e
`build/` no PATH. Com os diretórios de build já configurados:

```text
cmake --build build -j 2
cmake --build build/security-tests -j 2
ctest --test-dir build/security-tests --output-on-failure
python tests/perfil_integration.py
python tests/auth_integration.py
```

Para configurar o projeto de testes pela primeira vez, use `cmake -S tests -B
build/security-tests` com o mesmo gerador, toolchain vcpkg e triplet do build da
aplicação. O projeto de testes permanece separado, conforme a estrutura existente.

`sqlite_foreign_keys_tests` mantém três transações simultâneas em cada um de dois
pools para fixar seis conexões físicas distintas. Consulta `PRAGMA foreign_keys`
e `PRAGMA busy_timeout` em cada uma.

`perfil_integration.py` cria banco e configuração temporários, inicia o servidor
com três conexões e verifica CRUD, IDs de 64 bits, validação, NULL, PUT completo,
duplicidade concorrente, espera por bloqueio de escrita, exclusão referenciada,
erros de banco, health, Academia e login/me/logout. Verifica que o hash do banco
de desenvolvimento não mudou e remove os dados temporários.

`auth_integration.py` e os testes de segurança existentes continuam sendo a
regressão específica da TH-24.
