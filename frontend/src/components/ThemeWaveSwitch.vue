<template>
  <button
    ref="buttonRef"
    type="button"
    class="theme-wave-switch"
    :class="[`theme-wave-switch--${theme}`, `theme-wave-switch--${variant}`]"
    :aria-label="nextLabel"
    :title="nextLabel"
    :disabled="transitioning"
    @click="toggleTheme"
  >
    <span class="theme-wave-switch__halo" aria-hidden="true"></span>
    <span class="theme-wave-switch__icon">
      <AppIcon :name="theme === 'light' ? 'sun' : 'moon'" :size="20" />
    </span>
  </button>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import AppIcon from '@/components/AppIcon.vue'
import { applyTheme, getCurrentTheme, getOppositeTheme } from '@/utils/theme'

const WAVE_DURATION_MS = 760
const THEME_SWAP_DELAY_MS = 120
const FADE_DURATION_MS = 220

defineProps({
  variant: {
    type: String,
    default: 'inline'
  }
})

const buttonRef = ref(null)
const theme = ref('dark')
const transitioning = ref(false)

const nextLabel = computed(() => (theme.value === 'light' ? '切换为深色模式' : '切换为浅色模式'))

onMounted(() => {
  theme.value = getCurrentTheme()
  window.addEventListener('storage', syncThemeFromStorage)
})

onBeforeUnmount(() => {
  window.removeEventListener('storage', syncThemeFromStorage)
})

function syncThemeFromStorage(event) {
  if (event.key === 'liveagent.theme') {
    theme.value = getCurrentTheme()
  }
}

async function toggleTheme(event) {
  if (transitioning.value) {
    return
  }
  const nextTheme = getOppositeTheme(theme.value)
  const origin = resolveWaveOrigin(event)

  transitioning.value = true
  const overlay = createWaveOverlay(nextTheme, origin)
  document.body.appendChild(overlay)

  await wait(THEME_SWAP_DELAY_MS)
  theme.value = applyTheme(nextTheme)
  await wait(WAVE_DURATION_MS - THEME_SWAP_DELAY_MS)
  overlay.classList.add('theme-wave-overlay--fade')
  await wait(FADE_DURATION_MS)
  overlay.remove()
  transitioning.value = false
}

function resolveWaveOrigin(event) {
  const target = buttonRef.value
  const rect = target?.getBoundingClientRect()
  if (rect) {
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2
    }
  }
  return {
    x: event?.clientX || 36,
    y: event?.clientY || window.innerHeight - 36
  }
}

function createWaveOverlay(targetTheme, origin) {
  const radius = Math.ceil(
    Math.hypot(
      Math.max(origin.x, window.innerWidth - origin.x),
      Math.max(origin.y, window.innerHeight - origin.y)
    )
  )
  const overlay = document.createElement('div')
  overlay.className = `theme-wave-overlay theme-wave-overlay--${targetTheme}`
  overlay.style.setProperty('--theme-wave-x', `${origin.x}px`)
  overlay.style.setProperty('--theme-wave-y', `${origin.y}px`)
  overlay.style.setProperty('--theme-wave-radius', `${radius}px`)
  for (let index = 0; index < 4; index += 1) {
    const ring = document.createElement('span')
    ring.className = 'theme-wave-overlay__ring'
    ring.style.setProperty('--theme-ring-delay', `${index * 96}ms`)
    ring.style.setProperty('--theme-ring-opacity', `${0.3 - index * 0.045}`)
    overlay.appendChild(ring)
  }
  overlay.setAttribute('aria-hidden', 'true')
  return overlay
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}
</script>
