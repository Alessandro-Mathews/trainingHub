import { getJson, getAuthContext, logout } from './api.js';
import { loadAcademias } from './academias.js';

const pages = ['dashboard', 'academias'];

function navigate(moveFocus = true) {
  const requested = location.hash.slice(1);
  const page = pages.includes(requested) ? requested : 'dashboard';
  for (const name of pages) document.getElementById(name).hidden = name !== page;
  for (const link of document.querySelectorAll('[data-page]')) {
    const active = link.dataset.page === page;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  const title = page === 'dashboard' ? 'Dashboard' : 'Academias';
  document.getElementById('page-context').textContent = title;
  document.title = `${title} | TrainingHub`;
  const sidebar = document.getElementById('sidebar');
  const drawer = window.bootstrap?.Offcanvas.getInstance(sidebar);
  const focusContent = () => document.getElementById('main-content').focus();
  if (drawer && sidebar.classList.contains('show')) {
    if (moveFocus) sidebar.addEventListener('hidden.bs.offcanvas', focusContent, { once: true });
    drawer.hide();
  } else if (moveFocus) focusContent();
}

async function loadHealth(path, id, healthy, label) {
  const target = document.getElementById(id);
  try {
    const result = await getJson(path);
    const available = healthy(result);
    target.textContent = available ? label : 'Indisponível';
    target.classList.toggle('available', available);
  } catch {
    target.textContent = 'Indisponível';
  }
}

const logo = document.getElementById('brand-logo');
function useTextLogo() {
  logo.hidden = true;
  logo.closest('.brand').classList.add('logo-missing');
}
logo.addEventListener('error', useTextLogo);
if (logo.complete && logo.naturalWidth === 0) useTextLogo();

window.addEventListener('hashchange', () => navigate());
for (const link of document.querySelectorAll('.sidebar a[href^="#"]')) {
  link.addEventListener('click', () => {
    if (location.hash === link.hash) navigate();
  });
}
document.getElementById('refresh-academias').addEventListener('click', loadAcademias);
document.getElementById('retry-academias').addEventListener('click', loadAcademias);
navigate(false);

const authenticatedApp = document.getElementById('authenticated-app');
const sessionState = document.getElementById('session-state');
const sessionTitle = document.getElementById('session-title');
const sessionMessage = document.getElementById('session-message');
const retrySession = document.getElementById('retry-session');
const sessionLogout = document.getElementById('session-logout');
const logoutButton = document.getElementById('logout-button');
let checkingSession = false;
let loggingOut = false;

async function checkSession() {
  if (checkingSession || loggingOut) return;
  checkingSession = true;
  authenticatedApp.hidden = true;
  sessionState.hidden = false;
  sessionState.setAttribute('aria-busy', 'true');
  sessionTitle.textContent = 'Verificando sessão...';
  sessionMessage.textContent = 'Aguarde para acessar seu painel.';
  retrySession.hidden = true;
  sessionLogout.hidden = true;
  try {
    await getAuthContext();
    sessionState.hidden = true;
    authenticatedApp.hidden = false;
    loadAcademias();
    loadHealth('/api/health', 'system-status', (data) => data?.status === 'ok' && data.application === 'TrainingHub', 'Operacional');
    loadHealth('/api/health/database', 'database-status', (data) => data?.status === 'ok' && data.database === 'connected', 'Conectado');
  } catch (error) {
    if (error.status === 401) {
      location.replace('/login.html');
      return;
    }
    sessionTitle.textContent = error.status === 403 ? 'Acesso indisponível' : 'Não foi possível acessar o painel.';
    sessionMessage.textContent = error.status === 403 ? 'Sua conta não tem permissão para acessar esta área.'
      : error.status === 0 ? 'Não foi possível conectar ao TrainingHub.' : 'Tente novamente em instantes.';
    retrySession.hidden = false;
    sessionLogout.hidden = false;
  } finally {
    sessionState.setAttribute('aria-busy', 'false');
    checkingSession = false;
  }
}

async function endSession() {
  if (loggingOut || checkingSession) return;
  loggingOut = true;
  logoutButton.disabled = sessionLogout.disabled = true;
  authenticatedApp.hidden = true;
  sessionState.hidden = false;
  sessionState.setAttribute('aria-busy', 'true');
  sessionTitle.textContent = 'Encerrando sessão...';
  sessionMessage.textContent = 'Aguarde...';
  retrySession.hidden = true;
  sessionLogout.hidden = false;
  try {
    await logout();
    location.replace('/login.html');
  } catch (error) {
    sessionTitle.textContent = 'Não foi possível sair.';
    sessionMessage.textContent = error.status === 0 ? 'Não foi possível conectar ao TrainingHub.'
      : 'Não foi possível sair agora. Tente novamente.';
    retrySession.hidden = false;
    sessionMessage.focus();
  } finally {
    loggingOut = false;
    logoutButton.disabled = sessionLogout.disabled = false;
    sessionState.setAttribute('aria-busy', 'false');
  }
}

retrySession.addEventListener('click', checkSession);
logoutButton.addEventListener('click', endSession);
sessionLogout.addEventListener('click', endSession);
window.addEventListener('pagehide', () => { authenticatedApp.hidden = true; });
window.addEventListener('pageshow', (event) => {
  if (event.persisted) location.reload();
});
checkSession();
