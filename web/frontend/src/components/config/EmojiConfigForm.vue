<template>
  <div class="emoji-config-form">
    <!-- 存储 -->
    <FormSection title="存储" icon="◈">
      <div class="form-row">
        <label class="form-label">表情目录</label>
        <input v-model="model.storage.emoji_dir" class="form-input" placeholder="emoji" />
      </div>
      <div class="form-row">
        <label class="form-label">数据库路径</label>
        <input v-model="model.storage.db_path" class="form-input" placeholder="data/emoji.db" />
      </div>
    </FormSection>

    <!-- 模型 -->
    <FormSection title="模型" icon="◉">
      <div class="form-row">
        <label class="form-label">视觉模型</label>
        <input v-model="model.models.vision_model" class="form-input" placeholder="vision_emoji_desc" />
      </div>
      <div class="form-row">
        <label class="form-label">嵌入模型</label>
        <input v-model="model.models.embedding_model" class="form-input" placeholder="embedding_bge_m3" />
      </div>
    </FormSection>

    <!-- 检索 -->
    <FormSection title="检索" icon="◎">
      <div class="form-row">
        <label class="form-label">相似度阈值</label>
        <input v-model.number="model.retrieval.similarity_threshold" type="number" class="form-input" min="0" max="1" step="0.01" />
        <span class="form-hint">低于此值不发送</span>
      </div>
      <div class="form-row">
        <label class="form-label">最大候选数</label>
        <input v-model.number="model.retrieval.max_candidates" type="number" class="form-input" min="10" />
      </div>
      <div class="form-row">
        <label class="form-label">每条最多发送</label>
        <input v-model.number="model.retrieval.max_send_per_reply" type="number" class="form-input" min="1" max="5" />
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
    if (!cfg.storage) cfg.storage = { emoji_dir: 'emoji', db_path: 'data/emoji.db' }
    if (!cfg.models) cfg.models = { vision_model: 'vision_emoji_desc', embedding_model: 'embedding_bge_m3' }
    if (!cfg.retrieval) cfg.retrieval = { similarity_threshold: 0.51, max_candidates: 100, max_send_per_reply: 1 }
    return cfg
  },
  set: (v) => emit('update:modelValue', v),
})
</script>

<style scoped>
.emoji-config-form {
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

.form-hint {
  font-size: 11px;
  color: #a0b8cc;
  flex: 1;
}
</style>
