import axios from 'axios'

import { clearStudioToken, clearStudioUser, readStudioToken } from '@/utils/studioAuth'

export const studioHttp = axios.create({
  baseURL: '/api/v1',
  timeout: 10000
})

studioHttp.interceptors.request.use((config) => {
  const token = readStudioToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

studioHttp.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearStudioToken()
      clearStudioUser()
    }
    return Promise.reject(error)
  }
)
