import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useWorkspaceStore } from '@/stores/workspace'

describe('workspace store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps the local QA card while QA streaming is in progress', () => {
    const store = useWorkspaceStore()

    store.isStreaming = true
    store.streamingKey = 'qa'
    store.actionCenter.qa = {
      key: 'qa',
      title: 'RAG 知识 Agent',
      subtitle: '实时解答',
      tone: 'indigo',
      status: 'streaming',
      editable: true,
      content: '本地流式输出',
      detail: '处理中',
      references: [],
      metadata: {}
    }

    store.applyActionCenterPayload({
      cards: [
        {
          key: 'qa',
          title: 'RAG 知识 Agent',
          subtitle: '实时解答',
          tone: 'indigo',
          status: 'ready',
          editable: true,
          content: '接口返回的旧内容',
          detail: '引用 0 条知识片段',
          references: [],
          metadata: {
            message_created_at: '2026-04-02T08:00:00.000Z'
          }
        }
      ]
    })

    expect(store.actionCenter.qa.content).toBe('本地流式输出')
    expect(store.actionCenter.qa.status).toBe('streaming')
  })

  it('keeps the newer QA card when a stale action-center payload arrives', () => {
    const store = useWorkspaceStore()

    store.actionCenter.qa = {
      key: 'qa',
      title: 'RAG 知识 Agent',
      subtitle: '实时解答',
      tone: 'indigo',
      status: 'ready',
      editable: true,
      content: '较新的本地答案',
      detail: '引用 1 条知识片段',
      references: [],
      metadata: {
        message_created_at: '2026-04-02T10:00:00.000Z'
      }
    }

    store.applyActionCenterPayload({
      cards: [
        {
          key: 'qa',
          title: 'RAG 知识 Agent',
          subtitle: '实时解答',
          tone: 'indigo',
          status: 'ready',
          editable: true,
          content: '较旧的接口答案',
          detail: '引用 1 条知识片段',
          references: [],
          metadata: {
            message_created_at: '2026-04-02T09:00:00.000Z'
          }
        }
      ]
    })

    expect(store.actionCenter.qa.content).toBe('较新的本地答案')
  })
})
