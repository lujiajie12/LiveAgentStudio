<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-for="(segment, index) in segments" :key="`${name}-${index}`">
      <path v-if="segment.type === 'path'" :d="segment.value" />
      <circle v-else-if="segment.type === 'circle'" :cx="segment.cx" :cy="segment.cy" :r="segment.r" />
      <ellipse
        v-else-if="segment.type === 'ellipse'"
        :cx="segment.cx"
        :cy="segment.cy"
        :rx="segment.rx"
        :ry="segment.ry"
      />
      <rect
        v-else-if="segment.type === 'rect'"
        :x="segment.x"
        :y="segment.y"
        :width="segment.width"
        :height="segment.height"
        :rx="segment.rx"
      />
      <polygon v-else-if="segment.type === 'polygon'" :points="segment.points" />
    </template>
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: {
    type: String,
    required: true
  },
  size: {
    type: Number,
    default: 18
  }
})

const icons = {
  home: [
    { type: 'path', value: 'M3 10.5 12 3l9 7.5' },
    { type: 'path', value: 'M5 9.5V21h14V9.5' },
    { type: 'path', value: 'M9.5 21v-6h5v6' }
  ],
  'book-open': [
    { type: 'path', value: 'M2.5 6.5A2.5 2.5 0 0 1 5 4h6.5v16H5a2.5 2.5 0 0 0-2.5 2z' },
    { type: 'path', value: 'M21.5 6.5A2.5 2.5 0 0 0 19 4h-6.5v16H19a2.5 2.5 0 0 1 2.5 2z' }
  ],
  'list-todo': [
    { type: 'path', value: 'M10 6h10' },
    { type: 'path', value: 'M10 12h10' },
    { type: 'path', value: 'M10 18h10' },
    { type: 'path', value: 'm3.5 6 1.5 1.5L7.5 5' },
    { type: 'path', value: 'm3.5 12 1.5 1.5L7.5 11' }
  ],
  workflow: [
    { type: 'rect', x: 3, y: 4, width: 6, height: 5, rx: 1.5 },
    { type: 'rect', x: 15, y: 4, width: 6, height: 5, rx: 1.5 },
    { type: 'rect', x: 9, y: 15, width: 6, height: 5, rx: 1.5 },
    { type: 'path', value: 'M9 6.5h6' },
    { type: 'path', value: 'M12 9v6' }
  ],
  'monitor-play': [
    { type: 'rect', x: 3, y: 4, width: 18, height: 12, rx: 2 },
    { type: 'path', value: 'M8 20h8' },
    { type: 'path', value: 'M12 16v4' },
    { type: 'polygon', points: '10,8 16,11 10,14' }
  ],
  settings: [
    { type: 'circle', cx: 12, cy: 12, r: 3.2 },
    { type: 'path', value: 'M12 2.8v2.4' },
    { type: 'path', value: 'M12 18.8v2.4' },
    { type: 'path', value: 'm4.9 4.9 1.7 1.7' },
    { type: 'path', value: 'm17.4 17.4 1.7 1.7' },
    { type: 'path', value: 'M2.8 12h2.4' },
    { type: 'path', value: 'M18.8 12h2.4' },
    { type: 'path', value: 'm4.9 19.1 1.7-1.7' },
    { type: 'path', value: 'm17.4 6.6 1.7-1.7' }
  ],
  logout: [
    { type: 'path', value: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4' },
    { type: 'path', value: 'M16 17l5-5-5-5' },
    { type: 'path', value: 'M21 12H9' }
  ],
  send: [
    { type: 'path', value: 'm22 2-7 20-4-9-9-4Z' },
    { type: 'path', value: 'M22 2 11 13' }
  ],
  'arrow-right': [
    { type: 'path', value: 'M5 12h14' },
    { type: 'path', value: 'm13 5 7 7-7 7' }
  ],
  bot: [
    { type: 'rect', x: 5, y: 7, width: 14, height: 11, rx: 3 },
    { type: 'path', value: 'M12 3v4' },
    { type: 'circle', cx: 9.2, cy: 12.5, r: 1 },
    { type: 'circle', cx: 14.8, cy: 12.5, r: 1 },
    { type: 'path', value: 'M9 16h6' }
  ],
  user: [
    { type: 'circle', cx: 12, cy: 8, r: 3.5 },
    { type: 'path', value: 'M5 20a7 7 0 0 1 14 0' }
  ],
  users: [
    { type: 'circle', cx: 9, cy: 9, r: 3 },
    { type: 'circle', cx: 16.5, cy: 10.5, r: 2.5 },
    { type: 'path', value: 'M4.5 19a5.5 5.5 0 0 1 9 0' },
    { type: 'path', value: 'M14.5 19a4.5 4.5 0 0 1 6 0' }
  ],
  sparkles: [
    { type: 'path', value: 'M12 3 13.6 7.4 18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6Z' },
    { type: 'path', value: 'm5 16 .8 2.2L8 19l-2.2.8L5 22l-.8-2.2L2 19l2.2-.8Z' },
    { type: 'path', value: 'm19 2 .6 1.6L21.2 4l-1.6.6L19 6.2l-.6-1.6L16.8 4l1.6-.4Z' }
  ],
  activity: [
    { type: 'path', value: 'M3 12h4l2.5-5 4 10 2.5-5H21' }
  ],
  tag: [
    { type: 'path', value: 'M20 13 11 22l-9-9V4h9z' },
    { type: 'circle', cx: 7, cy: 7, r: 1.2 }
  ],
  box: [
    { type: 'path', value: 'M12 2 4 6.2v11.6L12 22l8-4.2V6.2Z' },
    { type: 'path', value: 'M12 22V12.1' },
    { type: 'path', value: 'M4 6.2 12 11l8-4.8' }
  ],
  info: [
    { type: 'circle', cx: 12, cy: 12, r: 9 },
    { type: 'path', value: 'M12 10v6' },
    { type: 'path', value: 'M12 7h.01' }
  ],
  mail: [
    { type: 'rect', x: 3, y: 5, width: 18, height: 14, rx: 2 },
    { type: 'path', value: 'm4 7 8 6 8-6' }
  ],
  lock: [
    { type: 'rect', x: 5, y: 10, width: 14, height: 11, rx: 2 },
    { type: 'path', value: 'M8 10V7a4 4 0 0 1 8 0v3' }
  ],
  database: [
    { type: 'ellipse', cx: 12, cy: 5, rx: 7, ry: 3 },
    { type: 'path', value: 'M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5' },
    { type: 'path', value: 'M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7' }
  ],
  'shield-check': [
    { type: 'path', value: 'M12 3 5 6.5V12c0 4.4 3 7.8 7 9 4-1.2 7-4.6 7-9V6.5Z' },
    { type: 'path', value: 'm9.5 12 1.8 1.8 3.7-3.8' }
  ],
  'shopping-cart': [
    { type: 'circle', cx: 9, cy: 20, r: 1.5 },
    { type: 'circle', cx: 18, cy: 20, r: 1.5 },
    { type: 'path', value: 'M3 4h2l2.4 10.5a1 1 0 0 0 1 .8h9.8a1 1 0 0 0 1-.8L21 8H7' }
  ],
  'trending-up': [
    { type: 'path', value: 'M3 17 10 10l4 4 7-7' },
    { type: 'path', value: 'M17 7h4v4' }
  ],
  'alert-circle': [
    { type: 'circle', cx: 12, cy: 12, r: 9 },
    { type: 'path', value: 'M12 8v5' },
    { type: 'path', value: 'M12 16h.01' }
  ],
  'message-square': [
    { type: 'path', value: 'M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7A2.5 2.5 0 0 1 17.5 16H9l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z' }
  ],
  'shield-alert': [
    { type: 'path', value: 'M12 3 5 6.5V12c0 4.4 3 7.8 7 9 4-1.2 7-4.6 7-9V6.5Z' },
    { type: 'path', value: 'M12 8v4.5' },
    { type: 'path', value: 'M12 16h.01' }
  ],
  zap: [
    { type: 'path', value: 'M13 2 4 14h6l-1 8 9-12h-6z' }
  ],
  mic: [
    { type: 'rect', x: 9, y: 3, width: 6, height: 11, rx: 3 },
    { type: 'path', value: 'M6 11a6 6 0 0 0 12 0' },
    { type: 'path', value: 'M12 17v4' },
    { type: 'path', value: 'M8.5 21h7' }
  ],
  'monitor-up': [
    { type: 'rect', x: 3, y: 4, width: 18, height: 12, rx: 2 },
    { type: 'path', value: 'M8 20h8' },
    { type: 'path', value: 'M12 16v4' },
    { type: 'path', value: 'm9 12 2.5-2.5 2 2 3.5-3.5' }
  ],
  'chevron-right': [
    { type: 'path', value: 'm9 6 6 6-6 6' }
  ],
  history: [
    { type: 'path', value: 'M3 12a9 9 0 1 0 3-6.7' },
    { type: 'path', value: 'M3 4v4h4' },
    { type: 'path', value: 'M12 7.5v5l3 1.8' }
  ],
  clock: [
    { type: 'circle', cx: 12, cy: 12, r: 8.5 },
    { type: 'path', value: 'M12 7.5v4.8l3 1.8' }
  ],
  copy: [
    { type: 'rect', x: 9, y: 9, width: 10, height: 11, rx: 2 },
    { type: 'path', value: 'M7 15H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1' }
  ],
  'trash-2': [
    { type: 'path', value: 'M4 7h16' },
    { type: 'path', value: 'M9 7V4h6v3' },
    { type: 'path', value: 'M7 7l1 12h8l1-12' },
    { type: 'path', value: 'M10 11v5' },
    { type: 'path', value: 'M14 11v5' }
  ],
  'more-vertical': [
    { type: 'circle', cx: 12, cy: 5, r: 1.2 },
    { type: 'circle', cx: 12, cy: 12, r: 1.2 },
    { type: 'circle', cx: 12, cy: 19, r: 1.2 }
  ],
  flame: [
    { type: 'path', value: 'M12.5 3c.8 3-1.2 4.7-2.7 6 1.7-.1 3.4.9 4 2.7.8 2.2-.5 4.9-3 6-2.8 1.2-6-.2-7-3-1.3-3.6 1.1-6.2 3.3-8.3.8-.8 1.7-1.7 2.2-2.9.4-.8.6-1.6.7-2.5 1.2.5 2 1.4 2.5 2.3Z' }
  ]
}

const segments = computed(() => icons[props.name] || icons.info)
</script>
