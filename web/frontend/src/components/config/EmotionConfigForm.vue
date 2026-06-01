<template>
  <div class="emotion-config-form">
    <!-- 情绪等级 -->
    <FormSection title="情绪等级" icon="◈">
      <div class="form-row">
        <label class="form-label">情绪列表</label>
        <TagInput v-model="model.emotions.levels" placeholder="输入后按回车添加" />
      </div>
      <div class="form-row">
        <label class="form-label">默认情绪</label>
        <select v-model="model.emotions.default" class="form-input">
          <option v-for="level in model.emotions.levels" :key="level" :value="level">{{ level }}</option>
        </select>
      </div>
    </FormSection>

    <!-- 运行时 -->
    <FormSection title="运行时" icon="◉">
      <div class="form-row">
        <label class="form-label">更新间隔（秒）</label>
        <input v-model.number="model.runtime.update_interval_seconds" type="number" class="form-input" min="10" />
      </div>
      <div class="form-row">
        <label class="form-label">历史消息上限</label>
        <input v-model.number="model.runtime.history_message_limit" type="number" class="form-input" min="5" />
      </div>
    </FormSection>

    <!-- 提示词 -->
    <FormSection title="提示词" icon="◎">
      <div class="form-row">
        <label class="form-label">System Prompt</label>
        <textarea v-model="model.prompt.system" class="form-textarea" rows="6" placeholder="情绪分析提示词" />
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
import TagInput from './TagInput.vue'

const props = defineProps<{
  modelValue: any
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: any): void
}>()

const model = computed({
  get: () => {
    const cfg = props.modelValue
    if (!cfg.emotions) cfg.emotions = { levels: ['平静', '放松', '开心', '兴奋', '激动', '疲惫', '难过', '沮丧'], default: '平静' }
    if (!Array.isArray(cfg.emotions.levels)) cfg.emotions.levels = []
    if (!cfg.runtime) cfg.runtime = { update_interval_seconds: 60, history_message_limit: 20 }
    if (!cfg.prompt) cfg.prompt = { system: '', user_template: '' }
    return cfg
  },
  set: (v) => emit('update:modelValue', v),
})
</script>

<style scoped>
.emotion-config-form {
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
</style>
