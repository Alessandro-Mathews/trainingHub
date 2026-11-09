# TH-28 — Interface Web de Autenticação

## Objetivo e arquivos

Login real integrado à sessão existente do Drogon, preservando `index.html`
como dashboard e sem alterar backend, migrations, dependências ou CI.

- `public/login.html`: página de autenticação.
- `public/js/login.js`: validação, loading, mensagens e navegação do login.
- `public/js/api.js`: GET existente, login, contexto e logout.
- `public/js/app.js`: validação de sessão antes das chamadas do dashboard e logout.
- `public/js/academias.js`: estados distintos para 401 e 403.
- `public/css/style.css`: estilos de autenticação e estado de sessão.
- `tests/interface_web.py` e `.mjs`: cobertura ampliada, preservando a TH-21.

## Fluxo e Código da academia

O backend identifica a conta por academia e e-mail. Por isso o formulário tem
três campos: **Código da academia**, **E-mail** e **Senha**. O código corresponde
ao `academia_id` do contrato, sem expor esse nome técnico na interface.

O código deve ser fornecido pela própria academia. Não há ID fixo, descoberta
pública de academias ou alteração da autenticação. Após login, a academia
validada da sessão continua sendo a autoridade para operações tenant-scoped.

O submit envia ao endpoint real:

```text
POST /api/auth/login
Content-Type: application/json
```

```json
{"academia_id":1,"email":"usuario@example.test","senha":"..."}
```

Após HTTP 200, a página limpa a senha, consulta `GET /api/auth/me` e somente
então navega para `/index.html`. Não há redirecionamento controlado por query.
Falhas não causam repetição automática de login.

Ao abrir login, `/me` retorna:

| Resultado | Comportamento |
|---|---|
| 200 | Navegar para `/index.html` |
| 401 | Permanecer no formulário |
| 403 | Mostrar acesso indisponível, sem loop |
| 500/rede | Mostrar falha e permitir tentativa manual de login |

## Sessão e dashboard

Requests usam `credentials: 'same-origin'`, `cache: 'no-store'` e timeout de
15 segundos. A sessão é exclusivamente a existente no servidor, com cookie
`JSESSIONID`. Não há JWT, token próprio ou leitura/escrita manual de cookie.

A configuração atual do backend usa HttpOnly, SameSite Strict, Path `/`, timeout
de 1800 segundos e HTTP local sem Secure. Esta issue não altera esses parâmetros.

O dashboard começa oculto, com estado de verificação de sessão. Antes de chamar
Academias e health, consulta `/me`. Sucesso libera a inicialização. 401 navega
para login; 403 mostra acesso indisponível; erro interno/rede mostra falha com
retry. Esses estados também oferecem saída. Nenhuma Role é inferida de `perfilId`.

`GET /api/academias` continua ADMIN-only. GESTOR, INSTRUTOR e ALUNO autenticados
podem abrir o dashboard, mas veem **Sem permissão** nessa área. Um 403 não é
tratado como sessão expirada. Já um 401 desse recurso oculta o painel e leva ao
login. A autorização permanece integralmente no backend.

**Sair** envia `POST /api/auth/logout`. Após sucesso, navega para `/login.html`.
O botão é protegido contra repetição durante a request. Em falha, não afirma
que a sessão foi encerrada: apresenta erro e permite tentar novamente.

Ao sair da página, o dashboard é ocultado e a senha do login é limpa. Retorno
pelo bfcache provoca reload, reexecutando a validação de sessão. Arquivos HTML
continuam públicos; o gate visual não substitui filtros de autorização da API.

## Validação e int64

Código usa campo textual com teclado numérico, sem conversão para `Number`.
`parseAcademiaCode` aceita somente representação decimal canônica positiva
(`^[1-9][0-9]*$`), sem sinal nem zeros iniciais, com valor entre 1 e
9223372036854775807. Zero, negativos, decimais, espaços, texto e overflow são
rejeitados; códigos como `01` e `0001` não são normalizados nem enviados.

A faixa é verificada com BigInt. O valor decimal validado é emitido diretamente
como número JSON; e-mail e senha são escapados com `JSON.stringify`. Assim o
request representa inclusive INT64_MAX exatamente, sem arredondamento e sem
tentar serializar BigInt diretamente.

As respostas numéricas do backend ainda são lidas pelo parser JSON nativo.
IDs maiores que `Number.MAX_SAFE_INTEGER` podem perder precisão na representação
JavaScript. A página não usa esses IDs para escolher tenant, Role, URL ou conta;
somente verifica a estrutura positiva do contexto. Uma futura interface que
precise reutilizar esses IDs deverá adotar leitura sem perda de precisão.

E-mail usa `type="email"`, `required` e `autocomplete="username"`. Senha usa
`type="password"`, `required` e `autocomplete="current-password"` durante todo
o fluxo. Não há mostrar senha, maxlength arbitrário, transformação de caixa ou
trim manual. A normalização nativa de `input type=email` continua a do navegador.
Senha nunca passa por trim ou normalização.

HTML5 e JavaScript fazem somente validação de UX. Backend continua autoridade
sobre credenciais e permissão. As mensagens de validação estão em português.

## Loading, erros e segurança

