import { ApiError, getJson, postJson, putJson, parseId, parseCentavos, parseDuracao } from './api.js';

const element = (id) => document.getElementById(id);
const text = (id, value) => { element(id).textContent = value; };
let context;
let initialized = false;
let generation = 0;
let visited = false;
let loading = false;
let writing = false;
let checking = false;
let closing = false;
let ready = false;
let denied = false;
let planos = new Map();
let dialog = null;
let pending = null;
const openers = new Map();
const kinds = ['create', 'edit', 'status'];

export function reaisParaCentavos(value) {
  if (typeof value !== 'string') return null;
  const match = /^(\d+)(?:[.,](\d{1,2}))?$/.exec(value.trim());
  if (!match || match[1].length > 17) return null;
  return parseCentavos((BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0'))).toString());
}

export function centavosParaReais(value) {
  if (parseCentavos(value) === null) return null;
  const digits = value.padStart(3, '0');
  return `${digits.slice(0, -2)},${digits.slice(-2)}`;
}

export function formatarValor(value) {
  const decimal = centavosParaReais(value);
  if (decimal === null) return 'Valor indisponível';
  const [whole, fraction] = decimal.split(',');
  return `R$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction}`;
}

function validPlano(value) {
  return value && !Array.isArray(value) && Object.keys(value).length === 8
    && parseId(value.id) !== null && value.academia_id === context.academiaId
    && typeof value.nome === 'string' && (value.descricao === null || typeof value.descricao === 'string')
    && parseCentavos(value.valor_centavos) !== null && parseDuracao(value.duracao_dias) !== null
    && typeof value.ativo === 'boolean' && typeof value.criado_em === 'string' && value.criado_em.length > 0;
}

function errorMessage(error) {
  return ({ 0: 'Não foi possível conectar ao TrainingHub. A conexão pode ter expirado.',
    400: 'Confira o nome, o valor em reais e a duração em dias.',
    403: 'Sua conta não tem permissão para gerenciar planos.',
    404: 'Plano não disponível. Feche o diálogo e atualize a listagem.',
    409: 'Conflito nos dados. Confira se já existe plano com esse nome e atualize a listagem.',
    500: 'Não foi possível concluir a operação no servidor.',
    502: 'Resposta incompatível do servidor.' })[error.status] || 'Não foi possível concluir a operação.';
}

function sessionExpired(error) {
  if (error.status !== 401) return false;
  generation++;
  context = null;
  writing = false;
  dialog = null;
  pending = null;
  element('authenticated-app').hidden = true;
  for (const kind of kinds) window.bootstrap?.Modal.getInstance(element(`plano-${kind}-modal`))?.hide();
  location.replace('/login.html');
  return true;
}

function controls() {
  const busy = loading || writing || checking || closing;
  element('planos-panel').setAttribute('aria-busy', String(busy));
  element('refresh-planos').disabled = busy || dialog !== null;
  element('retry-planos').disabled = busy;
  element('create-plano').disabled = busy || !ready || denied || !!pending || !!dialog;
  if (element('planos-empty-create')) element('planos-empty-create').disabled = element('create-plano').disabled;
  for (const action of element('planos-rows').querySelectorAll('button')) action.disabled = busy || !ready || denied || !!pending || !!dialog;
  for (const kind of kinds) {
    const modal = element(`plano-${kind}-modal`);
    modal.setAttribute('aria-busy', String(writing || (dialog?.kind === kind && dialog.loading)));
    for (const control of modal.querySelectorAll('input, textarea, button')) {
      control.disabled = control.dataset.dismiss === 'true' ? writing
        : closing || writing || !!pending || denied || !dialog || dialog.kind !== kind || dialog.loading || !dialog.loaded || !dialog.shown;
    }
  }
  element('planos-uncertain').hidden = pending === null;
  element('planos-reconcile').disabled = busy || !!dialog;
  element('planos-resume').hidden = !pending?.checked;
  element('planos-resume').disabled = busy || !!dialog;
}

function button(label, action) {
  const result = document.createElement('button');
  result.type = 'button';
  result.className = 'btn btn-outline-secondary';
  result.textContent = label;
  result.addEventListener('click', action);
  return result;
}

function cell(label, value) {
  const td = document.createElement('td');
  const caption = document.createElement('span');
  caption.className = 'planos-mobile-label';
  caption.textContent = label;
  caption.setAttribute('aria-hidden', 'true');
  const content = document.createElement('span');
  content.textContent = value;
  td.append(caption, content);
  return td;
}

function render() {
  const rows = document.createDocumentFragment();
  for (const plano of planos.values()) {
    const row = document.createElement('tr');
    row.append(cell('Nome', plano.nome));
    const description = cell('Descrição', plano.descricao || 'Sem descrição');
    const content = description.children[1];
    content.className = 'planos-description';
    if (plano.descricao) {
      content.id = `plano-description-${plano.id}`;
      const expand = button('Mostrar descrição completa', () => {
        const expanded = expand.getAttribute('aria-expanded') !== 'true';
        content.classList.toggle('is-expanded', expanded);
        expand.setAttribute('aria-expanded', String(expanded));
        expand.textContent = expanded ? 'Resumir descrição' : 'Mostrar descrição completa';
      });
      expand.className = 'btn btn-link planos-description-toggle';
      expand.setAttribute('aria-expanded', 'false');
      expand.setAttribute('aria-controls', content.id);
      description.append(expand);
    }
    row.append(description, cell('Valor', formatarValor(plano.valor_centavos)),
      cell('Duração', `${plano.duracao_dias} ${plano.duracao_dias === '1' ? 'dia' : 'dias'}`));
    const status = cell('Status', '');
    const badge = status.children[1];
    badge.className = `status-badge${plano.ativo ? '' : ' inactive'}`;
    badge.textContent = plano.ativo ? 'Ativo' : 'Inativo';
    const actions = cell('Ações', '');
    const group = document.createElement('div');
    group.className = 'd-flex flex-wrap gap-2';
    const edit = button('Editar', () => openExisting('edit', plano.id, edit));
    const change = button(plano.ativo ? 'Desativar' : 'Ativar', () => openExisting('status', plano.id, change));
    edit.setAttribute('aria-label', `Editar plano ${plano.nome}`);
    change.setAttribute('aria-label', `${plano.ativo ? 'Desativar' : 'Ativar'} plano ${plano.nome}`);
    group.append(edit, change);
    actions.append(group);
    row.append(status, actions);
    rows.append(row);
  }
  element('planos-rows').replaceChildren(rows);
  element('planos-error').hidden = true;
  element('planos-state').hidden = planos.size !== 0;
  element('planos-table-container').hidden = planos.size === 0;
  const empty = document.createElement('p');
  empty.textContent = 'Nenhum plano cadastrado';
  const create = button('Novo plano', () => openCreate(create));
  create.id = 'planos-empty-create';
  element('planos-state').replaceChildren(empty, create);
  text('planos-count', `${planos.size} ${planos.size === 1 ? 'plano' : 'planos'}`);
  controls();
}

async function readList() {
  const values = await getJson('/api/planos');
  if (!Array.isArray(values) || !values.every(validPlano)
    || new Set(values.map((value) => value.id)).size !== values.length) throw new ApiError(502);
  return new Map(values.map((value) => [value.id, value]));
}

function listError(error) {
  ready = false;
  denied = error.status === 403;
  element('planos-state').hidden = true;
  element('planos-table-container').hidden = true;
  element('planos-error').hidden = false;
  text('planos-error-title', denied ? 'Sem permissão para consultar planos.' : 'Não foi possível carregar os planos.');
  text('planos-error-message', errorMessage(error));
  text('planos-count', denied ? 'Sem permissão' : 'Indisponível');
}

export async function loadPlanos() {
  if (!context || loading || writing || checking || dialog) return;
  const token = ++generation;
  visited = true;
  loading = true;
  ready = false;
  element('planos-error').hidden = true;
  element('planos-table-container').hidden = true;
  element('planos-state').hidden = false;
  const spinner = document.createElement('span');
  spinner.className = 'spinner-border spinner-border-sm';
  spinner.setAttribute('aria-hidden', 'true');
  const message = document.createElement('p');
  message.textContent = 'Carregando planos...';
  element('planos-state').replaceChildren(spinner, message);
  text('planos-count', 'Consultando');
  controls();
  try {
    const records = await readList();
    if (generation !== token) return;
    planos = records;
    ready = true;
    denied = false;
    render();
  } catch (error) {
    if (generation === token && !sessionExpired(error)) listError(error);
  } finally {
    if (generation === token) { loading = false; controls(); }
  }
}

export function visitPlanos() { if (context && (!visited || !ready)) return loadPlanos(); }

export function leavePlanos() {
  if (!initialized || writing || checking) return;
  generation++;
  loading = false;
  visited = false;
  ready = false;
  if (dialog) closeDialog(dialog.kind);
  controls();
}

function showDialog(view, focus) {
  dialog = view;
  openers.set(view.kind, view.opener);
  const modal = element(`plano-${view.kind}-modal`);
  modal.addEventListener('shown.bs.modal', () => {
    view.shown = true;
    controls();
    if (dialog === view) element(view.loaded && view.kind !== 'create'
      ? view.kind === 'edit' ? 'plano-edit-name' : 'plano-status-submit' : focus).focus();
  }, { once: true });
  window.bootstrap.Modal.getOrCreateInstance(modal).show();
  controls();
}

function closeDialog(kind) {
  const view = dialog;
  if (!view || view.kind !== kind) return;
  dialog = null;
  const node = element(`plano-${kind}-modal`);
  const modal = window.bootstrap?.Modal.getInstance(node);
  if (modal && !view.shown) {
    closing = true;
    node.addEventListener('shown.bs.modal', () => modal.hide(), { once: true });
  }
  else modal?.hide();
  controls();
}

function resetForm(kind) {
  element(`plano-${kind}-form`).reset();
  for (const field of ['name', 'description', 'value', 'duration']) {
    element(`plano-${kind}-${field}`).setCustomValidity('');
    element(`plano-${kind}-${field}`).removeAttribute('aria-invalid');
  }
  text(`plano-${kind}-feedback`, '');
}

function openCreate(opener) {
  if (!ready || loading || writing || checking || closing || pending || dialog || denied) return;
  resetForm('create');
  showDialog({ kind: 'create', opener, loaded: true }, 'plano-create-name');
}

async function openExisting(kind, id, opener) {
  if (!ready || loading || writing || checking || closing || pending || dialog || denied) return;
  if (kind === 'edit') resetForm(kind);
  text(`plano-${kind}-feedback`, 'Consultando plano...');
  if (kind === 'status') text('plano-status-question', 'Consultando plano...');
  const view = { kind, id, opener, loading: true, loaded: false };
  const token = generation;
  showDialog(view, `plano-${kind}-feedback`);
  try {
    const plano = await getJson(`/api/planos/${id}`);
    if (dialog !== view || token !== generation) return;
    if (!validPlano(plano) || plano.id !== id) throw new ApiError(502);
    view.original = plano;
    view.loaded = true;
    if (kind === 'edit') {
      element('plano-edit-name').value = plano.nome;
      element('plano-edit-description').value = plano.descricao ?? '';
      element('plano-edit-value').value = centavosParaReais(plano.valor_centavos);
      element('plano-edit-duration').value = plano.duracao_dias;
    } else {
      view.desiredStatus = !plano.ativo;
      text('plano-status-question', `${view.desiredStatus ? 'Ativar' : 'Desativar'} o plano ${plano.nome}?`);
      text('plano-status-explanation', view.desiredStatus ? 'O plano voltará a estar disponível para novas contratações.'
        : 'O plano deixará de estar disponível para novas contratações. O histórico será preservado.');
      text('plano-status-submit', view.desiredStatus ? 'Ativar plano' : 'Desativar plano');
    }
    text(`plano-${kind}-feedback`, '');
  } catch (error) {
    if (dialog === view && token === generation && !sessionExpired(error)) {
      denied = error.status === 403;
      text(`plano-${kind}-feedback`, errorMessage(error));
    }
  } finally {
    if (dialog === view) {
      view.loading = false;
      controls();
      element(view.loaded ? kind === 'edit' ? 'plano-edit-name' : 'plano-status-submit' : `plano-${kind}-feedback`).focus();
    }
  }
}

function formData(view) {
  const kind = view.kind;
  const name = element(`plano-${kind}-name`);
  const value = element(`plano-${kind}-value`);
  const duration = element(`plano-${kind}-duration`);
  name.setCustomValidity(name.value.trim() ? '' : 'Informe um nome.');
  const cents = reaisParaCentavos(value.value);
  value.setCustomValidity(cents === null ? 'Informe reais sem milhares, com até duas casas e dentro do limite permitido.' : '');
  const days = parseDuracao(duration.value);
  duration.setCustomValidity(days === null ? 'Informe dias inteiros positivos até 9223372036854775807.' : '');
  for (const input of [name, value, duration]) input.setAttribute('aria-invalid', String(!input.validity.valid));
  if (!element(`plano-${kind}-form`).reportValidity()) return null;
  const description = element(`plano-${kind}-description`).value;
  return { nome: name.value, descricao: kind === 'edit' && !view.descriptionTouched
    ? view.original.descricao : description === '' ? null : description,
    valor_centavos: cents, duracao_dias: days };
}

async function submit(event) {
  event?.preventDefault();
  const view = dialog;
  if (!view || !view.loaded || !view.shown || view.loading || closing || writing || loading || checking || pending || denied) return;
  const dto = view.kind === 'status' ? { ativo: view.desiredStatus } : formData(view);
  if (!dto) return;
  const actor = context;
  writing = true;
  text(`plano-${view.kind}-feedback`, 'Salvando...');
  controls();
  try {
    const saved = view.kind === 'create' ? await postJson('/api/planos', dto)
      : await putJson(`/api/planos/${view.id}${view.kind === 'status' ? '/status' : ''}`, dto);
    if (context !== actor) return;
    if (!validPlano(saved) || (view.id && saved.id !== view.id)
      || !Object.entries(dto).every(([key, value]) => saved[key] === value)) throw new ApiError(502);
    writing = false;
    closeDialog(view.kind);
    text('planos-feedback', view.kind === 'create' ? 'Plano cadastrado com sucesso.'
      : view.kind === 'edit' ? 'Plano atualizado com sucesso.'
        : saved.ativo ? 'Plano ativado com sucesso.' : 'Plano desativado com sucesso.');
    await loadPlanos();
  } catch (error) {
    if (context !== actor || sessionExpired(error)) return;
    if (error.status === 0 || error.status === 502 || error.status >= 500) {
      pending = { kind: view.kind, id: view.id, dto, checked: false };
      writing = false;
      closeDialog(view.kind);
      text('planos-uncertain-message', 'O resultado da escrita não pôde ser confirmado. Ela pode ter sido concluída. Verifique os dados antes de decidir por outra tentativa.');
      element('planos-uncertain-message').focus();
    } else {
      denied = error.status === 403;
      text(`plano-${view.kind}-feedback`, errorMessage(error));
      element(`plano-${view.kind}-feedback`).focus();
    }
  } finally {
    if (context === actor) { writing = false; controls(); }
  }
}

async function reconcile() {
  if (!pending || loading || writing || checking || dialog) return;
  const attempt = pending;
  const actor = context;
  checking = true;
  text('planos-uncertain-message', 'Consultando o estado atual. Nenhuma escrita será repetida.');
  controls();
  try {
    if (attempt.kind === 'create') {
      const records = await readList();
      if (context !== actor || pending !== attempt) return;
      planos = records;
      ready = true;
      denied = false;
      render();
      const matching = [...records.values()].some((plano) => plano.nome === attempt.dto.nome);
      text('planos-uncertain-message', matching
        ? 'Existe um plano com o mesmo nome. Isso não prova que esta tentativa foi concluída. Confira a listagem e decida explicitamente antes de criar novamente.'
        : 'Nenhum plano com o mesmo nome foi observado. A escrita anterior ainda pode estar em processamento. Confira os dados antes de decidir por outra tentativa.');
    } else {
      const observed = await getJson(`/api/planos/${attempt.id}`);
      if (context !== actor || pending !== attempt) return;
      if (!validPlano(observed) || observed.id !== attempt.id) throw new ApiError(502);
      text('planos-uncertain-message', `Estado observado: ${observed.nome}; ${formatarValor(observed.valor_centavos)}; ${observed.duracao_dias} dias; ${observed.ativo ? 'ativo' : 'inativo'}. Esta consulta não prova autoria ou conclusão da escrita anterior. Atualize a listagem antes de outra alteração.`);
      ready = false;
    }
    attempt.checked = true;
  } catch (error) {
    if (context !== actor || sessionExpired(error)) return;
    attempt.checked = error.status === 404 && attempt.kind !== 'create';
    text('planos-uncertain-message', `${errorMessage(error)} O resultado da escrita anterior continua sem confirmação.`);
  } finally {
    if (context === actor) { checking = false; controls(); }
  }
}

export function initPlanos(authContext) {
  generation++;
  context = authContext;
  visited = loading = writing = checking = closing = ready = denied = false;
  planos = new Map();
  dialog = pending = null;
  if (initialized) { controls(); return; }
  initialized = true;
  element('refresh-planos').addEventListener('click', loadPlanos);
  element('retry-planos').addEventListener('click', loadPlanos);
  element('create-plano').addEventListener('click', (event) => openCreate(event.currentTarget));
  element('planos-reconcile').addEventListener('click', reconcile);
  element('planos-resume').addEventListener('click', async () => {
    if (!pending?.checked || writing || loading || checking || dialog) return;
    pending = null;
    text('planos-feedback', 'Tentativa anterior encerrada por sua decisão. Confira a listagem antes de iniciar uma nova operação.');
    controls();
    await loadPlanos();
  });
  for (const kind of kinds) {
    if (kind !== 'status') element(`plano-${kind}-form`).addEventListener('submit', submit);
    else element('plano-status-submit').addEventListener('click', submit);
    const modal = element(`plano-${kind}-modal`);
    modal.addEventListener('hide.bs.modal', (event) => {
      if (writing) { event.preventDefault(); return; }
      closing = true;
      if (dialog?.kind === kind) {
        dialog.shown = false;
        dialog = null;
      }
      controls();
    });
    modal.addEventListener('hidden.bs.modal', () => {
      closing = false;
      if (dialog?.kind === kind) dialog = null;
      controls();
      const opener = openers.get(kind);
      (opener?.isConnected && !opener.disabled ? opener : element('create-plano').disabled
        ? element('refresh-planos') : element('create-plano')).focus();
    });
    if (kind !== 'status') for (const field of ['name', 'description', 'value', 'duration']) {
      element(`plano-${kind}-${field}`).addEventListener('input', (event) => {
        if (field === 'description' && dialog?.kind === kind) dialog.descriptionTouched = true;
        event.target.setCustomValidity('');
        event.target.removeAttribute('aria-invalid');
      });
    }
  }
  controls();
}
