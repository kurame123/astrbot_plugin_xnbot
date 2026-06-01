<template>
  <div class="rey-config-form">
    <!-- roleplay_main -->
    <FormSection title="角色扮演提示词" icon="◈">
      <div class="form-row">
        <label class="form-label">System Prompt</label>
        <textarea v-model="model.roleplay_main.system_prompt" class="form-textarea" rows="8" placeholder="系统提示词" />
      </div>
      <div class="form-row">
        <label class="form-label">User Prompt 模板</label>
        <textarea v-model="model.roleplay_main.user_prompt_template" class="form-textarea" rows="6" placeholder="用户消息模板" />
      </div>
    </FormSection>

    <!-- vision_emoji_desc -->
    <FormSection title="表情描述提示词" icon="◉">
      <div class="form-row">
        <label class="form-label">System Prompt</label>
        <textarea v-model="model.vision_emoji_desc.system_prompt" class="form-textarea" rows="4" placeholder="表情描述提示词" />
      </div>
      <div class="form-row">
        <label class="form-label">User Prompt</label>
        <input v-model="model.vision_emoji_desc.user_prompt" class="form-input" placeholder="用户消息" />
      </div>
    </FormSection>

    <!-- vision_image_desc -->
    <FormSection title="图片描述提示词" icon="◎">
      <div class="form-row">
        <label class="form-label">System Prompt</label>
        <textarea v-model="model.vision_image_desc.system_prompt" class="form-textarea" rows="4" placeholder="图片描述提示词" />
      </div>
      <div class="form-row">
        <label class="form-label">User Prompt</label>
        <input v-model="model.vision_image_desc.user_prompt" class="form-input" placeholder="用户消息" />
      </div>
    </FormSection>

    <!-- debug -->
    <FormSection title="调试" icon="◇">
      <div class="form-row">
        <label class="form-label">场景模型调试</label>
        <label class="form-switch">
          <input type="checkbox" v-model="model.debug.enable_context_debug" />
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-row">
        <label class="form-label">回复模型调试</label>
        <label class="form-switch">
          <input type="checkbox" v-model="model.debug.enable_reply_debug" />
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-row">
        <label class="form-label">日志最大字符</label>
        <input v-model.number="model.debug.max_log_chars" type="number" class="form-input" min="100" />
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
    if (!cfg.roleplay_main) cfg.roleplay_main = { system_prompt: '', user_prompt_template: '' }
    if (!cfg.vision_emoji_desc) cfg.vision_emoji_desc = { system_prompt: '', user_prompt: '' }
    if (!cfg.vision_image_desc) cfg.vision_image_desc = { system_prompt: '', user_prompt: '' }
    if (!cfg.debug) cfg.debug = { enable_context_debug: true, enable_reply_debug: true, max_log_chars: 800 }
    return cfg
  },
  set: (v) => emit('update:modelValue', v),
})
</script>

<style scoped>
.rey-config-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.form-label {
  flex: 0 0 140px;
  font-size: 13px;
  color: #5a7a9a;
  padding-top: 8px;
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

.form-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  cursor: pointer;
}

.form-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.switch-slider {
  position: absolute;
  inset: 0;
  background: #ccc;
  border-radius: 24px;
  transition: 0.3s;
}

.switch-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: 0.3s;
}

.form-switch input:checked + .switch-slider {
  background: #4a9eff;
}

.form-switch input:checked + .switch-slider::before {
  transform: translateX(20px);
}
</style>