Durante submit, flag síncrona impede dupla requisição, botão fica desabilitado,
spinner local e texto **Entrando...** são apresentados, formulário recebe
`aria-busy` e região `aria-live` anuncia o estado. Em erro, controles são
restaurados. A senha é limpa ao terminar a tentativa e antes da navegação.

| Falha | Mensagem |
|---|---|
| Login 401 | Não foi possível entrar. Verifique suas credenciais. |
| Login 400 | Confira os dados informados. |
| Login 500 | Não foi possível entrar agora. Tente novamente. |
| Rede/timeout | Não foi possível conectar ao TrainingHub. |
| Contexto 403 | Sua conta não tem permissão para acessar esta área. |

Não há diferenciação entre usuário inexistente, senha incorreta e vínculos
inativos. Mensagens são locais, aplicadas com `textContent`. Body de erro do
servidor nunca é exibido. `ApiError` preserva somente status HTTP seguro; status
0 representa falha de transporte, abort ou timeout, inclusive durante a leitura
do body (`AbortError`, `TypeError` e `TimeoutError`). JSON inválido em resposta
HTTP bem-sucedida e contexto incompatível recebem 502. Erros HTTP preservam seu
status real antes de qualquer tentativa de leitura do body, mesmo vazio ou não JSON.

Não há senha em log, URL, storage, atributo HTML adicional ou cache próprio.
Não há localStorage/sessionStorage de autenticação, session ID armazenado,
request externa ou redirecionamento arbitrário. O wrapper não redireciona:
cada página decide seu fluxo. O `getJson` existente mantém GET, timeout,
no-store e retorno JSON/rejeição por Error, agora com status disponível.

## Layout, responsividade e acessibilidade

Card central com logo oficial, nome e slogan, cores existentes, botão verde e
fundos claros. Bootstrap 5.3.3 é local; login usa somente seu CSS. Dashboard
preserva o bundle para offcanvas. Poppins continua com fallback, sem download
remoto ou novo arquivo de fonte.

Estilos de autenticação são escopados, preservando sidebar e breakpoints. Em
mobile, card ocupa a largura disponível com margens, controles de pelo menos
46 px e logo proporcional. Layout foi preparado para desktop e 375 px.

Labels têm associação explícita, campos têm IDs e names, foco é visível e ordem
de teclado é natural. Erros de campo usam validação nativa e `aria-invalid`.
Feedback possui `aria-live`; falhas de autenticação recebem foco na mensagem.
Spinner é decorativo com `aria-hidden`. Loading não depende somente da animação.

## Testes e resultados

`python tests/interface_web.py` preserva os checks HTTP da TH-21 e adiciona:

- Leitura estrutural de HTML, campos, required/autocomplete, feedback/loading
  acessível e assets locais.
- Login, credenciais inválidas, `/me`, logout, cookies, 401/403 e isolamento,
  usando servidor real e SQLite temporário.
- Código int64 máximo enviado ao backend com representação exata.
- Quando Node está disponível, testes do módulo API com fetch simulado: faixa
  int64, rejeição de zeros iniciais e demais formatos não canônicos sem request,
  body exato, escaping, status HTTP, rede/timeout e contexto inválido. Falhas de
  transporte na leitura do body são distintas de JSON inválido; login e `/me`
  exercitam a mensagem de conexão e a recuperação dos controles nesses casos.
- Testes dos módulos entregues com DOM simulado: login, loading, submit duplo,
  erros, gate de sessão, logout e distinção de recurso 401/403.

Node não é uma dependência nova instalada pelo teste. Sua ausência é informada
como checks JS indisponíveis; HTML/HTTP continuam executando. Testes com DOM
simulado não comprovam renderização, layout, validação nativa real ou APIs de
acessibilidade do navegador.

`python tests/interface_web.py --browser` usa a infraestrutura Chrome/CDP nativa
existente, sem npm. A suíte foi ampliada para formulário real, teclado,
desktop/mobile, loading/submit duplo, login inválido/válido, redirecionamentos,
logout, 403 sem loop e ausência de credenciais em URL/storage. Cenários anteriores
de Academias foram mantidos; a expectativa de erro genérico para 401 passou a
verificar revogação real da sessão e redirecionamento aprovado para login.

Validação nesta implementação:

- Build da aplicação e testes aprovado; CTest 3/3.
- Interface HTTP, HTML e testes JavaScript/DOM simulado aprovados.
- Suíte browser tentou executar, mas falhou em `CDP timeout: Page.enable` antes
  da navegação. É a limitação ambiental já registrada na TH-21; não equivale a
  aprovação dos novos cenários visuais/interativos. Não houve screenshot novo
  da aplicação nessa tentativa.
- Backend e workflow preservados; CI continua executando o script HTTP ampliado.

Os testes usam SQLite temporário e comparam o SHA-256 de `data/traininghub.db`.
Não há migrations ou dados aplicados ao banco local por esta entrega.

## Fora do escopo

Cadastro, recuperação/mudança de senha, lembrar de mim, mostrar senha, OAuth,
JWT, MFA, CAPTCHA, RBAC completo e interfaces de Aluno/Instrutor. Nenhuma
autenticação paralela, dependência nova ou mudança de contrato backend.
