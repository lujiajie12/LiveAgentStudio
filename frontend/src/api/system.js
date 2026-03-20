import { http } from '@/api/http'

export async function fetchSystemHealth() {
  const response = await http.get('/system/health')
  return response.data
}
