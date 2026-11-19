import { ApiError, getJson, postJson, putJson, parseId } from './api.js';

const element = (id) => document.getElementById(id);
let context;
let initialized = false;
let visited = false;
let loading = false;
let submitting = false;
let profilesLoading = false;
let snapshotReady = false;
let uncertain = false;
let instrutores = [];
let users = new Map();
let profile = null;
let pendingUser = null;
let accountUnconfirmed = false;
let selectedUser = null;
let desiredStatus = false;
let allowHide = false;
const openers = new Map();

function text(id, value) { element(id).textContent = value; }

function sessionExpired(error) {
  if (error.status !== 401) return false;
  document.getElementById('authenticated-app').hidden = true;
  element('instrutor-create-password').value = '';
  for (const name of ['create', 'edit', 'status']) hideModal(name);
  location.replace('/login.html');
  return true;
}

function errorMessage(error) {
  return ({ 0: 'Não foi possível conectar ao TrainingHub.',
    400: 'Confira os dados informados e a elegibilidade da conta.',
    403: 'Sua conta não tem permissão para esta operação.',
    404: 'Recurso não disponível. Atualize a listagem.',
    409: 'Conflito nos dados. O e-mail ou cadastro pode já existir. Atualize a listagem.',
    500: 'Não foi possível concluir a operação no servidor.',
    502: 'Resposta incompatível do servidor.' })[error.status] || 'Não foi possível concluir a operação.';
}

const ambiguous = (error) => error.status === 0 || error.status === 502 || error.status >= 500;

function validUser(user) {
  return user && parseId(user.id) !== null && parseId(user.academia_id) !== null
    && user.academia_id === context.academiaId && parseId(user.perfil_id) !== null
    && typeof user.nome === 'string' && typeof user.email === 'string' && typeof user.ativo === 'boolean';
}

function validInstrutor(instrutor) {
  return instrutor && parseId(instrutor.id) !== null && parseId(instrutor.usuario_id) !== null
    && typeof instrutor.criado_em === 'string';
}

// Keep the wall-clock representation supplied by SQLite; do not infer a zone.
export function formatInstrutorDate(value) {
  if (typeof value !== 'string') return 'Data indisponível';
  const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(value);
  if (!match) return 'Data indisponível';
  const [, year, month, day, hour, minute, second] = match;
  const y = Number(year), m = Number(month), d = Number(day);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (y < 1 || m < 1 || m > 12 || d < 1 || d > days[m - 1]
    || Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59) return 'Data indisponível';
  return `${day}/${month}/${year} ${hour}:${minute}`;
}

function cell(value) {
  const td = document.createElement('td');
  td.textContent = value;
  return td;
}

function button(label, action) {
  const result = document.createElement('button');
  result.type = 'button';
  result.className = 'btn btn-outline-secondary';
  result.textContent = label;
  result.addEventListener('click', action);
  return result;
}

// Aluno history does not affect eligibility for a new Instrutor record.
function eligibleUsers() {
  const registered = new Set(instrutores.map((instrutor) => instrutor.usuario_id));
  return [...users.values()].filter((user) => profile && user.ativo === true
    && user.perfil_id === profile.id && !registered.has(user.id));
}

function renderOptions() {
  const select = element('instrutor-existing-user');
  const previous = select.value;
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Selecione uma conta';
  select.replaceChildren(placeholder);
  const eligible = eligibleUsers();
  for (const user of eligible) {
    const option = document.createElement('option');
    option.value = user.id;
    option.textContent = `${user.nome} — ${user.email}`;
    select.append(option);
  }
  select.value = eligible.some((user) => user.id === previous) ? previous : '';
  text('instrutor-existing-help', eligible.length ? 'Contas ativas com perfil Instrutor que ainda não possuem cadastro como Instrutor.'
    : 'Nenhuma conta elegível disponível. Atualize a listagem ou crie uma nova conta.');
}

