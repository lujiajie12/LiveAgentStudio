import { http } from '@/api/http'

export async function fetchSystemHealth() {
  const response = await http.get('/system/health')
  return response.data.data
}

export async function fetchSystemMetrics() {
  const response = await http.get('/system/metrics')
  return response.data.data
}
