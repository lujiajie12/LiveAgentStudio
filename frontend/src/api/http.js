import axios from 'axios'

import { clearToken, clearUser, readToken } from '@/utils/auth'

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 10000
})

http.interceptors.request.use((config) => {
  const token = readToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken()
      clearUser()
    }
    return Promise.reject(error)
  }
)