function controls() {
  const locked = loading || submitting;
  const canCreate = snapshotReady && profile !== null && !profilesLoading;
  element('refresh-instrutores').disabled = locked || profilesLoading;
  element('retry-instrutores').disabled = locked || profilesLoading;
  element('create-instrutor').disabled = locked || (!canCreate && pendingUser === null && !accountUnconfirmed);
  element('instrutores-panel').setAttribute('aria-busy', String(loading));
  for (const name of ['create', 'edit']) element(`instrutor-${name}-form`).setAttribute('aria-busy', String(submitting));
  element('instrutor-status-modal').setAttribute('aria-busy', String(submitting));
  for (const name of ['create', 'edit', 'status']) {
    for (const control of element(`instrutor-${name}-modal`).querySelectorAll('button, input, select')) control.disabled = locked;
  }
  const existing = element('instrutor-create-mode').value === 'existing';
  const recovery = pendingUser !== null || accountUnconfirmed;
  element('instrutor-create-mode').disabled = locked || recovery;
  element('instrutor-new-fields').hidden = existing || recovery;
  element('instrutor-existing-fields').hidden = !existing || recovery;
  for (const field of ['name', 'email', 'password']) element(`instrutor-create-${field}`).disabled = locked || existing || recovery;
  element('instrutor-existing-user').disabled = locked || !existing || recovery;
  element('instrutor-create-submit').hidden = recovery;
  element('instrutor-create-submit').disabled = locked || !canCreate || uncertain
    || (existing && !eligibleUsers().some((user) => user.id === element('instrutor-existing-user').value));
  element('instrutor-complete').hidden = pendingUser === null;
  element('instrutor-complete').disabled = locked || !canCreate;
  element('instrutor-end-attempt').hidden = pendingUser === null;
  element('instrutor-reconcile').hidden = !accountUnconfirmed && !uncertain;
  element('instrutor-edit-submit').disabled = locked || uncertain;
  element('instrutor-status-submit').disabled = locked || uncertain;
  if (element('instrutores-empty-create')) element('instrutores-empty-create').disabled = locked || !canCreate;
  for (const action of element('instrutores-rows').querySelectorAll('button')) {
    action.disabled = locked || uncertain || action.dataset.unavailable === 'true';
  }
}

function render() {
  const rows = document.createDocumentFragment();
  for (const instrutor of instrutores) {
    const user = users.get(instrutor.usuario_id);
    const row = document.createElement('tr');
    const name = user ? user.nome : 'Dados do usuário indisponíveis';
    row.append(cell(name), cell(user ? user.email : 'Indisponível'));
    const status = cell('');
    if (user) {
      const badge = document.createElement('span');
      badge.className = `status-badge${user.ativo ? '' : ' inactive'}`;
      badge.textContent = user.ativo ? 'Ativo' : 'Inativo';
      status.append(badge);
    } else status.textContent = 'Indisponível';
    row.append(status, cell(formatInstrutorDate(instrutor.criado_em)));
    const actions = cell('');
    const group = document.createElement('div');
    group.className = 'd-flex flex-wrap gap-2';
    const edit = button('Editar', () => openEdit(user, edit));
    const change = button(user?.ativo === false ? 'Ativar' : 'Desativar', () => openStatus(user, change));
    edit.setAttribute('aria-label', `Editar conta de ${name}`);
    change.setAttribute('aria-label', `${user?.ativo === false ? 'Ativar' : 'Desativar'} conta de ${name}`);
    edit.dataset.unavailable = String(!user);
    const self = user?.ativo === true && user.id === context.userId;
    change.dataset.unavailable = String(!user || self);
    if (self) {
      const explanation = document.createElement('span');
      explanation.id = `instrutor-self-${instrutor.id}`;
      explanation.className = 'small';
      explanation.textContent = 'Você não pode desativar a própria conta.';
      change.setAttribute('aria-describedby', explanation.id);
      actions.append(explanation);
    }
    group.append(edit, change);
    actions.append(group);
    row.append(actions);
    rows.append(row);
  }
  element('instrutores-rows').replaceChildren(rows);
  text('instrutores-count', `${instrutores.length} ${instrutores.length === 1 ? 'instrutor' : 'instrutores'}`);
  element('instrutores-error').hidden = true;
  element('instrutores-state').hidden = instrutores.length !== 0;
  element('instrutores-table-container').hidden = instrutores.length === 0;
  const empty = document.createElement('p');
  empty.textContent = 'Nenhum instrutor cadastrado.';
  element('instrutores-state').replaceChildren(empty);
  if (profile && snapshotReady) {
    const create = button('Cadastrar instrutor', () => openCreate(create));
    create.id = 'instrutores-empty-create';
    element('instrutores-state').append(create);
  }
  renderOptions();
  controls();
}

