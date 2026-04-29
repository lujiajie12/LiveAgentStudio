import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'

import { buildRouter } from '@/router'
import { clearToken, writeToken } from '@/utils/auth'

describe('router guard', () => {
  beforeEach(() => {
    clearToken()
  })

  it('redirects anonymous users to login', async () => {
    const router = buildRouter(createMemoryHistory())
    await router.push('/workbench')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('allows authenticated users through', async () => {
    writeToken('demo-token')
    const router = buildRouter(createMemoryHistory())
    await router.push('/workbench')
    expect(router.currentRoute.value.name).toBe('workbench')
  })
})
