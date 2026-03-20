const TOKEN_KEY = 'liveagent.token'
const USER_KEY = 'liveagent.user'

export function readToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function writeToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export function readUser() {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function writeUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearUser() {
  localStorage.removeItem(USER_KEY)
}

export function hasAuthToken() {
  return Boolean(readToken())
}
