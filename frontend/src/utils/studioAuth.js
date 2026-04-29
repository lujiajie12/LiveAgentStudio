const STUDIO_TOKEN_KEY = 'liveagent.studio.token'
const STUDIO_USER_KEY = 'liveagent.studio.user'

export function readStudioToken() {
  return localStorage.getItem(STUDIO_TOKEN_KEY) || ''
}

export function writeStudioToken(token) {
  localStorage.setItem(STUDIO_TOKEN_KEY, token)
}

export function clearStudioToken() {
  localStorage.removeItem(STUDIO_TOKEN_KEY)
}

export function readStudioUser() {
  const raw = localStorage.getItem(STUDIO_USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function writeStudioUser(user) {
  localStorage.setItem(STUDIO_USER_KEY, JSON.stringify(user))
}

export function clearStudioUser() {
  localStorage.removeItem(STUDIO_USER_KEY)
}

export function hasStudioAuthToken() {
  return Boolean(readStudioToken())
}
