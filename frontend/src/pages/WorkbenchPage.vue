<template>
  <div class="workspace-grid">
    <SessionListPanel
      :sessions="workspace.sessions"
      :active-session-id="workspace.activeSessionId"
      @select="workspace.loadMessages"
    />
    <ChatStreamPanel
      :messages="workspace.activeMessages"
      :stream-buffer="workspace.streamBuffer"
      :is-streaming="workspace.isStreaming"
      :error="workspace.error"
      @send="workspace.sendMessage"
    />
    <SideContextPanel :live-context="workspace.liveContext" />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'

import ChatStreamPanel from '@/components/ChatStreamPanel.vue'
import SessionListPanel from '@/components/SessionListPanel.vue'
import SideContextPanel from '@/components/SideContextPanel.vue'
import { useWorkspaceStore } from '@/stores/workspace'

const workspace = useWorkspaceStore()

onMounted(async () => {
  workspace.bootstrap()
  if (workspace.activeSessionId) {
    await workspace.loadMessages(workspace.activeSessionId)
  }
})
</script>