async function snapshot() {
  const results = await Promise.allSettled([
    getJson('/api/instrutores'), getJson(`/api/usuarios?academia_id=${context.academiaId}`),
  ]);
  // Keep the load locked until both reads settle, even when one fails early.
  const failed = results.find((result) => result.status === 'rejected' && result.reason.status === 401)
    || results.find((result) => result.status === 'rejected');
  if (failed) throw failed.reason;
  const [records, accounts] = results.map((result) => result.value);
  if (!Array.isArray(records) || !records.every(validInstrutor) || !Array.isArray(accounts) || !accounts.every(validUser)
    || new Set(records.map((record) => record.id)).size !== records.length
    || new Set(records.map((record) => record.usuario_id)).size !== records.length
    || new Set(accounts.map((account) => account.id)).size !== accounts.length) throw new ApiError(502);
  // A fresh snapshot always requires an explicit selection of an existing account.
  element('instrutor-existing-user').value = '';
  instrutores = records;
  users = new Map(accounts.map((user) => [user.id, user]));
  snapshotReady = true;
  uncertain = false;
  render();
}

async function loadProfiles() {
  if (profilesLoading) return;
  profilesLoading = true;
  profile = null;
  text('instrutores-registration-info', 'Consultando disponibilidade do cadastro...');
  controls();
  try {
    const profiles = await getJson('/api/perfis');
    if (!Array.isArray(profiles) || profiles.some((item) => !item || parseId(item.id) === null
      || typeof item.nome !== 'string' || ![0, 1].includes(item.ativo))) throw new ApiError(502);
    profile = profiles.find((item) => item.nome === 'Instrutor' && item.ativo === 1) || null;
    text('instrutores-registration-info', profile ? 'Cadastro disponível para novas contas e usuários elegíveis.'
      : 'Cadastro indisponível: o perfil Instrutor está ausente ou inativo. Procure a administração.');
  } catch (error) {
    if (!sessionExpired(error)) text('instrutores-registration-info', `Cadastro indisponível. ${errorMessage(error)} Use Atualizar listagem para consultar novamente.`);
  } finally {
    profilesLoading = false;
    if (snapshotReady) render();
    controls();
  }
}

