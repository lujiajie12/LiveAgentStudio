import { http } from '@/api/http'

export async function fetchQaMemoryInsights(params = {}) {
  const response = await http.get('/memory/qa/insights', { params })
  return response.data.data
}
