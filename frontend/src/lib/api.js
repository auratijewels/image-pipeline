const BASE = '/api'

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${path}: ${detail}`)
  }
  return res.json()
}

export const api = {
  health: () => req('/health'),
  assetTypes: () => req('/asset-types'),
  formats: () => req('/formats'),
  anatomy: () => req('/anatomy'),
  costs: () => req('/costs'),
}
