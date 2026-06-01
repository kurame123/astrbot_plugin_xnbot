<template>
  <div class="reply-config-form">
    <!-- 切分参数 -->
    <FormSection title="切分参数" icon="◈">
      <div class="form-row">
        <label class="form-label">最大句数</label>
        <input v-model.number="model.segment.max_segments" type="number" class="form-input" min="1" max="10" />
      </div>
      <div class="form-row">
        <label class="form-label">每条最少字数</label>
        <input v-model.number="model.segment.min_chars" type="number" class="form-input" min="1" />
      </div>
      <div class="form-row">
        <label class="form-label">每条建议字数</label>
        <input v-model.number="model.segment.max_chars" type="number" class="form-input" min="10" />
      </div>
      <div class="form-row">
        <label class="form-label">跳过阈值</label>
        <input v-model.number="model.segment.skip_threshold" type="number" class="form-input" min="1" />
        <span class="form-hint">低于此长度不拆分</span>
      </div>
    </FormSection>

    <!-- 发送间隔 -->
    <FormSection title="发送间隔" icon="◉">
      <div class="form-row">
        <label class="form-label">最短间隔（秒）</label>
        <input v-model.number="model.send.min_interval" type="number" class="form-input" min="0.1" step="0.1" />
      </div>
      <div class="form-row">
        <label class="form-label">最长间隔（秒）</label>
        <input v-model.number="model.send.max_interval" type="number" class="form-input" min="0.1" step="0.1" />
      </div>
    </FormSection>

    <!-- 提示词 -->
    <FormSection title="提示词" icon="◎">
      <div class="form-row">
        <label class="form-label">System Prompt</label>
        <textarea v-model="model.prompt.system" class="form-textarea" rows="8" placeholder="切分提示词" />
      </div>
      <div class="form-row">
        <label class="form-label">User 模板</label>
        <textarea v-model="model.prompt.user_template" class="form-textarea" rows="4" placeholder="用户消息模板" />
      </div>
    </FormSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import FormSection from './FormSection.vue'

const props = defineProps<{
  modelValue: any
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: any): void
}>()

const model = computed({
  get: () => {
    const cfg = props.modelValue
    if (!cfg.segment) cfg.segment = { max_segments: 5, min_chars: 4, max_chars: 40, skip_threshold: 20 }
    if (!cfg.send) cfg.send = { min_interval: 0.4, max_interval: 0.9 }
    if (!cfg.prompt) cfg.prompt = { system: '', user_template: '' }
    return cfg
  },
  set: (v) => emit('update:modelValue', v),
})
</script>

<style scoped>
.reply-config-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.form-label {
  flex: 0 0 140px;
  font-size: 13px;
  color: #5a7a9a;
}

.form-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid rgba(74, 158, 255, 0.15);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.6);
  font-size: 13px;
  color: #2a4a6a;
  outline: none;
  font-family: inherit;
}

.form-input:focus {
  border-color: rgba(74, 158, 255, 0.4);
}

.form-textarea {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid rgba(74, 158, 255, 0.15);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.6);
  font-size: 13px;
  color: #2a4a6a;
  outline: none;
  resize: vertical;
  line-height: 1.6;
  font-family: 'Consolas', monospace;
}

.form-textarea:focus {
  border-color: rgba(74, 158, 255, 0.4);
}

.form-hint {
  font-size: 11px;
  color: #a0b8cc;
  flex: 1;
}
</style>
