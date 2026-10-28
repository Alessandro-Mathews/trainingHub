import { getJson } from './api.js';
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
loadAcademias();
loadHealth('/api/health', 'system-status', (data) => data?.status === 'ok' && data.application === 'TrainingHub', 'Operacional');
loadHealth('/api/health/database', 'database-status', (data) => data?.status === 'ok' && data.database === 'connected', 'Conectado');
