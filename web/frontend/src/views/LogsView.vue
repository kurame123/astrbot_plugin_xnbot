<template>
  <div>
    <div class="page-title">日志查看</div>

    <div class="log-toolbar glass-card">
      <div class="toolbar-group">
        <button
          class="log-tab"
          :class="{ active: logName === 'llm' }"
          @click="logName = 'llm'; load()"
        >LLM 日志</button>
        <button
          class="log-tab"
          :class="{ active: logName === 'agent' }"
          @click="logName = 'agent'; load()"
        >Agent 日志</button>
      </div>
      <div class="toolbar-group">
        <input
          v-model="filter"
          class="filter-input"
          placeholder="过滤关键词..."
          @keyup.enter="load"
        />
        <select v-model="lines" class="lines-select" @change="load">
          <option :value="100">100 行</option>
          <option :value="300">300 行</option>
          <option :value="500">500 行</option>
          <option :value="1000">1000 行</option>
        </select>
        <button class="btn-ghost" @click="load">刷新</button>
        <button class="btn-ghost" @click="scrollBottom">↓ 底部</button>
      </div>
    </div>

    <div class="glass-card log-box-wrap">
      <div v-if="loading" class="log-loading">加载中...</div>
      <div ref="logBox" class="log-box" v-else>
        <div
          v-for="(line, i) in logLines"
          :key="i"
          class="log-line"
          :class="lineClass(line)"
        >{{ line }}</div>
        <div v-if="!logLines.length" class="log-empty">暂无日志</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { getLogs } from '@/api'

const logName = ref('llm')
const filter = ref('')
const lines = ref(300)
const loading = ref(false)
const logLines = ref<string[]>([])
const logBox = ref<HTMLElement | null>(null)

function lineClass(line: string) {
  if (line.includes('[ERROR]')) return 'log-error'
  if (line.includes('[WARNING]')) return 'log-warn'
  if (line.includes('[SUCCESS]')) return 'log-success'
  if (line.includes('[INFO]')) return 'log-info'
  return ''
}

async function load() {
  loading.value = true
  try {
    const res = await getLogs(logName.value, {
      lines: lines.value,
      filter: filter.value || undefined,
    })
    logLines.value = res.data.lines
    await nextTick()
    scrollBottom()
  } finally {
    loading.value = false
  }
}

function scrollBottom() {
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
}

onMounted(load)
</script>

<style scoped>
.log-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.log-tab {
  padding: 6px 16px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: transparent;
  color: #5a7a9a;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.log-tab.active {
  background: linear-gradient(135deg, rgba(74, 158, 255, 0.18), rgba(168, 212, 255, 0.12));
  color: #1a6bc4;
  font-weight: 600;
  border-color: rgba(74, 158, 255, 0.4);
}

.filter-input {
  padding: 6px 12px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: rgba(255, 255, 255, 0.6);
  color: #2a4a6a;
  font-size: 13px;
  outline: none;
  width: 180px;
  font-family: inherit;
}

.filter-input:focus {
  border-color: rgba(74, 158, 255, 0.5);
  background: rgba(255, 255, 255, 0.85);
}

.lines-select {
  padding: 6px 10px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: rgba(255, 255, 255, 0.6);
  color: #2a4a6a;
  font-size: 13px;
  outline: none;
  cursor: pointer;
  font-family: inherit;
}

.btn-ghost {
  padding: 6px 14px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
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

.log-box-wrap {
  padding: 0;
  overflow: hidden;
}

.log-loading {
  padding: 40px;
  text-align: center;
  color: #7a9ab8;
  font-size: 14px;
}

.log-box {
  height: calc(100vh - 240px);
  overflow-y: auto;
  padding: 14px 16px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.75;
  background: rgba(240, 248, 255, 0.6);
}

.log-box::-webkit-scrollbar { width: 5px; }
.log-box::-webkit-scrollbar-track { background: transparent; }
.log-box::-webkit-scrollbar-thumb { background: rgba(74, 158, 255, 0.2); border-radius: 3px; }

.log-line {
  color: #3a5a7a;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-error { color: #c0392b; }
.log-warn  { color: #d68910; }
.log-success { color: #1a8a3a; }
.log-info  { color: #2471a3; }

.log-empty {
  text-align: center;
  color: #a0b8cc;
  padding: 40px;
}
</style>
