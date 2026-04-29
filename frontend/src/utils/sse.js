export function parseSSEBuffer(buffer) {
  const segments = buffer.split('\n\n')
  const complete = segments.slice(0, -1)
  const rest = segments.at(-1) || ''

  const events = complete
    .map((segment) => {
      const lines = segment.split('\n')
      const event = lines.find((line) => line.startsWith('event:'))?.replace('event:', '').trim()
      const dataLine = lines.find((line) => line.startsWith('data:'))?.replace('data:', '').trim()
      if (!event || !dataLine) {
        return null
      }
      return {
        event,
        data: JSON.parse(dataLine)
      }
    })
    .filter(Boolean)

  return { events, rest }
}

export async function consumeSSEStream({ url, token, body, onEvent }) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify(body)
  })

  if (!response.ok || !response.body) {
    throw new Error(`SSE request failed with ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSSEBuffer(buffer)
    buffer = parsed.rest
    for (const event of parsed.events) {
      onEvent(event)
    }
  }
}
