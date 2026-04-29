import { http } from '@/api/http'

export async function createDocument(payload) {
  const response = await http.post('/documents', payload)
  return response.data.data
}
