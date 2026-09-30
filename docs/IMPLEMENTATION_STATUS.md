# TrainingHub - Status de Implementação

## Etapa atual

Base inicial do módulo Academia: leitura assíncrona com separação Controller → Service → Repository → Drogon ORM → SQLite.

## Ambiente

- Sistema: Windows + MSYS2 UCRT64
- Linguagem: C++20
- Compilador: GCC/G++ 16.2.0
- Build system: CMake 4.4.3
- Gerador CMake: Ninja
- Gerenciador de dependências: vcpkg em C:/Projetos/vcpkg
- Triplet: x64-mingw-dynamic
- Framework backend: Drogon 1.9.13, compilado com ORM + SQLite
- Banco: SQLite integrado ao Drogon, DbClient `default`
- Banco local: `./data/traininghub.db`

## Concluído

- Integração CMake + vcpkg + GCC + Drogon validada.
- Servidor configurado em `127.0.0.1:8080`.
- Estrutura `include/traininghub` utilizada para headers públicos.
- Migration `001_initial_schema.sql` criada, aplicada e validada.
- Tabelas `academia`, `perfil` e `usuario` existentes.
- Foreign keys de `usuario` para `academia` e `perfil` verificadas; `PRAGMA foreign_key_check` sem violações.
- Endpoint `GET /api/health` implementado e validado.
- Endpoint `GET /api/health/database` validado com `SELECT 1` pelo Drogon ORM.
- Model `Academia` criado, com ID de 64 bits e campos anuláveis representados por `std::optional<std::string>`.
- `AcademiaRepository::findAll` consulta os sete campos da tabela, ordenados por ID, usando callbacks assíncronos.
- `AcademiaService::listAll` delega a leitura ao Repository.
- `GET /api/academias` implementado com conversão para JSON somente no Controller.
- CMake atualizado com os novos arquivos de implementação.
- Banco, arquivos auxiliares SQLite, builds, DLLs e executáveis cobertos pelo `.gitignore`.

## Contrato de GET /api/academias

Sucesso: HTTP 200 com array JSON, ordenado por `id`. Sem registros, retorna `[]`.
Cada objeto contém `id`, `nome`, `cnpj`, `email`, `telefone`, `ativo` e `criado_em`.
Campos SQL NULL permanecem `null` no JSON. `ativo` é booleano; `criado_em` preserva o texto do SQLite.
Erro de banco: HTTP 500 com `{"message":"Erro ao listar academias."}`. Detalhes ficam no log do servidor.
Os callbacks HTTP são copiados para os caminhos de sucesso e erro, sem movimentação dupla.

## Validação executada

- `cmake --build build` concluído com sucesso, usando GCC/MSYS2 UCRT64 e a configuração existente.
- Banco existente inspecionado em modo somente leitura: tabelas e foreign keys verificadas.
- Teste HTTP isolado em `127.0.0.1:18080`, com banco temporário criado pela migration existente.
- Health e conexão de banco retornaram HTTP 200.
- Listagem vazia, registros completos, campos NULL, string vazia, ID de 64 bits, ordem por ID, booleanos e data verificados.
- Falha SQL simulada somente no banco temporário retornou HTTP 500 com mensagem genérica.

## Testes manuais

1. Na raiz `trainingHub`, disponibilize `C:/msys64/ucrt64/bin` no PATH e execute `cmake --build build`.
2. Execute `./build/traininghub.exe` a partir da raiz, onde estão `config.json` e `data/`.
3. Consulte `http://127.0.0.1:8080/api/health`: espere HTTP 200 e status `ok`.
4. Consulte `http://127.0.0.1:8080/api/health/database`: espere HTTP 200 e database `connected`.
5. Consulte `http://127.0.0.1:8080/api/academias`: espere HTTP 200 com array, possivelmente vazio.
6. Em banco de teste com registros, confira os sete campos, ordem por ID, `null` e valores booleanos.
7. Para verificar HTTP 500, use uma instância isolada com banco de teste sem a tabela `academia`.

## Limites desta etapa

Somente leitura de Academia. Autenticação, JWT, cadastro/login, outros módulos, frontend e CRUD completo não foram implementados.
Configuração do Drogon e migration existente preservadas. Nenhuma biblioteca adicionada.
