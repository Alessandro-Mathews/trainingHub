# TH-19 — Módulo Usuário

Arquitetura: `UsuarioController → UsuarioService → UsuarioRepository → SQLite`.
O Model e o Repository da TH-24 foram reutilizados; somente o Repository foi ampliado.
Todos os acessos ao banco usam callbacks assíncronos e SQL parametrizado.
Controller valida HTTP/JSON e serializa respostas; Service concentra regras,
hash e tradução de exceções; Repository concentra SQL e mapeamento de registros.

## Endpoints

| Método | Rota | Sucesso |
|---|---|---|
| POST | `/api/usuarios` | 201, usuário criado |
| GET | `/api/usuarios?academia_id=1` | 200, array ordenado por ID |
| GET | `/api/usuarios/{id}?academia_id=1` | 200, usuário da academia informada |

Cadastro:

```json
{
  "academia_id": 1,
  "perfil_id": 1,
  "nome": "João Silva",
  "email": "joao@example.test",
  "senha": "senha-do-usuario"
}
```

Resposta de cadastro e busca individual:

```json
{
  "id": 1,
  "academia_id": 1,
  "perfil_id": 1,
  "nome": "João Silva",
  "email": "joao@example.test",
  "ativo": true,
  "criado_em": "2026-10-26 12:00:00"
}
```

Erros usam `{"erro":"mensagem"}`: 400 para estrutura/dados inválidos ou vínculo
inativo; 404 para Academia/Perfil inexistente no cadastro ou usuário não encontrado
na academia consultada; 409 para e-mail duplicado ou FK perdida entre validação e
INSERT; 500 com mensagem genérica para falhas inesperadas e de conversão.

## Regras

- O corpo precisa ser objeto JSON com os cinco campos obrigatórios.
- IDs JSON aceitam somente inteiros positivos de 64 bits com sinal; rejeitam
  booleanos, strings, números decimais e overflow. IDs na URL/query aceitam
  representação decimal positiva, sem espaços, sinal `+` ou sufixos.
- `nome`, `email` e `senha` precisam ser strings. Nome exige ao menos um
  caractere diferente de espaço ASCII, tabulação ou quebra de linha, conforme Perfil.
- E-mail exige exatamente um `@`, conteúdo antes e depois, sem espaços ASCII,
  tabulação, quebras de linha ou byte NUL. Não há validação completa RFC/DNS,
  exigência de ponto no domínio ou dependência de serviço externo.
- Nome e e-mail são preservados exatamente, sem trim ou conversão de caixa.
  O schema usa a comparação existente do SQLite: `Usuario@example.test` e
  `usuario@example.test` são distintos. O login também mantém comparação exata.
- Senha exige somente string não vazia. Não há política formal de complexidade
  ou tamanho; espaços são aceitos. `PasswordHasher::hash()` da TH-24 gera Argon2id.
- `senha_hash` no request é rejeitado. Senha/hash nunca integram respostas HTTP.
  ID, estado ativo e data são gerados pelo backend/banco; novos usuários são ativos.
- Academia e Perfil devem existir e estar ativos no momento da validação.
  Academia mantém o conceito booleano existente; Perfil precisa ter `ativo = 1`.
  Reutiliza-se `PerfilRepository::buscarPorId` e adiciona-se a busca individual
  ao `AcademiaRepository`, sem SQL desses módulos no UsuarioRepository.

## Multi-academia, concorrência e autenticação

GET exige `academia_id` explícito. Todas as consultas filtram por academia no SQL.
Listagem sem usuários retorna `[]`, inclusive para academia inexistente. Busca
individual com academia diferente retorna 404, sem revelar outro registro.
Listagens incluem usuários inativos. A query não comprova pertencimento do
solicitante: autorização e RBAC continuam reservados à TH-25.

`UNIQUE(academia_id, email)` é a proteção final, sem SELECT prévio de duplicidade.
E-mail repetido na mesma academia retorna 409; academias distintas podem repetir
o e-mail. `UniqueViolation` e `ForeignKeyViolation` tornam-se erros de negócio no
Service. A solução `SqliteConfig` da TH-20 permanece intacta, sem novo PRAGMA.
FK protege existência dos vínculos mesmo se o pai desaparecer após validação.
O estado ativo é validado antes do INSERT, sem nova garantia transacional contra
desativação concorrente. Não se altera o efeito de desativação sobre sessões/login.

`findByAcademiaAndEmail` mantém assinatura, SQL e resultado usados pela TH-24.
Seu mapeamento agora também captura falhas de conversão, como as novas consultas.
Dados incompatíveis geram erro controlado sem derrubar o event loop.
Cadastro não autentica nem altera sessão. O usuário criado pode usar
`POST /api/auth/login`, `GET /api/auth/me` e `POST /api/auth/logout` existentes.
PasswordHasher, AuthController, AuthService e SessionManager permanecem intactos.

## Verificação

No ambiente existente Windows/MSYS2, com `C:/msys64/ucrt64/bin` e `build/` no PATH:

```text
cmake --build build -j 2
cmake --build build/security-tests -j 2
ctest --test-dir build/security-tests --output-on-failure
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/auth_integration.py
git diff --check
```

Os builds reutilizam a configuração CMake/vcpkg existente. O projeto CTest continua
separado em `tests/`, conforme TH-20. Os testes HTTP são executados pelos scripts.

`usuario_integration.py` inicia servidor com banco/configuração temporários e pool
de três conexões. Verifica cadastro, estrutura/tipos, regras semânticas, inativos,
IDs de 64 bits, isolamento da consulta, caixa do e-mail, senha Argon2id e ausência
de credenciais nas respostas/logs, cadastro/login/me/logout, UNIQUE concorrente,
FK após validação, mapeamentos incompatíveis, erros de banco e health checks.
O teste da FK usa trigger temporária para remover o Perfil durante o INSERT;
a FK rejeita a operação e o rollback preserva o Perfil. O teste confirma o hash
inalterado de `data/traininghub.db` e remove os dados temporários.

Validação executada: build real aprovado; CTest 2/2; TH-19 136 verificações HTTP;
TH-20 138 verificações HTTP; TH-24 aprovada. Health, Academia, Perfil, autenticação,
UNIQUE e FK preservados. `git diff --check` sem erros. Nenhuma migration,
dependência ou configuração de autenticação foi alterada.

Para revisão humana: contrato explícito de academia, comparação exata do e-mail,
senha apenas não vazia e rejeição de vínculos inativos. Consultas exigem academia,
mas não fornecem autorização; o estado ativo pode mudar após validação.
