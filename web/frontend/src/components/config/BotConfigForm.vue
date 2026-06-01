<template>
  <div class="bot-config-form">
    <!-- 服务器 -->
    <FormSection title="服务器" icon="◈">
      <div class="form-row">
        <label class="form-label">主机地址</label>
        <input v-model="model.bot.server.host" class="form-input" placeholder="0.0.0.0" />
      </div>
      <div class="form-row">
        <label class="form-label">端口</label>
        <input v-model.number="model.bot.server.port" type="number" class="form-input" placeholder="8080" />
      </div>
      <div class="form-row">
        <label class="form-label">WebSocket 路径</label>
        <input v-model="model.bot.server.ws_path" class="form-input" placeholder="/onebot/v11/ws" />
      </div>
    </FormSection>

    <!-- OneBot -->
    <FormSection title="OneBot" icon="◉">
      <div class="form-row">
        <label class="form-label">Bot QQ 号</label>
        <input v-model="model.bot.onebot.self_id" class="form-input" placeholder="NapCat 登录的 QQ 号" />
      </div>
    </FormSection>

    <!-- 角色设定 -->
    <FormSection title="角色设定" icon="◎">
      <div class="form-row">
        <label class="form-label">一句话介绍</label>
        <input v-model="model.character.short_desc" class="form-input" placeholder="角色简介" />
      </div>
      <div class="form-row">
        <label class="form-label">性格详情</label>
        <textarea v-model="model.character.profile" class="form-textarea" rows="4" placeholder="详细性格描述" />
      </div>
    </FormSection>

    <!-- 性格 -->
    <FormSection title="性格" icon="◇">
      <div class="form-row">
        <label class="form-label">性格关键词</label>
        <TagInput v-model="model.personality.traits" placeholder="输入后按回车添加" />
      </div>
      <div class="form-row">
        <label class="form-label">说话风格</label>
        <textarea v-model="model.personality.speaking_style" class="form-textarea" rows="3" placeholder="说话风格描述" />
      </div>
    </FormSection>

    <!-- 行为 -->
    <FormSection title="行为" icon="◆">
      <div class="form-row">
        <label class="form-label">允许 NSFW</label>
        <label class="form-switch">
          <input type="checkbox" v-model="model.behavior.allow_nsfw" />
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="form-row">
        <label class="form-label">记忆窗口（轮）</label>
        <input v-model.number="model.behavior.remember_length" type="number" class="form-input" min="1" />
      </div>
      <div class="form-row">
        <label class="form-label">回复前缀</label>
        <input v-model="model.behavior.reply_prefix" class="form-input" placeholder="可留空" />
      </div>
      <div class="form-row">
        <label class="form-label">历史加载条数</label>
        <input v-model.number="model.behavior.history_load_limit" type="number" class="form-input" min="1" />
      </div>
    </FormSection>

    <!-- 搜索 -->
    <FormSection title="搜索" icon="○">
      <div class="form-row">
        <label class="form-label">Serper API Key</label>
        <input v-model="model.search.serper_api_key" class="form-input" placeholder="留空则禁用联网搜索" />
      </div>
    </FormSection>

    <!-- XN_Core -->
    <FormSection title="XN_Core 内核" icon="♡">
      <div class="form-row">
        <label class="form-label">启用内核</label>
        <label class="form-switch">
          <input type="checkbox" v-model="model.xn_core.enabled" />
          <span class="switch-slider"></span>
        </label>
      </div>

      <!-- 睡眠 -->
      <div class="sub-section">
        <div class="sub-title">睡眠</div>
        <div class="form-row">
          <label class="form-label">睡眠关键词</label>
          <TagInput v-model="model.xn_core.sleep.keywords" placeholder="输入后按回车添加" />
        </div>
        <div class="form-row">
          <label class="form-label">最短睡眠（小时）</label>
          <input v-model.number="model.xn_core.sleep.min_sleep_hours" type="number" class="form-input" min="1" step="0.5" />
        </div>
        <div class="form-row">
          <label class="form-label">最长睡眠（小时）</label>
          <input v-model.number="model.xn_core.sleep.max_sleep_hours" type="number" class="form-input" min="1" step="0.5" />
        </div>
      </div>

      <!-- 心跳 -->
      <div class="sub-section">
        <div class="sub-title">心跳</div>
        <div class="form-row">
          <label class="form-label">每日最少心跳</label>
          <input v-model.number="model.xn_core.heartbeat.min_beats_per_day" type="number" class="form-input" min="1" max="20" />
        </div>
        <div class="form-row">
          <label class="form-label">每日最多心跳</label>
          <input v-model.number="model.xn_core.heartbeat.max_beats_per_day" type="number" class="form-input" min="1" max="20" />
        </div>
      </div>

      <!-- 沉默 -->
      <div class="sub-section">
        <div class="sub-title">沉默</div>
        <div class="form-row">
          <label class="form-label">启用沉默机制</label>
          <label class="form-switch">
            <input type="checkbox" v-model="model.xn_core.silence.enabled" />
            <span class="switch-slider"></span>
          </label>
        </div>
        <div class="form-row">
          <label class="form-label">连续沉默上限</label>
          <input v-model.number="model.xn_core.silence.max_consecutive" type="number" class="form-input" min="1" />
        </div>
        <div class="form-row">
          <label class="form-label">跳过单字消息</label>
          <label class="form-switch">
            <input type="checkbox" v-model="model.xn_core.silence.skip_single_char" />
            <span class="switch-slider"></span>
          </label>
        </div>
        <div class="form-row">
          <label class="form-label">跳过纯表情</label>
          <label class="form-switch">
            <input type="checkbox" v-model="model.xn_core.silence.skip_emoji_only" />
            <span class="switch-slider"></span>
          </label>
        </div>
        <div class="form-row">
          <label class="form-label">跳过重复消息</label>
          <label class="form-switch">
            <input type="checkbox" v-model="model.xn_core.silence.skip_repeat" />
            <span class="switch-slider"></span>
          </label>
        </div>
        <div class="form-row">
          <label class="form-label">短时消息上限</label>
          <input v-model.number="model.xn_core.silence.burst_limit" type="number" class="form-input" min="1" />
        </div>
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
    // 确保嵌套结构存在
    if (!cfg.bot) cfg.bot = {}
    if (!cfg.bot.server) cfg.bot.server = { host: '0.0.0.0', port: 8080, ws_path: '/onebot/v11/ws' }
    if (!cfg.bot.onebot) cfg.bot.onebot = { self_id: '' }
    if (!cfg.character) cfg.character = { short_desc: '', profile: '' }
    if (!cfg.personality) cfg.personality = { traits: [], speaking_style: '' }
    if (!cfg.behavior) cfg.behavior = { allow_nsfw: false, remember_length: 20, reply_prefix: '', history_load_limit: 20 }
    if (!cfg.search) cfg.search = { serper_api_key: '' }
    if (!cfg.xn_core) cfg.xn_core = {}
    if (!cfg.xn_core.sleep) cfg.xn_core.sleep = { keywords: [], min_sleep_hours: 6, max_sleep_hours: 12 }
    if (!cfg.xn_core.heartbeat) cfg.xn_core.heartbeat = { min_beats_per_day: 3, max_beats_per_day: 8 }
    if (!cfg.xn_core.silence) cfg.xn_core.silence = { enabled: true, max_consecutive: 2, skip_single_char: true, skip_emoji_only: true, skip_repeat: true, burst_limit: 4 }
    // 确保数组字段是数组
    if (!Array.isArray(cfg.personality.traits)) cfg.personality.traits = []
    if (!Array.isArray(cfg.xn_core.sleep.keywords)) cfg.xn_core.sleep.keywords = []
    return cfg
  },
  set: (v) => emit('update:modelValue', v),
})
</script>

<style scoped>
.bot-config-form {
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
  transition: border-color 0.2s;
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
  font-family: inherit;
}

.form-textarea:focus {
  border-color: rgba(74, 158, 255, 0.4);
}

/* 开关 */
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

/* 子分区 */
.sub-section {
  background: rgba(74, 158, 255, 0.03);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sub-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a4a7a;
  margin-bottom: 4px;
}
</style>
