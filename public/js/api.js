// All requests use the TrainingHub origin; no external service is required.
export async function getJson(path) {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error('Request failed');
  return response.json();
}
