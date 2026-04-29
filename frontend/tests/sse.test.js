import { describe, expect, it } from 'vitest'

import { parseSSEBuffer } from '@/utils/sse'

describe('parseSSEBuffer', () => {
  it('parses complete events and keeps trailing buffer', () => {
    const raw =
      'event: token\ndata: {"content":"hello"}\n\n' +
      'event: final\ndata: {"content":"done"}\n\n' +
      'event: token\ndata: {"content":"partial"}'

    const parsed = parseSSEBuffer(raw)

    expect(parsed.events).toHaveLength(2)
    expect(parsed.events[0]).toEqual({
      event: 'token',
      data: { content: 'hello' }
    })
    expect(parsed.rest).toContain('partial')
  })
})