export async function loadInstrutores() {
  if (!context || loading || submitting || profilesLoading) return;
  visited = true;
  loading = true;
  snapshotReady = false;
  element('instrutores-error').hidden = true;
  element('instrutores-table-container').hidden = true;
  element('instrutores-state').hidden = false;
  const spinner = document.createElement('span');
  spinner.className = 'spinner-border spinner-border-sm';
  spinner.setAttribute('aria-hidden', 'true');
  const message = document.createElement('p');
  message.textContent = 'Carregando instrutores...';
  element('instrutores-state').replaceChildren(spinner, message);
  text('instrutores-count', 'Consultando');
  text('instrutores-feedback', '');
  controls();
  // Profile failures must not determine the result of the independent listing.
  const metadata = loadProfiles();
  try {
    await snapshot();
    if (accountUnconfirmed) {
      accountUnconfirmed = false;
      element('instrutor-create-mode').value = 'existing';
      element('instrutor-existing-user').value = '';
      text('instrutor-create-feedback', 'Dados atualizados. Confira as contas elegíveis e selecione explicitamente a conta desejada.');
    }
  } catch (error) {
    if (!sessionExpired(error)) {
      text('instrutores-error-title', error.status === 403 ? 'Sem permissão para consultar instrutores.' : 'Não foi possível carregar os instrutores.');
      text('instrutores-error-message', errorMessage(error));
      text('instrutores-count', error.status === 403 ? 'Sem permissão' : 'Indisponível');
      element('instrutores-state').hidden = true;
      element('instrutores-error').hidden = false;
    }
  } finally {
    loading = false;
    controls();
    await metadata;
  }
}

export function visitInstrutores() {
  if (context && !visited) return loadInstrutores();
}

function showModal(name, opener, focus) {
  const recovering = name === 'create' && (pendingUser !== null || accountUnconfirmed);
  if (loading || submitting || (!snapshotReady && !recovering)) return;
  openers.set(name, opener);
  const modal = element(`instrutor-${name}-modal`);
  modal.addEventListener('shown.bs.modal', () => element(focus).focus(), { once: true });
  window.bootstrap.Modal.getOrCreateInstance(modal).show();
}

function hideModal(name) {
  allowHide = true;
  window.bootstrap?.Modal.getInstance(element(`instrutor-${name}-modal`))?.hide();
  allowHide = false;
}

function openCreate(opener) {
  if (!profile && pendingUser === null && !accountUnconfirmed) return;
  if (!pendingUser && !accountUnconfirmed) {
    text('instrutor-create-feedback', uncertain ? 'Atualize os dados antes de realizar outra escrita.' : '');
  }
  renderOptions();
  controls();
  showModal('create', opener, pendingUser ? (element('instrutor-complete').disabled ? 'instrutor-end-attempt' : 'instrutor-complete') : accountUnconfirmed || uncertain
    ? 'instrutor-reconcile' : 'instrutor-create-mode');
}

function openEdit(user, opener) {
  if (!user || uncertain || submitting || loading) return;
  selectedUser = user.id;
  element('instrutor-edit-name').value = user.nome;
  element('instrutor-edit-email').value = user.email;
  for (const field of ['name', 'email']) element(`instrutor-edit-${field}`).removeAttribute('aria-invalid');
  text('instrutor-edit-feedback', '');
  showModal('edit', opener, 'instrutor-edit-name');
}

function openStatus(user, opener) {
  if (!user || uncertain || submitting || loading || (user.ativo && user.id === context.userId)) return;
  selectedUser = user.id;
  desiredStatus = !user.ativo;
  text('instrutor-status-question', `${desiredStatus ? 'Ativar' : 'Desativar'} a conta de ${user.nome}?`);
  text('instrutor-status-explanation', desiredStatus ? 'A conta voltará a permitir autenticação conforme as regras do servidor.'
    : 'Desativar a conta impede que o usuário faça login. O cadastro como Instrutor será preservado.');
  text('instrutor-status-feedback', '');
  text('instrutor-status-submit', desiredStatus ? 'Ativar conta' : 'Desativar conta');
  showModal('status', opener, 'instrutor-status-submit');
}

function validFields(prefix, password = false) {
  const fields = ['name', 'email', ...(password ? ['password'] : [])];
  for (const field of fields) {
    const input = element(`instrutor-${prefix}-${field}`);
    input.setCustomValidity(field === 'name' && !input.value.trim() ? 'Informe um nome.' : '');
    input.setAttribute('aria-invalid', String(!input.validity.valid));
  }
  return element(`instrutor-${prefix}-form`).reportValidity();
}

function operationFeedback(name, message) {
  text(`instrutor-${name}-feedback`, message);
  element(`instrutor-${name}-feedback`).focus();
}

