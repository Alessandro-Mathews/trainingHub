# TH-33 — Interface de vínculo Aluno–Instrutor

## Objetivo e integração

A tabela administrativa de Alunos oferece a ação “Instrutor responsável” em cada
linha. Um modal específico permite consultar, definir ou substituir o responsável.
Os fluxos de cadastro, edição, situação e recuperação parcial da TH-31 continuam
independentes. Não há nova seção, redesign ou cadastro nesta funcionalidade.

A TH-30 fornece as operações do vínculo. A TH-31 fornece a entrada, os dados do
aluno e a infraestrutura de modais. A TH-32 serve como referência para associar
Instrutor e Usuario, sem importar seu estado privado. A implementação permanece
em `public/js/alunos.js` e usa os helpers públicos existentes de `api.js`.

## Contratos e identidades

| Operação | Entrada | Resposta de sucesso |
|---|---|---|
| GET `/api/alunos/{alunoId}/instrutor` | Sem query ou body | 200, `{"instrutor_id":123}` ou `{"instrutor_id":null}` |
| PUT `/api/alunos/{alunoId}/instrutor` | Somente `{"instrutor_id":123}` | 200, `{"instrutor_id":123}` |

`alunoId` significa `Aluno.id`. O aluno se associa ao seu Usuario por
`Aluno.usuario_id = Usuario.id`. No select e no payload, `instrutor_id` significa
`Instrutor.id`, nunca `Instrutor.usuario_id`. Este último identifica a conta usada
para resolver nome, e-mail, perfil e atividade.

Nenhum tenant é enviado no PUT. O backend obtém a academia do contexto autenticado.
ADMIN e GESTOR podem ler e alterar. INSTRUTOR, ALUNO e UNKNOWN não recebem essa
permissão. Não há inferência de Role por IDs fixos no frontend. HTTP 401 segue o
fluxo de login existente; 403 mantém feedback de falta de permissão.

## Leitura, ausência e histórico

Somente `instrutor_id: null` em uma resposta válida representa ausência. O modal
mostra “Nenhum instrutor definido”. HTTP 404, transporte e resposta incompatível
nunca são interpretados como ausência.

Instrutores completos e candidatos são mapas diferentes. O mapa completo resolve
o responsável atual mesmo quando sua conta ficou inativa ou mudou de perfil.
Quando esse responsável não pode receber novos vínculos, o modal mantém sua
identificação e mostra “Indisponível para nova seleção”. Dados não resolvíveis
recebem mensagem explícita; o vínculo não é ocultado nem transformado em null.

O backend não oferece desvinculação: não existe DELETE, candidato “Sem instrutor”
ou PUT com null. O placeholder “Selecione um instrutor” não pode ser salvo.

## Candidatos e elegibilidade

Um candidato precisa ter registro Instrutor, Usuario associado resolvível na
academia autenticada, `Usuario.ativo === true`, Perfil existente com `ativo === 1`
e nome exatamente `Instrutor`. A academia ativa é validada na autenticação.
`GET /api/instrutores` isoladamente não garante essas condições.

O aluno também precisa de Usuario resolvível na academia, ativo, com Perfil ativo
e nome exatamente `Aluno`. Se perder elegibilidade, o modal ainda tenta exibir o
responsável, mas bloqueia alteração com explicação. Nada é corrigido automaticamente.

A correção preparatória em `UsuarioRepository` rejeita atividade persistida fora
de 0/1, em vez de apresentá-la como true. Se uma API necessária falhar, o modal não
habilita a escrita. Respostas com formatos inválidos, IDs duplicados ou contas de
tenant inesperado também bloqueiam o snapshot; não são parcialmente confiadas.
Instrutores sem Usuario resolvível são excluídos dos candidatos.

## Requests e snapshots

Abrir a seção mantém os três GETs existentes: Alunos, Usuarios e Perfis. Não há
consulta por linha nem carregamento antecipado de vínculos.

Cada abertura ou atualização explícita do modal faz quatro leituras independentes:

```text
GET /api/alunos/{Aluno.id}/instrutor
GET /api/instrutores
GET /api/usuarios?academia_id=<context.academiaId>
GET /api/perfis
```

As requisições são iniciadas em paralelo e aguardadas com `Promise.allSettled`.
Somente um snapshot de candidatos validado por inteiro é publicado. A seleção é
limpa a cada atualização. Leitura do vínculo é tratada separadamente dos metadados:
uma falha nos candidatos não se converte em “nenhum responsável”.

Salvar com sucesso usa somente um PUT, sem recarregar a tabela ou executar GET
adicional. Reconciliação usa somente um GET do vínculo por tentativa. Após um
resultado divergente, atualizar candidatos exige os quatro GETs e nova escolha.

## Validação e alteração

Os rótulos das opções são `Nome — email`. Antes de salvar, o valor passa por
`parseId`, membership do mapa interno de candidatos e nova verificação das
associações, tenant, atividade e perfil do snapshot. Inserir ou adulterar uma
option no DOM não autoriza o ID. O aluno é revalidado no mesmo snapshot.

Selecionar o próprio responsável mantém o botão desabilitado e não gera escrita.
O submit trava antes do primeiro await, impedindo duplo envio. O responsável só é
atualizado após resposta válida e ID correspondente ao solicitado. As mensagens
distinguem “Instrutor definido com sucesso” e “Instrutor alterado com sucesso”.

HTTP 400, 403, 404 e 409 produzem mensagens específicas e exigem atualização antes
de outra escrita. Corpos internos, SQL, stack traces e detalhes de transporte não
são apresentados. O backend continua sendo a autoridade final para concorrência
e elegibilidade, mesmo após todas as validações locais.

