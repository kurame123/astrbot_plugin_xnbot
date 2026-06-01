<template>
  <div class="ai-config-form">
    <!-- 服务商 -->
    <FormSection title="服务商" icon="◈">
      <!-- 服务商切换 tabs -->
      <div class="server-tabs">
        <button
          v-for="(_, name) in model.servers"
          :key="name"
          class="server-tab"
          :class="{ active: activeServer === name }"
          @click="activeServer = name as string"
        >
          {{ name }}
        </button>
        <button class="server-tab server-tab-add" @click="showAddServer = true">+</button>
      </div>

      <!-- 添加服务商弹窗 -->
      <div v-if="showAddServer" class="add-server-form">
        <input v-model="newServerName" class="form-input" placeholder="服务商名称（如 openai）" />
        <div class="add-server-actions">
          <button class="btn-ghost" @click="showAddServer = false">取消</button>
          <button class="btn-primary" @click="addServer">确定</button>
        </div>
      </div>

      <!-- 当前服务商配置 -->
      <div v-if="activeServer && model.servers[activeServer]" class="server-form">
        <div class="form-row">
          <label class="form-label">Base URL</label>
          <input v-model="model.servers[activeServer].base_url" class="form-input" placeholder="https://api.example.com/v1" />
        </div>
        <div class="form-row">
          <label class="form-label">API Key</label>
          <input v-model="model.servers[activeServer].api_key" class="form-input" type="password" placeholder="sk-..." />
        </div>
        <div class="form-row" v-if="model.servers[activeServer].timeout !== undefined">
          <label class="form-label">超时（秒）</label>
          <input v-model.number="model.servers[activeServer].timeout" type="number" class="form-input" min="10" />
        </div>
        <button class="btn-remove" @click="removeServer(activeServer)">删除此服务商</button>
      </div>
    </FormSection>

    <!-- 模型列表 -->
    <FormSection title="模型列表" icon="◉">
      <div v-for="(m, i) in model.models" :key="i" class="model-card">
        <div class="model-header">
          <div class="model-info">
            <span class="model-name">{{ getModelLabel(m.name) }}</span>
            <span class="model-id">{{ m.name }}</span>
          </div>
          <button class="btn-remove-sm" @click="removeModel(i)">删除</button>
        </div>
        <div class="form-row">
          <label class="form-label">服务商</label>
          <select v-model="m.provider" class="form-input">
            <option v-for="(_, name) in model.servers" :key="name" :value="name">{{ name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label class="form-label">模型 ID</label>
          <input v-model="m.model" class="form-input" placeholder="deepseek-v4-flash" />
        </div>
        <div class="form-row">
          <label class="form-label">备用模型</label>
          <select v-model="m.fallback" class="form-input">
            <option value="">无</option>
            <option v-for="other in model.models" :key="other.name" :value="other.name" :disabled="other.name === m.name">
              {{ other.name }}
            </option>
          </select>
        </div>
        <div class="sub-section" v-if="m.parameters">
          <div class="sub-title">参数</div>
          <div class="form-row">
            <label class="form-label">temperature</label>
            <input v-model.number="m.parameters.temperature" type="number" class="form-input" min="0" max="2" step="0.1" />
            <span class="form-hint">越高越随机</span>
          </div>
          <div class="form-row">
            <label class="form-label">top_p</label>
            <input v-model.number="m.parameters.top_p" type="number" class="form-input" min="0" max="1" step="0.1" />
            <span class="form-hint">核采样</span>
          </div>
          <div class="form-row">
            <label class="form-label">max_tokens</label>
            <input v-model.number="m.parameters.max_tokens" type="number" class="form-input" min="1" />
            <span class="form-hint">最大输出长度</span>
          </div>
        </div>
      </div>
      <button class="btn-add" @click="addModel">+ 添加模型</button>
    </FormSection>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import FormSection from './FormSection.vue'

const props = defineProps<{
  modelValue: any
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: any): void
}>()

const showAddServer = ref(false)
const newServerName = ref('')
const activeServer = ref('')

// 模型中文描述映射
const modelLabels: Record<string, string> = {
  roleplay_main: '回复生成（主模型）',
  roleplay_fallback: '回复生成（备用）',
  tools: '工具调用',
  embedding_bge_m3: '嵌入向量（bge-m3）',
  vision_emoji_desc: '表情描述',
  vision_image_desc: '图片描述',
  emotion_analyzer: '情绪分析',
  reply_segmenter: '回复切分',
  keyword_extractor: '关键词提取',
  ie_extractor: 'Agent 记忆检索',
  ie_extractor_fallback: 'Agent 记忆检索（备用）',
}

function getModelLabel(name: string): string {
  return modelLabels[name] || name
}

const model = computed({
  get: () => {
    const cfg = props.modelValue
    if (!cfg.servers) cfg.servers = {}
    if (!cfg.models) cfg.models = []
    // 初始化 activeServer
    if (!activeServer.value) {
      activeServer.value = Object.keys(cfg.servers)[0] || ''
    }
    return cfg
  },
  set: (v) => emit('update:modelValue', v),
})

function addServer() {
  const name = newServerName.value.trim()
  if (!name || model.value.servers[name]) return
  model.value.servers[name] = { base_url: '', api_key: '' }
  activeServer.value = name
  newServerName.value = ''
  showAddServer.value = false
}

function removeServer(name: string) {
  delete model.value.servers[name]
  const keys = Object.keys(model.value.servers)
  activeServer.value = keys[0] || ''
}

function addModel() {
  model.value.models.push({
    name: '',
    provider: activeServer.value || Object.keys(model.value.servers)[0] || '',
    model: '',
    fallback: '',
    parameters: { temperature: 0.5, top_p: 0.9, max_tokens: 2048 },
  })
}

function removeModel(index: string | number) {
  model.value.models.splice(Number(index), 1)
}
</script>

<style scoped>
.ai-config-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 服务商 tabs */
.server-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.server-tab {
  padding: 6px 16px;
  border-radius: 6px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: rgba(255, 255, 255, 0.5);
  color: #5a7a9a;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.server-tab:hover {
  background: rgba(74, 158, 255, 0.1);
  color: #2d7dd2;
}

.server-tab.active {
  background: rgba(74, 158, 255, 0.15);
  color: #1a6bc4;
  font-weight: 600;
  border-color: rgba(74, 158, 255, 0.4);
}

.server-tab-add {
  border-style: dashed;
  color: #4a9eff;
}

/* 添加服务商表单 */
.add-server-form {
  background: rgba(74, 158, 255, 0.05);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.add-server-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* 服务商表单 */
.server-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 模型卡片 */
.model-card {
  background: rgba(74, 158, 255, 0.03);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.model-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.model-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.model-name {
  font-size: 14px;
  font-weight: 600;
  color: #1a4a7a;
}

.model-id {
  font-size: 11px;
  color: #a0b8cc;
  font-family: 'Consolas', monospace;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-label {
  flex: 0 0 110px;
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
  flex: 0 0 auto;
}

.sub-section {
  background: rgba(255, 255, 255, 0.4);
  border-radius: 6px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sub-title {
  font-size: 12px;
  font-weight: 600;
  color: #7a9ab8;
}

.btn-remove {
  padding: 6px 12px;
  border-radius: 4px;
  border: 1px solid rgba(255, 100, 100, 0.3);
  background: transparent;
  color: #ff6464;
  font-size: 12px;
  cursor: pointer;
  align-self: flex-start;
}

.btn-remove:hover {
  background: rgba(255, 100, 100, 0.1);
}

.btn-remove-sm {
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid rgba(255, 100, 100, 0.3);
  background: transparent;
  color: #ff6464;
  font-size: 11px;
  cursor: pointer;
}

.btn-remove-sm:hover {
  background: rgba(255, 100, 100, 0.1);
}

.btn-add {
  padding: 10px 16px;
  border-radius: 6px;
  border: 1px dashed rgba(74, 158, 255, 0.3);
  background: transparent;
  color: #4a9eff;
  font-size: 13px;
  cursor: pointer;
  width: 100%;
  transition: all 0.2s;
}

.btn-add:hover {
  background: rgba(74, 158, 255, 0.05);
  border-color: rgba(74, 158, 255, 0.5);
}

.btn-ghost {
  padding: 5px 14px;
  border-radius: 6px;
  border: 1px solid rgba(74, 158, 255, 0.25);
  background: transparent;
  color: #5a7a9a;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}

.btn-ghost:hover {
  background: rgba(74, 158, 255, 0.08);
  color: #2d7dd2;
}

.btn-primary {
  padding: 5px 14px;
  border-radius: 6px;
  border: none;
  background: linear-gradient(135deg, #4a9eff, #2d7dd2);
  color: white;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}

.btn-primary:hover {
  background: linear-gradient(135deg, #6db3ff, #4a9eff);
}
</style>