function completed(instrutor) {
  if (!validInstrutor(instrutor) || instrutor.usuario_id !== pendingUser) throw new ApiError(502);
  if (!instrutores.some((item) => item.id === instrutor.id)) instrutores.push(instrutor);
  pendingUser = null;
  accountUnconfirmed = false;
  uncertain = false;
  element('instrutor-create-form').reset();
  render();
  hideModal('create');
  text('instrutores-feedback', 'Instrutor cadastrado com sucesso.');
}

async function createInstrutorRecord() {
  try {
    const instrutor = await postJson('/api/instrutores', { usuario_id: pendingUser });
    completed(instrutor);
  } catch (error) {
    if (sessionExpired(error)) return;
    uncertain = ambiguous(error) || error.status === 409;
    operationFeedback('create', `Conta de usuário confirmada: ${users.get(pendingUser)?.nome || 'Conta'} (ID ${pendingUser}). O cadastro como Instrutor não foi confirmado. ${errorMessage(error)} Use Tentar concluir cadastro do instrutor; os dados serão consultados antes de uma nova tentativa.`);
  }
}

async function submitCreate(event) {
  event.preventDefault();
  if (submitting || loading || uncertain || !profile || !snapshotReady || pendingUser || accountUnconfirmed) return;
  const existing = element('instrutor-create-mode').value === 'existing';
  if (!existing && !validFields('create', true)) return;
  const chosen = element('instrutor-existing-user').value;
  if (existing && !eligibleUsers().some((user) => user.id === chosen)) {
    operationFeedback('create', 'Selecione uma conta elegível.');
    return;
  }
  submitting = true;
  controls();
  text('instrutor-create-feedback', 'Cadastrando instrutor...');
  try {
    if (existing) pendingUser = chosen;
    else {
      // The password exists only in the input and this request DTO. Clear the
      // input immediately after dispatch, including synchronous validation errors.
      let request;
      try {
        request = postJson('/api/usuarios', { academia_id: context.academiaId, perfil_id: profile.id,
          nome: element('instrutor-create-name').value, email: element('instrutor-create-email').value,
          senha: element('instrutor-create-password').value });
      } finally { element('instrutor-create-password').value = ''; }
      const user = await request;
      if (!validUser(user)) throw new ApiError(502);
      users.set(user.id, user);
      pendingUser = user.id;
    }
    await createInstrutorRecord();
  } catch (error) {
    if (!sessionExpired(error)) {
      accountUnconfirmed = ambiguous(error);
      uncertain = accountUnconfirmed;
      operationFeedback('create', accountUnconfirmed
        ? 'O resultado da criação da conta não pôde ser confirmado. Atualize os dados antes de tentar novamente.' : errorMessage(error));
    }
  } finally {
    element('instrutor-create-password').value = '';
    submitting = false;
    controls();
  }
}

async function completePending() {
  if (submitting || loading || !pendingUser || !profile) return;
  submitting = true;
  controls();
  text('instrutor-create-feedback', 'Consultando o cadastro antes de concluir...');
  try {
    await snapshot();
    const existing = instrutores.find((instrutor) => instrutor.usuario_id === pendingUser);
    if (existing) completed(existing);
    else if (!eligibleUsers().some((user) => user.id === pendingUser)) {
      operationFeedback('create', 'A conta não está mais elegível. Procure a administração.');
    } else await createInstrutorRecord();
  } catch (error) {
    if (!sessionExpired(error)) operationFeedback('create', `Não foi possível reconciliar o cadastro. ${errorMessage(error)}`);
  } finally { submitting = false; controls(); }
}

