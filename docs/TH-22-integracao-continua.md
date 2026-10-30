# TH-22 — Integração contínua

## Objetivo e eventos

O workflow `.github/workflows/ci.yml`, chamado **TrainingHub CI**, verifica
configuração, compilação e testes. Executa em Pull Requests com destino à `main`,
pushes na `main` e manualmente por `workflow_dispatch` na aba Actions, quando o
workflow estiver disponível na branch padrão.

Uma falha de configure, build ou teste interrompe a execução e reprova o job.
Os comandos Bash usam `set -euo pipefail`; o bootstrap PowerShell propaga o
código de saída. Não há `continue-on-error`. O resultado definitivo depende
da execução real no GitHub; validação local não equivale à aprovação do Actions.

## Ambiente e dependências

- Runner `windows-2022`, com MSYS2 **UCRT64**, GCC/G++, C++20, CMake e Ninja.
- Python UCRT64 com `sqlite3`; os testes não precisam de pacotes Python externos.
- `actions/checkout@v6` e `msys2/setup-msys2@v2`, referenciadas pelas respectivas
  versões major. Não há SHA pinning dessas actions.
- MSYS2 instala `git`, `mingw-w64-ucrt-x86_64-gcc`,
  `mingw-w64-ucrt-x86_64-cmake`, `mingw-w64-ucrt-x86_64-ninja` e
  `mingw-w64-ucrt-x86_64-python`.
- `path-type: minimal` preserva ferramentas básicas do Windows e evita herdar
  outros compiladores. Os comandos de build usam o shell `msys2 {0}` em UCRT64.
- `PYTHONUTF8=1` evita depender da página de código do Windows.

O vcpkg é obtido em `build/vcpkg` no commit
`e456309491fd875487bf02b8a0dca76c1b1b00cc`, também usado como `builtin-baseline`
em `vcpkg.json`. Esse baseline resolve:

| Dependência direta | Versão do baseline | Uso |
|---|---|---|
| `drogon`, sem default features, com `orm` e `sqlite3` | `1.9.13#2` | HTTP e ORM SQLite |
| `sqlite3` | `3.53.4#2` | API SQLite usada diretamente e pelo Drogon |
| `argon2` | `20190702#1` | Hash de senhas |

Trantor, JsonCpp, Brotli, zlib, c-ares, OpenSSL e helpers CMake são dependências
transitivas. Não são adicionados MySQL, PostgreSQL, Redis ou ferramentas frontend.
O vcpkg resolve e instala o manifest durante o configure CMake.

Target e host usam `x64-mingw-dynamic` explicitamente. O compilador UCRT64 fica
no início do PATH; não se usa MSVC nem `x64-windows`. O triplet MinGW é comunitário
no vcpkg. Atualizações devem ser verificadas antes de trocar o baseline.
Esse triplet inclui o PATH no cálculo de ABI: mantenha o mesmo PATH nos dois
configures para evitar recompilar dependências. O workflow acrescenta os caminhos
das DLLs somente na etapa de execução dos testes.

Não há cache binário vcpkg (`VCPKG_BINARY_SOURCES=clear`) nem cache do setup MSYS2.
O primeiro build instala as dependências a partir dos fontes. Downloads de
ferramentas e fontes exigem acesso à rede. O baseline fixa os ports; o runner,
as actions major e os pacotes atualizados do MSYS2 não são imagens imutáveis.

## Etapas e caminhos

1. Checkout do TrainingHub, sem persistir credenciais Git.
2. Preparação do MSYS2 UCRT64.
3. Checkout fixado do vcpkg, também sem persistir credenciais, e bootstrap.
4. Verificação do módulo Python `sqlite3` e configure dos dois projetos CMake.
5. Build da aplicação e dos executáveis de teste, com paralelismo 2.
6. CTest e quatro suítes HTTP isoladas.

O projeto da raiz produz `build/traininghub.exe`. O projeto `tests/` é
independente: produz `build/security-tests/security_tests.exe` e
`build/security-tests/sqlite_foreign_keys_tests.exe`. Configurar somente a raiz
não registra os testes C++.

Ambos compartilham `build/vcpkg_installed`, dentro do diretório já ignorado pelo
Git. `VCPKG_MANIFEST_DIR` aponta explicitamente para a raiz em ambos os configures.
Os caminhos CMake são convertidos com `cygpath -m` e argumentos são protegidos
por aspas/arrays para suportar espaços no workspace.

Durante os testes, o PATH inclui o `bin` do triplet instalado, `tools/openssl`,
`build/` e o ambiente UCRT64. Isso disponibiliza DLLs de dependências e runtime
sem exigir cópias manuais provenientes da máquina de desenvolvimento.

## Testes e banco

O CTest executa `security` e `sqlite_foreign_keys` com
`--output-on-failure --no-tests=error`. Encontrar zero testes reprova a CI.
As verificações C++ usam exceções/códigos de saída e continuam ativas em Release.

Depois são executados, em sequência:

```text
python tests/interface_web.py
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/auth_integration.py
```

O teste da interface verifica servidor, HTML, assets/MIME, logo, API real,
health checks, lista preenchida/vazia e proteção dos arquivos privados.
As demais suítes cobrem Usuários, Perfis e autenticação, incluindo validações,
integridade e isolamento entre academias.

Cada suíte HTTP inicia seu servidor em porta local livre, cria banco e
configuração temporários em `build/`, aplica a migration existente e encerra o
servidor ao terminar. O teste C++ SQLite usa banco em memória. Não é necessário
criar, copiar ou aplicar migrations em `data/traininghub.db` para executar a CI.
Se esse banco existir localmente, os scripts verificam sua preservação; Auth
também pode inspecionar seu schema em modo somente leitura.

