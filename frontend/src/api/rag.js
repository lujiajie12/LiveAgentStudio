import { http } from '@/api/http'

export async function fetchRagOfflineOverview() {
  const response = await http.get('/rag/offline/overview')
  return response.data.data
}

export async function createRagOfflineJob(payload) {
  const response = await http.post('/rag/offline/jobs', payload)
  return response.data.data
}

export async function fetchRagOfflineJob(jobId) {
  const response = await http.get(`/rag/offline/jobs/${jobId}`)
  return response.data.data
}

export async function debugRagOnline(payload) {
  const response = await http.post('/rag/online/debug', payload, {
    timeout: 60000
  })
  return response.data.data
}