function endPendingAttempt() {
  if (submitting || loading || pendingUser === null) return;
  // Ending an attempt discards only local registration state. The confirmed
  // account remains intact, and an uncertain write still requires a refresh.
  pendingUser = null;
  accountUnconfirmed = false;
  element('instrutor-create-form').reset();
  element('instrutor-create-mode').value = 'new';
  element('instrutor-existing-user').value = '';
  element('instrutor-create-password').value = '';
  for (const field of ['name', 'email', 'password']) {
    element(`instrutor-create-${field}`).setCustomValidity('');
    element(`instrutor-create-${field}`).removeAttribute('aria-invalid');
  }
  text('instrutor-create-feedback', uncertain
    ? 'Tentativa encerrada. A conta de usuário permanece intacta. Atualize os dados antes de outra escrita.'
    : 'Tentativa encerrada. A conta de usuário permanece intacta.');
  renderOptions();
  controls();
  element('instrutor-create-mode').focus();
}

async function updateUser(name, dto) {
  if (submitting || loading || uncertain || !selectedUser || !snapshotReady) return;
  const userId = selectedUser;
  submitting = true;
  controls();
  text(`instrutor-${name}-feedback`, 'Salvando...');
  try {
    const user = await putJson(`/api/usuarios/${userId}${name === 'status' ? '/status' : ''}`, dto);
    if (!validUser(user) || user.id !== userId) throw new ApiError(502);
    users.set(user.id, user);
    render();
    hideModal(name);
    text('instrutores-feedback', name === 'edit' ? 'Dados da conta atualizados.' : 'Situação da conta atualizada.');
  } catch (error) {
    if (!sessionExpired(error)) {
      uncertain = ambiguous(error);
      const message = uncertain ? 'O resultado da alteração não pôde ser confirmado. Feche este diálogo e atualize a listagem antes de tentar novamente.'
        : errorMessage(error);
      operationFeedback(name, message);
      if (uncertain) text('instrutores-feedback', message);
    }
  } finally { submitting = false; controls(); }
}

export function initInstrutores(authContext) {
  context = authContext;
  if (initialized) return;
  initialized = true;
  element('refresh-instrutores').addEventListener('click', loadInstrutores);
  element('retry-instrutores').addEventListener('click', loadInstrutores);
  element('create-instrutor').addEventListener('click', (event) => openCreate(event.currentTarget));
  element('instrutor-create-mode').addEventListener('change', () => {
    if (element('instrutor-create-mode').value === 'existing') element('instrutor-create-password').value = '';
    element('instrutor-existing-user').value = '';
    controls();
  });
  element('instrutor-existing-user').addEventListener('change', controls);
  element('instrutor-create-form').addEventListener('submit', submitCreate);
  element('instrutor-complete').addEventListener('click', completePending);
  element('instrutor-end-attempt').addEventListener('click', endPendingAttempt);
  element('instrutor-reconcile').addEventListener('click', loadInstrutores);
  element('instrutor-edit-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (submitting || !validFields('edit')) return;
    return updateUser('edit', { nome: element('instrutor-edit-name').value, email: element('instrutor-edit-email').value });
  });
  element('instrutor-status-submit').addEventListener('click', () => updateUser('status', { ativo: desiredStatus }));
  for (const name of ['create', 'edit', 'status']) {
    const modal = element(`instrutor-${name}-modal`);
    modal.addEventListener('hide.bs.modal', (event) => { if (submitting && !allowHide) event.preventDefault(); });
    modal.addEventListener('hidden.bs.modal', () => {
      element('instrutor-create-password').value = '';
      const opener = openers.get(name);
      (opener?.isConnected && !opener.disabled ? opener : element('create-instrutor').disabled
        ? element('refresh-instrutores') : element('create-instrutor')).focus();
    });
  }
  for (const prefix of ['create', 'edit']) {
    for (const field of ['name', 'email']) element(`instrutor-${prefix}-${field}`).addEventListener('input', (event) => {
      event.target.setCustomValidity('');
      event.target.removeAttribute('aria-invalid');
    });
  }
  window.addEventListener('pagehide', () => { element('instrutor-create-password').value = ''; });
}
