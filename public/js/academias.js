import { getJson } from './api.js';

const element = (id) => document.getElementById(id);
let loading = false;

function cell(value, className) {
  const td = document.createElement('td');
  td.textContent = value ?? 'Não informado';
  if (className) td.className = className;
  return td;
}

function renderRows(academias) {
  const rows = document.createDocumentFragment();
  for (const academia of academias) {
    const row = document.createElement('tr');
    row.append(cell(academia.id), cell(academia.nome, 'academy-name'), cell(academia.cnpj));
    const contact = cell(academia.email);
    const phone = document.createElement('span');
    phone.className = 'contact-detail';
    phone.textContent = academia.telefone ?? 'Telefone não informado';
    contact.append(phone);
    const status = cell('');
    const badge = document.createElement('span');
    badge.className = `status-badge${academia.ativo ? '' : ' inactive'}`;
    badge.textContent = academia.ativo ? 'Ativa' : 'Inativa';
    status.append(badge);
    row.append(contact, status);
    rows.append(row);
  }
  element('academias-rows').replaceChildren(rows);
}

export async function loadAcademias() {
  if (loading) return;
  loading = true;
  const panel = element('academias-panel');
  const state = element('academias-state');
  const refresh = element('refresh-academias');
  panel.setAttribute('aria-busy', 'true');
  refresh.disabled = true;
  element('academias-error').hidden = true;
  element('academias-table-container').hidden = true;
  element('academias-rows').replaceChildren();
  state.hidden = false;
  state.replaceChildren();
  const spinner = document.createElement('span');
  spinner.className = 'spinner-border spinner-border-sm';
  spinner.setAttribute('aria-hidden', 'true');
  const message = document.createElement('p');
  message.textContent = 'Carregando academias...';
  state.append(spinner, message);
  element('academias-total').textContent = '—';
  element('academias-summary').textContent = 'Consultando academias…';
  element('academias-count').textContent = 'Consultando';
  try {
    const academias = await getJson('/api/academias');
    if (!Array.isArray(academias) || academias.some((item) =>
      item === null || typeof item !== 'object' || !Number.isInteger(item.id) ||
      typeof item.nome !== 'string' || typeof item.ativo !== 'boolean')) {
      throw new Error('Invalid response');
    }
    element('academias-total').textContent = String(academias.length);
    element('academias-summary').textContent = 'Total de academias na listagem';
    element('academias-count').textContent = `${academias.length} ${academias.length === 1 ? 'academia' : 'academias'}`;
    if (academias.length === 0) {
      message.textContent = 'Nenhuma academia cadastrada.';
      state.replaceChildren(message);
    } else {
      renderRows(academias);
      state.hidden = true;
      element('academias-table-container').hidden = false;
    }
  } catch {
    state.hidden = true;
    element('academias-error').hidden = false;
    element('academias-count').textContent = 'Indisponível';
    element('academias-summary').textContent = 'Não foi possível consultar a listagem';
  } finally {
    panel.setAttribute('aria-busy', 'false');
    refresh.disabled = false;
    loading = false;
  }
}
