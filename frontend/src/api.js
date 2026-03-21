/**
 * API client for SLM Evaluation backend (FastAPI at localhost:8000).
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function fetchApi(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  return res.json();
}

export async function getStatus() {
  return fetchApi('/status');
}

export async function getResults() {
  return fetchApi('/results');
}

export async function getValidationSummary() {
  return fetchApi('/validation-summary');
}

export async function getVariance() {
  return fetchApi('/variance');
}

export async function getConfigModels() {
  return fetchApi('/config/models');
}

export async function getPrompts() {
  return fetchApi('/config/prompts');
}

export async function getSystemProfile() {
  return fetchApi('/system-profile');
}

export async function triggerRun(phase = 1) {
  return fetchApi(`/run?phase=${phase}`, { method: 'POST' });
}

export async function triggerTemperatureRun() {
  return fetchApi('/temperature-run', { method: 'POST' });
}