## Escrita ambígua e reconciliação

Timeout, transporte, JSON inválido, resposta incompatível e 5xx após PUT não provam
falha da escrita. A interface guarda Aluno.id e Instrutor.id desejado e consulta o
GET do vínculo, sem repetir PUT automaticamente.

Se o ID observado corresponde ao desejado, o modal informa “Responsável atual
confirmado após consulta”. Se diverge, mostra o responsável observado e exige
atualização e nova escolha explícita. Se a consulta falhar, o resultado permanece
incerto: somente o botão de repetir a leitura é habilitado para recuperação.

Cancelar após falha da reconciliação não descarta a intenção pendente. Ela permanece
em memória por aluno; reabrir consulta o estado antes de permitir nova escrita.
Nenhuma intenção é persistida em storage. Reload encerra o estado em memória e uma
nova abertura continua exigindo o GET atual.

Uma leitura divergente não prova que o PUT falhou. O servidor pode concluir depois,
ou outro operador pode ter feito uma alteração. A API não oferece versão, operação
consultável ou compare-and-swap; a última escrita válida efetivada prevalece.

## Concorrência e ciclo do modal

Cada abertura/fechamento invalida a geração anterior. Operações capturam geração,
objeto de estado e Aluno.id. Leituras, reconciliações e suas finalizações só podem
alterar o modal/travas se a operação ainda pertence ao aluno atual.

Ao receber `hide.bs.modal`, a interface marca `responsavelClosing` e invalida as
operações antigas, mantendo as ações e atualizações bloqueadas durante a animação.
Somente `hidden.bs.modal` finaliza a limpeza, libera essa trava e devolve o foco.
Tentativas de abertura durante fechamento não iniciam GETs. Nenhum timer decide
quando o modal está disponível novamente; o evento real do Bootstrap é a autoridade.

Fechar durante carregamento é permitido; respostas tardias de A não modificam B.
Durante PUT ou reconciliação crítica, botões de fechamento, Escape e backdrop são
bloqueados pelo evento `hide.bs.modal`. Uma falha de reconciliação libera fechamento,
mas mantém a intenção pendente. Sessão expirada permite desmontagem e redireciona.

A listagem e outras operações de Alunos ficam bloqueadas enquanto o modal está
aberto. O estado privado da TH-32 não atualiza nem substitui seu snapshot. Fechar
limpa seleção, snapshots e feedback temporário e não escreve no backend.

## Int64 e XSS

IDs permanecem strings decimais canônicas em mapas, select, comparação e URL.
`parseJson` e `putJson` preservam os tokens JSON exatos, incluindo
`9007199254740993` e `9223372036854775807`. Nenhum ID passa por Number, parseInt,
parseFloat ou conversão equivalente. `api.js` permanece inalterado.

Dados externos usam `createElement`, `textContent`, `value` e `replaceChildren`.
Nome e e-mail não entram em innerHTML ou insertAdjacentHTML. Mensagens são locais.

## Acessibilidade e responsividade

O modal associa título e identificação do aluno. O select tem label, required e
descrições de ajuda/feedback. Feedback usa role status e aria-live; o formulário
usa aria-busy. Foco inicial vai a Cancelar, disponível durante carregamento.
Ao fechar, retorna ao botão da linha; caso indisponível, usa o fallback existente
de cadastro/atualização. Bootstrap mantém foco e navegação por teclado.

A tabela mantém overflow horizontal local e ações com flex-wrap. O modal usa
modal-dialog-scrollable e botões com quebra de linha. A estrutura existente é
reutilizada, sem alteração de CSS. A aceitação visual cobre desktop e 375x812.

## Testes

`tests/aluno_instrutor_interface.py` executa o módulo entregue com HTML real e DOM
controlado, sem npm. Cobre contratos, quatro GETs, um PUT, candidatos, histórico,
aluno inelegível, int64 em quatro limites, XSS, adulteração do select, erros HTTP,
escrita ambígua, falha/repetição da reconciliação, intenção preservada ao fechar,
duplo envio e respostas tardias A/B. A invalidação forçada usada para testar uma
reconciliação antiga é instrumentação somente em memória do teste.

Oito mutações em memória devem falhar: trocar Instrutor.id por usuario_id, arredondar
IDs com Number, remover filtro de atividade, remover filtro de perfil, confiar no
DOM, remover trava de submit, remover proteção de geração e resolver a identificação
histórica somente entre candidatos elegíveis. Fontes não são editadas. Os testes
históricos conferem nome e e-mail exatos, ausência do histórico no select e presença
de outro candidato válido. O DOM controlado permite separar hide de hidden para
comprovar bloqueio e recuperação após uma transição assíncrona, sem GET prematuro.

`tests/interface_web.py --browser` executa `interface_web.mjs` com Chrome/CDP e
banco/perfil temporários. Cobre definição e substituição reais, histórico após
desativação, XSS, quatro leituras por modal, uma escrita por sucesso, teclado,
retorno de foco, Escape bloqueado durante write e desktop/mobile sem overflow global.
Também tenta abrir B durante o fechamento de A, verifica zero GETs prematuros e
reabre B após hidden; o responsável histórico precisa manter nome e e-mail corretos.
Screenshots ficam em `build/th21-screenshots/aluno-instrutor-*.png`.

TH-31 e TH-32 permanecem nas regressões. Seletores de ações de conta na TH-31 foram
ajustados para coexistir com o novo botão. CI acrescenta somente a nova suíte Python.
Não houve alteração de backend, migration, configuração ou banco persistente.
