# TH-21 — Estrutura inicial da interface web

## Objetivo e escopo

Base administrativa responsiva em HTML5, CSS3, JavaScript e Bootstrap 5, com
Dashboard e consulta real de Academias. Não inclui autenticação de interface,
RBAC/TH-25, formulários de cadastro, edição ou exclusão, nem dados fictícios.
Usuários e Perfis aparecem desabilitados, identificados como “Em breve”.

## Estrutura e arquivos

```text
public/
  index.html
  css/style.css
  js/api.js
  js/app.js
  js/academias.js
  images/traininghub-logo.png
  vendor/bootstrap/
    bootstrap.min.css
    bootstrap.bundle.min.js
    LICENSE
tests/
  interface_web.py
  interface_web.mjs
```

- `index.html`: sidebar, topbar, Dashboard e seção Academias, com HTML semântico.
- `style.css`: identidade visual, componentes e adaptação de layout.
- `api.js`: GET JSON na mesma origem, verificação HTTP e timeout de 15 segundos.
- `academias.js`: carregamento, validação da resposta, renderização e estados.
- `app.js`: navegação por hash, logo e consulta independente dos health checks.

## Servir e executar

Na análise inicial, `public/` continha somente o logo; não havia `templates/`,
frontend ou dependências frontend. `src/main.cpp` já carrega `config.json`.
O Drogon usa seu servidor de arquivos estáticos, sem controller adicional.

Alteração de configuração restrita a uma propriedade de `app`:

```json
"document_root": "./public"
```

A página inicial padrão do Drogon já é `index.html`, dispensando configuração
adicional. A raiz estática antes não apontava para `public/`. Agora `/` entrega
`public/index.html`, e `/css/`, `/js/`, `/images/` e `/vendor/` resolvem dentro
de `public/`. As rotas `/api/` continuam atendidas pelos controllers existentes.
Controllers, services, repositories, autenticação, CMake, schema e migrations
não foram alterados. Não coloque configuração, banco ou segredos em `public/`.

Com o ambiente C++/Drogon/vcpkg e banco já preparados, faça build e execute
**a partir da raiz do repositório**, conforme os caminhos relativos existentes:

```powershell
$env:PATH = "C:\msys64\ucrt64\bin;C:\Projetos\trainingHub\build;" + $env:PATH
cmake --build build -j 2
.\build\traininghub.exe
```

Acesse `http://127.0.0.1:8080/`, `/#dashboard` ou `/#academias`.
O botão Atualizar listagem repete a consulta; a troca de seção não recarrega a página.
Hashes desconhecidos mostram Dashboard. Não é necessário Node/npm para executar
ou construir a interface.

## Bootstrap, fonte e identidade

Bootstrap **5.3.3** oficial foi copiado para `public/vendor/bootstrap/`, com
licença MIT. CSS e bundle JavaScript são servidos localmente, sem CDN.
Origem dos arquivos: repositório `twbs/bootstrap`, tag `v5.3.3`, caminhos
`dist/css/bootstrap.min.css`, `dist/js/bootstrap.bundle.min.js` e `LICENSE`.
Não há chamadas a APIs externas ou download de dependências no navegador.

Variáveis CSS centralizam as cores oficiais: `#0F172A`, `#22C55E`, `#16A34A`,
`#94A3B8`, `#E2E8F0` e branco. Sidebar escura, conteúdo claro, bordas discretas
e verde reservado a ações, navegação ativa e indicadores. Textos auxiliares em
fundos claros usam cinza mais escuro para manter contraste.

Poppins é a primeira opção da pilha. Como o repositório não contém a fonte,
usa a Poppins instalada no dispositivo ou o fallback permitido:
`system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
Nenhuma fonte foi baixada. Para garantir Poppins em todos os dispositivos,
uma etapa futura deverá fornecer arquivos locais licenciados e `@font-face`.

## Logo oficial

O logo oficial está em `public/images/traininghub-logo.png`.
O HTML usa exatamente:

```html
<img id="brand-logo" src="/images/traininghub-logo.png"
     alt="Logo TrainingHub" width="48" height="48">
