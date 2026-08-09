const BASE = '/api'

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (res.status === 204) return null
  const body = await res.text()
  if (!res.ok) {
    throw new Error(detailOf(body) || `${res.status} ${res.statusText}`)
  }
  return body ? JSON.parse(body) : null
}

/** FastAPI puts errors in `detail`, which is a string for HTTPException and an
 *  array of field errors for validation failures. Flatten both to one line. */
function detailOf(body) {
  try {
    const { detail } = JSON.parse(body)
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((e) => {
          const field = (e.loc || []).filter((p) => p !== 'body').join('.')
          return field ? `${field}: ${e.msg}` : e.msg
        })
        .join('; ')
    }
  } catch {
    /* not JSON — fall through */
  }
  return body
}

const json = (method, payload) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const api = {
  health: () => req('/health'),
  assetTypes: () => req('/asset-types'),
  formats: () => req('/formats'),
  anatomy: () => req('/anatomy'),
  categories: () => req('/categories'),
  angles: () => req('/angles'),
  costs: () => req('/costs'),

  listProducts: () => req('/products'),
  getProduct: (id) => req(`/products/${id}`),
  createProduct: (payload) => req('/products', json('POST', payload)),
  updateProduct: (id, payload) => req(`/products/${id}`, json('PATCH', payload)),
  deleteProduct: (id) => req(`/products/${id}`, { method: 'DELETE' }),

  uploadAngle: (id, angle, file) => {
    const form = new FormData()
    form.append('file', file)
    return req(`/products/${id}/angles/${angle}`, { method: 'PUT', body: form })
  },
  deleteAngle: (id, angle) => req(`/products/${id}/angles/${angle}`, { method: 'DELETE' }),
  angleImageUrl: (id, angle, stamp) =>
    `${BASE}/products/${id}/angles/${angle}/raw${stamp ? `?v=${stamp}` : ''}`,
}
