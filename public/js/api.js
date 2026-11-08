// All requests use the TrainingHub origin; no external service is required.
export class ApiError extends Error {
  constructor(status) {
    super('Request failed');
    this.name = 'ApiError';
    this.status = status;
  }
}

async function requestJson(path, method = 'GET', body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      credentials: 'same-origin',
      cache: 'no-store',
      signal: AbortSignal.timeout(15000),
      ...(body === undefined ? {} : { body }),
    });
  } catch {
    throw new ApiError(0);
  }
  if (!response.ok) throw new ApiError(response.status);
  try {
    return await response.json();
  } catch (error) {
    throw new ApiError(error instanceof SyntaxError ? 502 : 0);
  }
}

export function getJson(path) {
  return requestJson(path);
}

export function parseAcademiaCode(value) {
  if (typeof value !== 'string' || !/^[1-9][0-9]*$/.test(value)) return null;
  if (value.length > 19 || BigInt(value) > 9223372036854775807n) return null;
  return value;
}

export async function login(academiaCode, email, senha) {
  const code = parseAcademiaCode(academiaCode);
  if (code === null) throw new ApiError(400);
  // Only the validated decimal is emitted as a JSON number. Strings are escaped
  // by JSON.stringify; no int64 is converted to a lossy JavaScript Number.
  const body = `{"academia_id":${code},"email":${JSON.stringify(email)},"senha":${JSON.stringify(senha)}}`;
  return requestJson('/api/auth/login', 'POST', body);
}

export async function getAuthContext() {
  const context = await getJson('/api/auth/me');
  if (!context || !['userId', 'academiaId', 'perfilId'].every((key) =>
    typeof context[key] === 'number' && Number.isInteger(context[key]) && context[key] > 0)) {
    throw new ApiError(502);
  }
  return context;
}

export function logout() {
  return requestJson('/api/auth/logout', 'POST');
}
