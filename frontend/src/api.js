import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
})

export async function uploadBatch(files) {
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  const { data } = await api.post('/api/v1/audit/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function listBatches(limit = 50, offset = 0) {
  const { data } = await api.get('/api/v1/audit/batches', { params: { limit, offset } })
  return data
}

export async function getBatch(batchId) {
  const { data } = await api.get(`/api/v1/audit/batches/${batchId}`)
  return data
}

export function exportCsvUrl(batchId) {
  const base = import.meta.env.VITE_API_BASE || ''
  return `${base}/api/v1/audit/batches/${batchId}/export`
}
