import { http } from '@/api/http'

export async function login(payload) {
  const response = await http.post('/auth/login', payload)
  return response.data.data
}

export async function fetchCurrentUser() {
  const response = await http.get('/me')
  return response.data.data
}
