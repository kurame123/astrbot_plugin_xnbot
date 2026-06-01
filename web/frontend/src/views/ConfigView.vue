<template>
  <div>
    <div class="page-title">配置编辑</div>

    <!-- 配置文件 tabs -->
    <div class="config-tabs">
      <button
        v-for="name in configNames"
        :key="name"
        class="config-tab"
        :class="{ active: activeConfig === name }"
        @click="switchConfig(name)"
      >
        {{ configLabels[name] || name }}
      </button>
    </div>

    <!-- 模式切换 -->
    <div class="mode-switch" v-if="activeConfig">
      <button class="mode-btn" :class="{ active: mode === 'form' }" @click="mode = 'form'">
        表单编辑
      </button>
      <button class="mode-btn" :class="{ active: mode === 'toml' }" @click="mode = 'toml'">
        TOML 编辑
      </button>
    </div>

    <!-- 表单模式 -->
    <div v-if="mode === 'form' && activeConfig" class="form-container">
      <!-- bot_config -->
      <BotConfigForm v-if="activeConfig === 'bot'" v-model="parsedConfig" />
      <!-- ai_config -->
      <AiConfigForm v-else-if="activeConfig === 'ai'" v-model="parsedConfig" />
      <!-- rey_config -->
      <ReyConfigForm v-else-if="activeConfig === 'rey'" v-model="parsedConfig" />
      <!-- reply_config -->
      <ReplyConfigForm v-else-if="activeConfig === 'reply'" v-model="parsedConfig" />
      <!-- emotion_config -->
      <EmotionConfigForm v-else-if="activeConfig === 'emotion'" v-model="parsedConfig" />
      <!-- emoji_config -->
      <EmojiConfigForm v-else-if="activeConfig === 'emoji'" v-model="parsedConfig" />

      <div class="form-actions">
        <button class="btn-ghost" @click="loadConfig(activeConfig)">重置</button>
        <button class="btn-primary" :disabled="saving" @click="saveForm">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>

    <!-- TOML 模式 -->
    <div class="glass-card config-editor" v-if="mode === 'toml' && activeConfig">
      <div class="editor-header">
        <span class="editor-filename">{{ activeConfig }}_config.toml</span>
        <div class="editor-actions">
          <button class="btn-ghost" @click="loadConfig(activeConfig)">重置</button>
          <button class="btn-primary" :disabled="saving" @click="saveToml">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
      <div class="editor-body" v-if="loading">
        <div class="loading-text">加载中...</div>
      </div>
      <textarea
        v-else
        v-model="tomlContent"
        class="code-editor"
        spellcheck="false"
      />
    </div>

    <div class="glass-card empty-hint" v-else-if="!loading && !activeConfig">
      <span>← 选择一个配置文件</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { listConfigs, getConfig, updateConfig } from '@/api'
import { parse, stringify } from 'smol-toml'

import BotConfigForm from '@/components/config/BotConfigForm.vue'
import AiConfigForm from '@/components/config/AiConfigForm.vue'
import ReyConfigForm from '@/components/config/ReyConfigForm.vue'
import ReplyConfigForm from '@/components/config/ReplyConfigForm.vue'
import EmotionConfigForm from '@/components/config/EmotionConfigForm.vue'
import EmojiConfigForm from '@/components/config/EmojiConfigForm.vue'

const configNames = ref<string[]>([])
const activeConfig = ref('')
const mode = ref<'form' | 'toml'>('form')
const tomlContent = ref('')
const parsedConfig = ref<any>({})
const loading = ref(false)
const saving = ref(false)
const message = useMessage()

const configLabels: Record<string, string> = {
  bot: '机器人',
  ai: 'AI 服务',
  rey: '提示词',
  reply: '回复切分',
  emotion: '情绪系统',
  emoji: '表情管理',
}

async function switchConfig(name: string) {
  activeConfig.value = name
  await loadConfig(name)
}

async function loadConfig(name: string) {
  loading.value = true
  try {
    const res = await getConfig(name)
    tomlContent.value = res.data.content
    try {
      parsedConfig.value = parse(res.data.content)
    } catch (e) {
      console.error('TOML parse error:', e)
      parsedConfig.value = {}
      message.warning('配置解析失败，已切换到 TOML 编辑模式')
      mode.value = 'toml'
    }
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function saveForm() {
  saving.value = true
  try {
    const content = stringify(parsedConfig.value)
    await updateConfig(activeConfig.value, content)
    tomlContent.value = content
    message.success('保存成功（重启 bot 后生效）')
  } catch (e: any) {
    message.error('保存失败: ' + (e.message || ''))
  } finally {
    saving.value = false
  }
}

async function saveToml() {
  saving.value = true
  try {
    // 验证 TOML 格式
    try {
      parse(tomlContent.value)
    } catch (e: any) {
      message.error('TOML 格式错误: ' + (e.message || ''))
      saving.value = false
      return
    }
    await updateConfig(activeConfig.value, tomlContent.value)
    message.success('保存成功（重启 bot 后生效）')
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const res = await listConfigs()
    configNames.value = res.data.configs
    if (configNames.value.length) {
      await switchConfig(configNames.value[0]!)
    }
  } catch {
    message.error('获取配置列表失败')
  }
})
</script>

<style scoped>
.config-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.config-tab {
  padding: 7px 18px;
  border-radius: 8px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: rgba(255, 255, 255, 0.5);
  color: #5a7a9a;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.config-tab:hover {
  background: rgba(74, 158, 255, 0.1);
  color: #2d7dd2;
  border-color: rgba(74, 158, 255, 0.35);
}

.config-tab.active {
  background: linear-gradient(135deg, rgba(74, 158, 255, 0.2), rgba(168, 212, 255, 0.15));
  color: #1a6bc4;
  font-weight: 600;
  border-color: rgba(74, 158, 255, 0.4);
}

.mode-switch {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 8px;
  padding: 4px;
  width: fit-content;
}

.mode-btn {
  padding: 6px 16px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #5a7a9a;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.mode-btn:hover {
  color: #2d7dd2;
}

.mode-btn.active {
  background: white;
  color: #1a6bc4;
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
}

.form-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 0;
}

.config-editor {
  padding: 0;
  overflow: hidden;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(74, 158, 255, 0.1);
  background: rgba(74, 158, 255, 0.04);
}

.editor-filename {
  font-size: 12px;
  color: #7a9ab8;
  font-family: 'Consolas', monospace;
}

.editor-actions {
  display: flex;
  gap: 8px;
}

.editor-body {
  padding: 24px;
}

.loading-text {
  color: #7a9ab8;
  font-size: 14px;
}

.code-editor {
  width: 100%;
  min-height: 520px;
  padding: 16px;
  background: rgba(248, 252, 255, 0.8);
  border: none;
  outline: none;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.7;
  color: #2a4a6a;
  resize: vertical;
  display: block;
}

.empty-hint {
  padding: 60px;
  text-align: center;
  color: #7a9ab8;
  font-size: 14px;
}

.btn-ghost {
  padding: 5px 14px;
  border-radius: 6px;
  border: 1px solid rgba(74, 158, 255, 0.25);
  background: transparent;
  color: #5a7a9a;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
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
  transition: all 0.2s;
  font-family: inherit;
}

.btn-primary:hover {
  background: linear-gradient(135deg, #6db3ff, #4a9eff);
  box-shadow: 0 2px 8px rgba(74, 158, 255, 0.35);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
