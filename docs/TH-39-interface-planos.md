# TH-39 — Interface administrativa de Planos

## Objetivo e integração

A seção `#planos` permite listar, cadastrar, editar e ativar/desativar planos da
academia autenticada. Usa HTML, CSS, ES modules e Bootstrap local, seguindo a
navegação, os panels, os badges e os modais existentes. Não altera backend,
migrations, CMake ou política de autorização.

`app.js` inicializa o módulo após `/api/auth/me`. A visita da seção carrega a
listagem. Sair invalida a geração das leituras, impedindo que respostas anteriores
substituam dados de uma nova visita. A navegação mantém título, item ativo, foco
no conteúdo e fechamento do offcanvas no mobile.

| Operação | Endpoint | Entrada |
| --- | --- | --- |
| Listar | GET `/api/planos` | Sem body/query |
| Consultar para editar ou confirmar status | GET `/api/planos/{id}` | ID exato na URL |
| Cadastrar | POST `/api/planos` | Nome, descrição, centavos e duração |
| Editar | PUT `/api/planos/{id}` | Objeto completo editável |
| Status | PUT `/api/planos/{id}/status` | Somente `ativo` boolean |

Não há N+1 na listagem: GET `/api/planos` fornece todos os campos da tabela,
incluindo ativos e inativos. Detalhes são consultados apenas ao abrir uma ação.
Após escrita confirmada, o modal fecha, o feedback anuncia sucesso e a listagem
é consultada novamente. Falha nessa leitura não transforma escrita confirmada
em falha ou dispara novo envio.

## Campos e precisão

Nome é obrigatório. A validação verifica conteúdo sem remover espaços do texto
enviado ou normalizar caixa. A descrição é opcional e seu conteúdo é preservado.
Cadastro vazio envia NULL. Edição sem alteração preserva a descrição original,
inclusive string vazia, NULL e quebras CRLF que o textarea normaliza visualmente.
Se o usuário alterar e apagar todo o conteúdo, a edição envia NULL.

Preço é apresentado em reais. O input textual com `inputmode="decimal"` aceita
`99`, `99,9`, `99,90`, `99.90`, `0` e `0,00`. Whitespace externo é tolerado apenas
no preço. Milhares, separadores misturados, sinais, negativos, espaços internos,
notação científica e mais de duas casas são rejeitados antes de qualquer envio.

`reaisParaCentavos` separa partes textuais e usa BigInt para conversão e limite.
`centavosParaReais` e `formatarValor` manipulam dígitos sem Number, parseFloat ou
arredondamento. INT64_MAX centavos corresponde a `92233720368547758,07` na entrada
e `R$ 92.233.720.368.547.758,07` na tabela. Zero é permitido.

Duração usa texto com `inputmode="numeric"`, exclusivamente inteiro decimal
canônico positivo entre 1 e `9223372036854775807`. Não aceita zero, zeros iniciais,
decimais, sinais ou expoentes. A tabela mostra `1 dia` ou `N dias`, sem conversão
para meses ou Number.

`api.js` mantém IDs como strings exatas e acrescenta apenas dois campos especiais:
`valor_centavos`, entre zero e INT64_MAX, e `duracao_dias`, entre um e INT64_MAX.
Parser preserva seus lexemas numéricos como strings internas. Serializer valida
decimal canônico e emite tokens numéricos JSON sem aspas. BigInt não é enviado
para JSON.stringify. Tipos e comportamento dos demais campos permanecem iguais.

## Autorização e tenant

Não há seleção de academia nem tenant no body/query de Plano. ID, academia,
atividade e criação nunca entram no DTO de cadastro/edição. Status envia somente
o boolean solicitado. A resposta é validada contra a academia do contexto atual.

Backend permite ADMIN/GESTOR e continua sendo autoridade. Frontend não deduz
Role por perfilId. A seção reage à API real: 401 oculta aplicação e redireciona
ao login; 403 informa falta de permissão e bloqueia operações até nova consulta.
Inativos continuam visíveis e editáveis. Status exige confirmação específica
para Plano, sem optimistic update ou mensagens sobre login de Usuario.

## Estados, erros e escritas ambíguas

Loading exibe spinner, mensagem, `aria-busy` e bloqueio dos dados anteriores.
Empty aparece somente após resposta válida `[]`, com CTA Novo plano. Falha de GET
produz estado separado com retry, nunca empty ou tabela antiga apresentada como atual.

Erros 400 e 409 mantêm formulário para correção. A mensagem de 409 descreve
conflito sem afirmar que toda ocorrência é duplicidade de nome. 404 informa
indisponibilidade e orienta atualização. Erros internos não expõem corpo HTTP,
SQL, caminhos ou detalhes de rede.

O helper mantém timeout de 15 segundos; falhas de rede/timeout tornam-se status 0,
JSON incompatível torna-se 502. Status 0, 502 ou 5xx após envio potencial não
provam falha da escrita. Nenhum POST/PUT é repetido automaticamente.

