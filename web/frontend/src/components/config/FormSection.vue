<template>
  <div class="glass-card form-section">
    <div class="section-header" @click="open = !open">
      <span class="section-icon">{{ icon }}</span>
      <span class="section-title">{{ title }}</span>
      <span class="section-arrow" :class="{ open }">›</span>
    </div>
    <div class="section-body" v-show="open">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  title: string
  icon?: string
}>()

const open = ref(true)
</script>

<style scoped>
.form-section {
  padding: 0;
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  cursor: pointer;
  transition: background 0.2s;
}

.section-header:hover {
  background: rgba(74, 158, 255, 0.04);
}

.section-icon {
  font-size: 16px;
  width: 24px;
  text-align: center;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a4a7a;
}

.section-arrow {
  margin-left: auto;
  font-size: 16px;
  color: #7a9ab8;
  transition: transform 0.2s;
}

.section-arrow.open {
  transform: rotate(90deg);
}

.section-body {
  padding: 0 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
</style>
