import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── Auth ────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  me: () => api.get('/auth/me'),
  register: (data) => api.post('/auth/register', data),
}

// ── Processes ───────────────────────────────────────────────────────────────
export const processApi = {
  list: () => api.get('/processes/'),
  config: () => api.get('/processes/config'),
  get: (id) => api.get(`/processes/${id}`),
  create: (data) => api.post('/processes/', data),
  run: (id) => api.post(`/processes/${id}/run`),
  progress: (id) => api.get(`/processes/${id}/progress`),
  delete: (id) => api.delete(`/processes/${id}`),
  reconcile: (id) => api.post(`/processes/${id}/reconcile`),
  unreconcile: (id) => api.post(`/processes/${id}/unreconcile`),
}

// ── Files ───────────────────────────────────────────────────────────────────
export const filesApi = {
  list: (processId) => api.get(`/files/${processId}`),
  upload: (processId, fileType, file) => {
    const form = new FormData()
    form.append('file_type', fileType)
    form.append('file', file)
    return api.post(`/files/upload/${processId}`, form)
  },
  delete: (fileId) => api.delete(`/files/${fileId}`),
}

// ── Results ─────────────────────────────────────────────────────────────────
export const resultsApi = {
  fees: (id) => api.get(`/results/${id}/fees`),
  kushki: (id) => api.get(`/results/${id}/kushki`),
  banregio: (id) => api.get(`/results/${id}/banregio`),
  conciliation: (id) => api.get(`/results/${id}/conciliation`),
  reconciliationView: (id, filter = 'all') => api.get(`/results/${id}/reconciliation-view?filter=${filter}`),
  acquirerBreakdown: (id) => api.get(`/results/${id}/acquirer-breakdown`),
  conciliationSummary: (id) => api.get(`/results/${id}/conciliation/summary`),
  exportFees: (id) => api.get(`/results/${id}/export/fees`, { responseType: 'blob' }),
  exportKushki: (id) => api.get(`/results/${id}/export/kushki`, { responseType: 'blob' }),
  exportBanregio: (id) => api.get(`/results/${id}/export/banregio`, { responseType: 'blob' }),
  exportReconciliation: (id) => api.get(`/results/${id}/export/reconciliation`, { responseType: 'blob' }),
  audit: (id) => api.get(`/results/${id}/audit`),
}

// ── Classifications ────────────────────────────────────────────────────────
export const classificationsApi = {
  classify: (processId, movementIndex, data) =>
    api.put(`/classifications/${processId}/${movementIndex}`, data),
  autoClassify: (processId) => api.post(`/classifications/${processId}/auto`),
  coverage: (processId) => api.get(`/classifications/${processId}/coverage`),
}

// ── SFTP ───────────────────────────────────────────────────────────
export const sftpApi = {
  status: () => api.get('/sftp/status'),
  test: (acquirer) => api.post(`/sftp/${acquirer}/test`),
  logs: (limit = 50) => api.get(`/sftp/logs?limit=${limit}`),
  downloads: (limit = 50) => api.get(`/sftp/downloads?limit=${limit}`),
}

// ── Adjustments ────────────────────────────────────────────────────────────
export const adjustmentsApi = {
  summary: (processId) => api.get(`/adjustments/${processId}/summary`),
  list: (processId, status) => api.get(`/adjustments/${processId}${status ? `?status=${status}` : ''}`),
  create: (processId, data) => api.post(`/adjustments/${processId}`, data),
  approve: (adjustmentId, reviewNotes) => api.put(`/adjustments/${adjustmentId}/approve`, { review_notes: reviewNotes }),
  reject: (adjustmentId, reviewNotes) => api.put(`/adjustments/${adjustmentId}/reject`, { review_notes: reviewNotes }),
  remove: (adjustmentId) => api.delete(`/adjustments/${adjustmentId}`),
}