```

Se não carregar, a imagem é ocultada e o nome TrainingHub permanece visível.
Para substituir a arte, coloque o logo oficial nessa mesma pasta e nome.
O favicon e o teste HTTP também usam `traininghub-logo.png`.
O slogan utilizado é “Sua evolução em um só lugar”.

## Contratos e estados

`GET /api/academias` retorna **array diretamente**, sem envelope. Campos reais:
`id`, `nome`, `cnpj`, `email`, `telefone`, `ativo` e `criado_em`.
A tabela exibe ID, nome, CNPJ, contato (email/telefone) e status derivado
do booleano `ativo`. `criado_em` existe, mas foi omitido da apresentação inicial.
Valores de contato nulos aparecem como “Não informado”. Conteúdo da API é
inserido com `textContent`, preservando texto sem executar HTML.

- Loading: spinner, “Carregando academias...”, `aria-busy` e atualização desabilitada.
- Lista preenchida: tabela e total calculado somente com o tamanho do array.
- Lista vazia: “Nenhuma academia cadastrada.” e total zero.
- Erro HTTP, rede, timeout ou contrato inválido: mensagem genérica e botão
  “Tentar novamente”; sem SQL, stack trace ou detalhes internos. Contagem volta
  ao estado neutro. Retry utiliza a mesma função de carregamento.

Dashboard consulta `GET /api/health`: só mostra Operacional quando `status` é
`ok` e `application` é `TrainingHub`. Consulta também `/api/health/database`:
só mostra Conectado quando `status` é `ok` e `database` é `connected`.
Falhas nessas consultas mostram Indisponível sem bloquear Academias.
Não há números de usuários, perfis, alunos ou receita simulados.

## Responsividade e acessibilidade

Sidebar fixa a partir de 992px. Abaixo disso, Bootstrap Offcanvas abre pelo
botão de menu, mantém foco no menu aberto e fecha por botão, Escape, backdrop
ou navegação. Cards empilham em telas menores; tabela tem rolagem horizontal
restrita ao seu contêiner, sem alargar a página em 375px.

Inclui `lang="pt-BR"`, link para pular navegação, landmarks, hierarquia de títulos,
nomes acessíveis, imagem com alt, foco visível, `aria-current`, `aria-busy`,
mensagens anunciadas, caption e cabeçalhos de tabela com `scope="col"`.
Contêiner da tabela recebe foco para permitir rolagem por teclado.

## Validação reproduzível

Use o PATH de build indicado acima:

```text
cmake --build build -j 2
cmake --build build/security-tests -j 2
ctest --test-dir build/security-tests --output-on-failure
python tests/usuario_integration.py
python tests/perfil_integration.py
python tests/auth_integration.py
python tests/interface_web.py
python tests/interface_web.py --browser
```

`interface_web.py` cria banco/configuração temporários em `build/`, inicia o
TrainingHub em porta livre e verifica arquivos estáticos/MIME, contratos reais,
health, lista preenchida e vazia, além de negar arquivos privados. Compara o
hash do banco de desenvolvimento e encerra o servidor ao terminar.

O modo opcional `--browser` usa **Chrome/Chromium instalado e Node 22+**, sem
pacotes npm. `TH21_CHROME` permite informar outro executável do navegador.
O teste usa CDP/WebSocket nativo para validar UI, loading, vazio, erro HTTP/rede,
contrato inválido, retry, escape de HTML, fallback do logo, navegação, foco,
Offcanvas/Escape e ausência de requisições externas. Respostas simuladas ficam
restritas à sessão de teste do navegador; a interface entregue usa a API real.
Capturas ficam em `build/th21-screenshots/` nas larguras 1440, 1024, 768 e 375px.

### Resultado nesta execução

- Build real do backend: aprovado.
- CTest: 2/2 aprovados (security e sqlite_foreign_keys).
- Regressão de Usuários: 146 verificações HTTP aprovadas.
- Regressão de Perfis: 138 verificações HTTP aprovadas.
- Regressão de autenticação: aprovada.
- TH-21 HTTP: aprovado, incluindo lista real preenchida/vazia, assets e health.
- Banco de desenvolvimento preservado nas verificações executadas.
- Validação visual e cenários de UI: **pendentes**. O Chromium instalado não
  concluiu a inicialização de depuração neste ambiente: tentativas sem porta
  disponível ou `CDP timeout: Page.enable`. Nenhuma captura foi gerada.
  A suíte opcional foi deixada para reprodução em um ambiente com navegador
  funcional; não se considera sua execução aprovada.

## Limitações e revisão humana

- Interface de consulta; funcionalidades futuras permanecem desabilitadas.
- Sem login de interface ou controle de acesso novo; preserva o comportamento
  atual dos endpoints. Autorização não faz parte da TH-21.
- Poppins depende da instalação local até o fornecimento dos arquivos da fonte.
- Health mostra o resultado da consulta inicial; não há polling.
- Revisão humana deve confirmar a aplicação da marca
  e a necessidade de fornecer Poppins localmente.
