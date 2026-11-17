// All requests use the TrainingHub origin; no external service is required.
export class ApiError extends Error {
  constructor(status) {
    super('Request failed');
    this.name = 'ApiError';
    this.status = status;
  }
}

const idKeys = new Set(['id', 'academia_id', 'perfil_id', 'usuario_id', 'instrutor_id',
  'aluno_id', 'userId', 'academiaId', 'perfilId']);

export function parseId(value) {
  if (typeof value !== 'string' || !/^[1-9][0-9]*$/.test(value)) return null;
  if (value.length > 19 || BigInt(value) > 9223372036854775807n) return null;
  return value;
}

// Parse ID number tokens before Number can round them. Other primitives retain
// JSON.parse semantics. This is a grammar parser, not a text replacement pass.
export function parseJson(text) {
  let at = 0;
  const fail = () => { throw new SyntaxError('Invalid JSON response'); };
  const space = () => { while (at < text.length && /[\t\n\r ]/.test(text[at])) at++; };
  function string() {
    const start = at++;
    while (at < text.length) {
      const char = text[at++];
      if (char === '"') return JSON.parse(text.slice(start, at));
      if (char === '\\') at++;
    }
    return fail();
  }
  function value(key, depth = 0) {
    if (depth > 128) return fail();
    space();
    const char = text[at];
    if (idKeys.has(key)) {
      if (key === 'instrutor_id' && text.slice(at, at + 4) === 'null') { at += 4; return null; }
      const match = /^[1-9][0-9]*/.exec(text.slice(at));
      if (!match || parseId(match[0]) === null) return fail();
      at += match[0].length;
      return match[0];
    }
    if (char === '"') return string();
    if (char === '{' || char === '[') {
      at++;
      const object = char === '{';
      const result = object ? {} : [];
      const end = object ? '}' : ']';
      space();
      if (text[at] === end) { at++; return result; }
      while (at < text.length) {
        space();
        let member;
        if (object) {
          if (text[at] !== '"') return fail();
          member = string();
          space();
          if (text[at++] !== ':') return fail();
        }
        const parsed = value(member, depth + 1);
        if (object) Object.defineProperty(result, member, { value: parsed, enumerable: true, configurable: true, writable: true });
        else result.push(parsed);
        space();
        if (text[at] === end) { at++; return result; }
        if (text[at++] !== ',') return fail();
      }
      return fail();
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.slice(at));
    if (!token) return fail();
    at += token[0].length;
    return JSON.parse(token[0]);
  }
  const result = value();
  space();
  if (at !== text.length) return fail();
  return result;
}

// Application DTOs are flat. Only validated ID strings may become raw JSON
// numbers; all other fields use the native string escaping and scalar encoding.
export function serializeBody(dto) {
  if (!dto || Object.getPrototypeOf(dto) !== Object.prototype) throw new ApiError(400);
  return '{' + Object.entries(dto).map(([key, value]) => {
    let encoded;
    if (idKeys.has(key)) {
      encoded = parseId(value);
      if (encoded === null) throw new ApiError(400);
    } else {
      if (!['string', 'boolean', 'number'].includes(typeof value) && value !== null) throw new ApiError(400);
      if (typeof value === 'number' && !Number.isFinite(value)) throw new ApiError(400);
      encoded = JSON.stringify(value);
    }
    return `${JSON.stringify(key)}:${encoded}`;
  }).join(',') + '}';
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
    return parseJson(await response.text());
  } catch (error) {
    throw new ApiError(error instanceof SyntaxError ? 502 : 0);
  }
}

export function getJson(path) {
  return requestJson(path);
}

export function postJson(path, dto) {
  return requestJson(path, 'POST', serializeBody(dto));
}

export function putJson(path, dto) {
  return requestJson(path, 'PUT', serializeBody(dto));
}

export function parseAcademiaCode(value) {
  return parseId(value);
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
    parseId(context[key]) !== null)) {
    throw new ApiError(502);
  }
  return context;
}

export function logout() {
  return requestJson('/api/auth/logout', 'POST');
}
