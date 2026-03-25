import { http } from '@/api/http'

export async function listTraces(limit = 20) {
  const response = await http.get('/ops/traces', { params: { limit } })
  return response.data.data
}

export async function fetchTrace(traceId) {
  const response = await http.get(`/ops/traces/${traceId}`)
  return response.data.data
}
