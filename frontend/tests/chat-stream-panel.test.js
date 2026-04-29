import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChatStreamPanel from '@/components/ChatStreamPanel.vue'

describe('ChatStreamPanel', () => {
  it('renders streaming token buffer', () => {
    const wrapper = mount(ChatStreamPanel, {
      props: {
        messages: [],
        streamBuffer: '正在流式输出',
        isStreaming: true,
        error: ''
      }
    })

    expect(wrapper.text()).toContain('正在流式输出')
    expect(wrapper.text()).toContain('Streaming')
  })
})
