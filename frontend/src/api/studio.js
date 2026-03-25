import { studioHttp } from '@/api/studioHttp'

export async function fetchStudioCurrentUser() {
  const response = await studioHttp.get('/me')
  return response.data.data
}

export async function fetchStudioMessages(sessionId) {
  const response = await studioHttp.get(`/sessions/${sessionId}/messages`)
  return response.data.data
}

export async function fetchStudioSystemHealth() {
  const response = await studioHttp.get('/system/health')
  return response.data.data
}

export async function fetchStudioSystemMetrics() {
  const response = await studioHttp.get('/system/metrics')
  return response.data.data
}

export async function fetchStudioTraces(limit = 20) {
  const response = await studioHttp.get('/ops/traces', { params: { limit } })
  return response.data.data
}

export async function fetchStudioPriorityQueue(sessionId, limit = 3) {
  const response = await studioHttp.get('/ops/priority-queue', {
    params: { session_id: sessionId, limit }
  })
  return response.data.data
}

export async function fetchStudioActionCenter(sessionId) {
  const response = await studioHttp.get('/ops/action-center', {
    params: { session_id: sessionId }
  })
  return response.data.data
}

export async function broadcastStudioTts(payload) {
  const response = await studioHttp.post('/ops/tts/broadcast', payload)
  return response.data.data
}
