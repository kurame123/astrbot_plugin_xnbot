<template>
  <div class="tag-input-wrap">
    <div class="tag-list">
      <span v-for="(tag, i) in modelValue" :key="i" class="tag">
        {{ tag }}
        <button class="tag-remove" @click="remove(i)">×</button>
      </span>
    </div>
    <input
      v-model="input"
      class="tag-input"
      :placeholder="placeholder"
      @keydown.enter.prevent="add"
      @keydown.backspace="onBackspace"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  modelValue: string[]
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string[]): void
}>()

const input = ref('')

function add() {
  const val = input.value.trim()
  if (val && !props.modelValue.includes(val)) {
    emit('update:modelValue', [...props.modelValue, val])
  }
  input.value = ''
}

function remove(index: number) {
  const newVal = [...props.modelValue]
  newVal.splice(index, 1)
  emit('update:modelValue', newVal)
}

function onBackspace() {
  if (!input.value && props.modelValue.length) {
    remove(props.modelValue.length - 1)
  }
}
</script>

<style scoped>
.tag-input-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(74, 158, 255, 0.15);
  border-radius: 8px;
  min-height: 38px;
  align-items: center;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  background: rgba(74, 158, 255, 0.1);
  border-radius: 12px;
  font-size: 12px;
  color: #2d7dd2;
}

.tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: #7a9ab8;
  font-size: 14px;
  padding: 0;
  line-height: 1;
}

.tag-remove:hover {
  color: #ff6464;
}

.tag-input {
  flex: 1;
  min-width: 80px;
  border: none;
  background: transparent;
  outline: none;
  font-size: 13px;
  color: #2a4a6a;
  font-family: inherit;
}
</style>