Nesses casos, a interface fecha o modal e bloqueia novas escritas. Verificar dados
consulta lista para cadastro ou detalhe para edição/status. Nome coincidente é
apenas indício; a interface não anuncia sucesso com base nessa coincidência.
Para edição/status, mostra nome, valor, duração e atividade observados. Nova
operação exige ação explícita para encerrar a tentativa e nova consulta da lista.
Uma leitura imediata não garante que escrita antiga ainda em processamento não
venha a terminar depois; essa limitação é apresentada ao usuário.

## Responsividade, acessibilidade e DOM

Desktop/tablet usam tabela com Nome, Descrição, Valor, Duração, Status e Ações.
Abaixo de 576 px, as mesmas linhas são empilhadas com rótulos por campo. Não há
segunda cópia dos dados nem dependência exclusiva de rolagem horizontal. CSS
específico de Planos preserva layout dos módulos anteriores.

Descrição é resumida visualmente com CSS, mantendo texto completo em estado e DOM.
Botão acessível expande/recolhe a descrição; edição mostra todo o conteúdo.
Nome, descrição e confirmações usam createElement/textContent, sem innerHTML.

Labels, ajuda de formato, aria-invalid, aria-live e aria-busy acompanham formulários
e operações. Modal só permite escrita após abertura concluída e dados carregados.
Envio duplo e fechamento durante escrita são bloqueados. Eventos Bootstrap
coordenam foco inicial, transição e retorno ao acionador ou controle disponível.
O início de `hide.bs.modal` invalida o diálogo e bloqueia novas submissões;
`hidden.bs.modal` libera o estado de fechamento. Fechar novamente um diálogo já
fechado não cria espera por outro evento. Uma escrita já enviada continua
impedindo fechamento até receber resposta.

## Testes e limites

`tests/planos_interface.py` executa módulos reais com Node/DOM double e confirma
bodies gerados pelo JavaScript contra servidor real e SQLite temporário. Cobre
int64, conversão monetária, validações, estados, CRUD/status, reconciliação,
requisições obsoletas, transição do modal, autenticação, XSS e tenant.

Harnesses de interface existentes receberam somente adaptação do novo import.
`interface_web.mjs`, executado por `interface_web.py --browser`, amplia a prova
real de navegação, formulários, precisão, teclado, foco e layout mobile.
Browser permanece opcional no CI. A única entrada adicional é
`python tests/planos_interface.py`.

Todos os bancos de teste são isolados. `data/traininghub.db` não recebe migrations
ou escritas. Um ambiente que ainda não possui a tabela Plano precisa aplicar a
migration 006 existente em uma operação separada; TH-39 não faz isso automaticamente.

Sem DELETE, nova API, financeiro, Matrícula, self-read, framework novo ou alterações
de autorização. O backend não oferece versão/ETag para impedir perda de edição
concorrente. A interface não promete que leitura de reconciliação identifique
autoria ou conclusão definitiva de uma escrita sem resposta.

## Validação realizada

Em 2026-11-28, na branch `feature/TH-39-interface-planos`, base `b6263da`:

- TH-39: 523 assertions JavaScript/DOM e 62 verificações HTTP com bodies gerados
  pelo JavaScript e persistência SQLite isolada.
- Interfaces anteriores: Alunos 386 assertions/26 HTTP, Instrutores 473/42 e
  vínculo 257 assertions, com oito mutações rejeitadas. Interface Web aprovada.
- Chrome/CDP: suítes existentes e TH-39 aprovadas, incluindo 1440/1024/768/375 px,
  apresentação empilhada, teclado, foco, XSS e valor/duração máximos.
- Build da aplicação e dos testes aprovado; CTest 4/4.
- Regressões: Plano 397, Matrícula 324, Aluno 147, Instrutor 155, vínculo 212,
  TH-34 865, Authorization 247, Usuario/TH-63 379, Perfil 138 e Auth aprovados.

Executar `python tests/planos_interface.py` e as entradas de interface existentes
no CI. Prova de navegador usa `python tests/interface_web.py --browser`, Chrome
instalado e Node com WebSocket nativo. Neste ambiente, Chrome/CDP precisou executar
fora do sandbox para acessar o renderer. Screenshots ficam em
`build/th21-screenshots/planos-{1440,1024,768,375}.png`.

O teste de transição do modal cobre resposta de detalhe anterior ao evento
`shown.bs.modal`. A edição preserva foco no campo Nome após a abertura. Outro caso
preserva descrição CRLF intacta quando o textarea não foi modificado.
O double também separa `hide` de `hidden`, cobrindo cancelamento sem escrita,
reabertura, escrita em andamento e liberação após sucesso ou erro ambíguo.
Chrome/CDP verifica Cancelar e Escape durante a transição dos três modais,
sem POST/PUT tardio e com retorno do foco ao acionador.

SHA-256 do banco persistente antes e depois:
`10C935F52AD5FEADA7F2C25D9257CCBB01CC076D7AFD1306518C98F5970BABA8`.
Staging permaneceu vazio, sem add, commit, push ou integração Git.
