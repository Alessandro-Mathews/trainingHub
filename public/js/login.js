import { login, getAuthContext, parseAcademiaCode } from './api.js';

const form = document.getElementById('login-form');
const academia = document.getElementById('academia-code');
const email = document.getElementById('login-email');
const password = document.getElementById('login-password');
const feedback = document.getElementById('login-feedback');
const submit = document.getElementById('login-submit');
let busy = true;

function loading(active, text = 'Entrando...') {
  busy = active;
  form.setAttribute('aria-busy', String(active));
  submit.disabled = active;
  document.getElementById('login-spinner').hidden = !active;
  document.getElementById('login-submit-text').textContent = active ? text : 'Entrar';
}

function message(text, isError = false) {
  feedback.textContent = text;
  feedback.classList.toggle('auth-feedback-error', isError);
}

function authError(error, checkingContext) {
  if (error.status === 0) return 'Não foi possível conectar ao TrainingHub.';
  if (error.status === 403) return 'Sua conta não tem permissão para acessar esta área.';
  if (error.status === 401) return checkingContext
    ? 'Sua sessão não está disponível. Entre novamente.'
    : 'Não foi possível entrar. Verifique suas credenciais.';
  if (error.status === 400) return 'Confira os dados informados.';
  return 'Não foi possível entrar agora. Tente novamente.';
}

for (const input of [academia, email, password]) {
  input.addEventListener('input', () => {
    input.setCustomValidity('');
    input.removeAttribute('aria-invalid');
  });
}

function validForm() {
  academia.setCustomValidity(!academia.value ? 'Informe o código da academia.'
    : parseAcademiaCode(academia.value) === null ? 'Informe um código da academia inteiro positivo válido.' : '');
  email.setCustomValidity(!email.value ? 'Informe seu e-mail.'
    : email.validity.typeMismatch ? 'Informe um e-mail válido.' : '');
  password.setCustomValidity(!password.value ? 'Informe sua senha.' : '');
  for (const input of [academia, email, password]) {
    input.setAttribute('aria-invalid', String(!input.validity.valid));
  }
  if (form.reportValidity()) return true;
  message('Confira os dados informados.', true);
  return false;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !validForm()) return;
  loading(true);
  message('Entrando...');
  let checkingContext = false;
  try {
    await login(academia.value, email.value, password.value);
    password.value = '';
    checkingContext = true;
    await getAuthContext();
    location.replace('/index.html');
  } catch (error) {
    message(authError(error, checkingContext), true);
    feedback.focus();
  } finally {
    password.value = '';
    loading(false);
  }
});

async function checkSession() {
  loading(true, 'Aguarde...');
  try {
    await getAuthContext();
    location.replace('/index.html');
  } catch (error) {
    message(error.status === 401 ? '' : authError(error, true), error.status !== 401);
  } finally {
    loading(false);
  }
}

window.addEventListener('pagehide', () => { password.value = ''; });
window.addEventListener('pageshow', (event) => {
  if (event.persisted) location.reload();
});
checkSession();
