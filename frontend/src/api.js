import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
})

/**
 * Tải lên một bộ chứng từ.
 * @param {File[]} files
 * @param {string} [referenceLabel] Số hoá đơn / tên chứng từ do người dùng nhập.
 * @param {(pct:number)=>void} [onProgress] Báo tiến độ tải lên (0-100).
 */
export async function uploadBatch(files, referenceLabel, onProgress) {
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  fd.append('reference_label', referenceLabel || '')

  const { data } = await api.post('/api/v1/audit/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
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
