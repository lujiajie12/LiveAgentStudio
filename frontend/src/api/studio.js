import { studioHttp } from '@/api/studioHttp'

export async function fetchStudioCurrentUser() {
  const response = await studioHttp.get('/me')
  return response.data.data
}

function resolveWsBase() {
  if (typeof window === 'undefined') {
    return 'ws://localhost:8000/api/v1'
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v1`
}

export async function fetchStudioMessages(sessionId) {
  const response = await studioHttp.get(`/sessions/${sessionId}/messages`)
  return response.data.data
}

export async function fetchStudioLiveOverview(sessionId) {
  const response = await studioHttp.get('/live/overview', {
    params: { session_id: sessionId }
  })
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

export async function pushStudioTeleprompter(payload) {
  const response = await studioHttp.post('/teleprompter/push', payload)
  return response.data.data
}

export async function fetchStudioTeleprompterCurrent(sessionId) {
  const response = await studioHttp.get('/teleprompter/current', {
    params: { session_id: sessionId }
  })
  return response.data.data
}

export function buildStudioBarrageWsUrl(sessionId, token) {
  const params = new URLSearchParams({
    session_id: sessionId,
    token
  })
  return `${resolveWsBase()}/live/barrages/stream?${params.toString()}`
}

export function buildStudioTeleprompterWsUrl(sessionId, token) {
  const params = new URLSearchParams({
    session_id: sessionId,
    token
  })
  return `${resolveWsBase()}/teleprompter/stream?${params.toString()}`
}