Chrome/CDP, `interface_web.mjs` e `interface_web.py --browser` ficam fora da CI.
Não se instala Node/npm, Playwright, Selenium ou dependências frontend novas.
**Resultado visual, responsividade e comportamento no navegador não são
validados por esta CI.** Continuam sujeitos à validação manual da interface.

## Reproduzir localmente

Use Windows com MSYS2 UCRT64 e os pacotes listados acima. Na raiz do projeto,
abra o terminal UCRT64 e prepare o vcpkg fixado, caso ainda não exista:

```bash
mkdir -p build
git clone https://github.com/microsoft/vcpkg.git build/vcpkg
git -C build/vcpkg checkout --detach e456309491fd875487bf02b8a0dca76c1b1b00cc
```

Execute o bootstrap em PowerShell, na mesma raiz:

```powershell
& ./build/vcpkg/bootstrap-vcpkg.bat -disableMetrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

De volta ao terminal **UCRT64**, execute os comandos abaixo. Use diretórios de
build novos se o build existente estiver configurado com outro toolchain.
Não misture dependências MSVC, MINGW64 e UCRT64.

```bash
set -euo pipefail
test "$MSYSTEM" = UCRT64
export VCPKG_DEFAULT_TRIPLET=x64-mingw-dynamic
export VCPKG_DEFAULT_HOST_TRIPLET=x64-mingw-dynamic
export VCPKG_BINARY_SOURCES=clear
export VCPKG_DISABLE_METRICS=1
export PYTHONUTF8=1
workspace="$(cygpath -m "$PWD")"
python -c "import sqlite3; print('Python SQLite:', sqlite3.sqlite_version)"
options=(
  -G Ninja
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_C_COMPILER=gcc
  -DCMAKE_CXX_COMPILER=g++
  "-DCMAKE_TOOLCHAIN_FILE=$workspace/build/vcpkg/scripts/buildsystems/vcpkg.cmake"
  -DVCPKG_TARGET_TRIPLET=x64-mingw-dynamic
  -DVCPKG_HOST_TRIPLET=x64-mingw-dynamic
  "-DVCPKG_MANIFEST_DIR=$workspace"
  "-DVCPKG_INSTALLED_DIR=$workspace/build/vcpkg_installed"
)
cmake -S . -B build "${options[@]}"
cmake -S tests -B build/security-tests "${options[@]}"
cmake --build build --parallel 2
cmake --build build/security-tests --parallel 2
installed="$PWD/build/vcpkg_installed/x64-mingw-dynamic"
export PATH="$installed/bin:$installed/tools/openssl:$PWD/build:$PATH"
ctest --test-dir build/security-tests --output-on-failure --no-tests=error
python tests/interface_web.py
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/auth_integration.py
```

Não execute Python com `-O`: as suítes existentes usam `assert`.

## Interpretar falhas e permissões

- **Checkout/setup/bootstrap:** verificar rede, disponibilidade das actions,
  downloads MSYS2 e ferramentas do vcpkg.
- **Configure:** verificar instalação do manifest, baseline, triplets e logs
  `vcpkg-manifest-install.log` no diretório de build correspondente.
- **Compilação/link:** consultar o primeiro erro GCC; confirmar UCRT64 e ausência
  de bibliotecas de outro toolchain.
- **DLL/servidor não inicia:** verificar PATH e logs dos testes; não solucionar
  copiando DLLs pessoais para o repositório.
- **CTest:** consultar a saída do teste reprovado. Zero testes é erro.
- **HTTP:** consultar traceback/assertion e logs temporários enquanto disponíveis.
  Falhas de integridade ou concorrência não devem ser mascaradas por retries no CI.

O workflow usa somente `permissions: contents: read`, sem permissões de escrita,
PAT, secrets personalizados, credenciais de banco ou APIs externas da aplicação.
O `GITHUB_TOKEN` automático atende ao checkout. Downloads de dependências são
separados das consultas locais realizadas pelos testes.

Após publicação autorizada da branch, conferir os checks do PR na aba Actions.
Depois da integração, conferir também o evento push na `main`. O status é
publicado pelo próprio GitHub; não requer `checks: write` ou `statuses: write`.

## Validação local da implementação

- JSON, resolução do manifest e instalação das dependências: aprovados.
- YAML/GitHub Actions: aprovado com actionlint 1.7.7; blocos Bash e PowerShell
  também tiveram a sintaxe verificada. Conversão de caminho com espaços aprovada.
- Configures e builds Release da aplicação e de `tests/`: aprovados em diretórios
  novos sob `build/th22/`, compartilhando `build/vcpkg_installed`.
- CTest: exatamente `security` e `sqlite_foreign_keys`, ambos aprovados.
- HTTP TH-21, Usuários (146 verificações), Perfis (138) e Auth: aprovados.
- As quatro suítes Python foram executadas em cópias idênticas dos arquivos
  originais, em `build/th22/clean-runtime`, sem `data/traininghub.db`.
  Os builds locais desativaram cópia automática de DLLs para confirmar resolução
  pelo PATH, sem DLLs ao lado dos executáveis.
- A instalação local recompilou as bibliotecas sem cache binário. Como downloads
  diretos estavam restritos, reutilizou arquivos de fontes e ferramentas já
  baixados. Bootstrap/downloads em máquina limpa e eventos do GitHub ainda
  precisam da execução real no runner. Nenhuma execução Actions foi aprovada localmente.
