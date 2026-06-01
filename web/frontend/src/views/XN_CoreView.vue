<template>
  <div class="xn-root">
    <div class="page-title">XN_Core 内核</div>

    <div class="xn-grid">
      <!-- 左栏：状态总览 -->
      <div class="xn-left">

        <!-- 状态总览卡片 -->
        <div class="glass-card overview-card">
          <div class="ov-header">
            <span class="ov-icon">♡</span>
            <span class="ov-title">内核状态</span>
            <span class="ov-badge" :class="status?.enabled ? 'ov-on' : 'ov-off'">
              {{ status?.enabled ? 'LIVE' : 'OFF' }}
            </span>
          </div>
          <div class="ov-grid">
            <div class="ov-item">
              <div class="ov-val">{{ status?.reflections_count ?? '—' }}</div>
              <div class="ov-label">反思日记</div>
            </div>
            <div class="ov-item">
              <div class="ov-val">{{ status?.heartbeat_count ?? '—' }}</div>
              <div class="ov-label">心跳次数</div>
            </div>
            <div class="ov-item">
              <div class="ov-val">{{ status?.heartbeat_today?.send ?? 0 }}/{{ status?.heartbeat_today?.skip ?? 0 }}</div>
              <div class="ov-label">今日心跳 发/跳</div>
            </div>
            <div class="ov-item">
              <div class="ov-val">{{ status?.max_beats ?? '—' }}</div>
              <div class="ov-label">心跳上限/天</div>
            </div>
            <div class="ov-item">
              <div class="ov-val">{{ status?.sleep_hours_range?.[0] ?? '—' }}~{{ status?.sleep_hours_range?.[1] ?? '—' }}h</div>
              <div class="ov-label">睡眠范围</div>
            </div>
          </div>
        </div>

        <!-- 当前睡眠 -->
        <div class="glass-card sleep-card" v-if="status?.sleeping_users?.length">
          <div class="sc-header">
            <span class="sc-z">💤</span>
            <span>正在睡眠</span>
          </div>
          <div class="sc-body" v-for="u in status.sleeping_users" :key="u.user_id">
            <div class="sc-top">
              <span class="sc-user">{{ u.user_id }}</span>
              <span class="sc-remain" v-if="u.wake_time_ts">{{ formatRemain(u.wake_time_ts) }}</span>
            </div>
            <div class="sc-bar">
              <div class="sc-bar-fill" :style="{ width: sleepPct(u) + '%' }"></div>
            </div>
            <div class="sc-time">{{ u.sleep_start }} → {{ u.wake_time }}</div>
          </div>
        </div>

        <!-- 最近反思 -->
        <div class="glass-card recent-ref" v-if="status?.last_reflection">
          <div class="rr-header">最近一次反思</div>
          <div class="rr-meta">
            <span class="rr-user">{{ status.last_reflection.user_id }}</span>
            <span class="rr-score" :class="status.last_reflection.health_score >= 7 ? 'rr-high' : ''">
              {{ status.last_reflection.health_score?.toFixed(1) }}
            </span>
            <span class="rr-date">{{ status.last_reflection.created_at_str }}</span>
          </div>
          <div class="rr-text">{{ status.last_reflection.summary }}</div>
          <div class="rr-feeling" v-if="status.last_reflection.feeling">{{ status.last_reflection.feeling }}</div>
        </div>

        <!-- 健康仪表盘 -->
        <div class="glass-card gauge-card">
          <div class="gc-header">对话健康度</div>
          <div class="gc-body" v-if="status?.last_reflection">
            <svg class="gc-svg" viewBox="0 0 160 100">
              <path d="M 20 90 A 60 60 0 0 1 140 90" fill="none"
                stroke="rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.08)"
                stroke-width="10" stroke-linecap="round"/>
              <path d="M 20 90 A 60 60 0 0 1 140 90" fill="none"
                :stroke="gaugeColor"
                stroke-width="10" stroke-linecap="round"
                :stroke-dasharray="arcLen"
                :stroke-dashoffset="arcOffset"/>
              <text x="80" y="75" text-anchor="middle" font-size="22" font-weight="800"
                :fill="gaugeColor">{{ healthScore.toFixed(1) }}</text>
              <text x="80" y="92" text-anchor="middle" font-size="9" fill="#7a9ab8">/ 10.0</text>
            </svg>
            <div class="gc-label" :style="{ color: gaugeColor }">{{ healthLabel }}</div>
          </div>
          <div class="gc-empty" v-else>暂无数据</div>
        </div>

        <!-- 空状态 -->
        <div class="glass-card empty-card" v-if="!status?.sleeping_users?.length && !status?.last_reflection">
          <div class="empty-icon">♡</div>
          <div class="empty-text">小雫正在正常运行中</div>
        </div>

      </div>

      <!-- 右栏：记录 -->
      <div class="xn-right">

        <!-- 反思日记 -->
        <div class="glass-card record-card">
          <div class="rc-header">
            <span class="rc-dot rc-dot-blue"></span>
            <span class="rc-title">反思日记</span>
            <span class="rc-count">{{ refTotal }} 条</span>
          </div>
          <div class="rc-body">
            <div v-if="loadingRef" class="rc-loading">加载中...</div>
            <div v-else-if="!reflections.length" class="rc-empty">暂无记录</div>
            <div v-else class="rc-list">
              <div class="rc-item" v-for="row in reflections" :key="row.id">
                <div class="rci-top">
                  <span class="rci-user">{{ row.user_id }}</span>
                  <span class="rci-score" :class="row.health_score >= 7 ? 'score-high' : row.health_score >= 4 ? 'score-mid' : 'score-low'">
                    {{ row.health_score?.toFixed(1) }}
                  </span>
                  <span class="rci-date">{{ row.created_at_str }}</span>
                </div>
                <div class="rci-time">{{ row.sleep_start_str }} ~ {{ row.sleep_end_str }}</div>
                <div class="rci-text">{{ row.summary }}</div>
                <div class="rci-feeling" v-if="row.feeling">{{ row.feeling }}</div>
                <div class="rci-hl" v-if="row.highlights_list?.length">
                  <span v-for="(h, i) in row.highlights_list" :key="i" class="hl-tag">{{ h }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="rc-footer" v-if="refTotal > refPageSize">
            <button class="pg-btn" :disabled="refPage <= 1" @click="refPage--; loadReflections()">‹</button>
            <span class="pg-info">{{ refPage }}/{{ refPageCount }}</span>
            <button class="pg-btn" :disabled="refPage >= refPageCount" @click="refPage++; loadReflections()">›</button>
          </div>
        </div>

        <!-- 心跳日志 -->
        <div class="glass-card record-card">
          <div class="rc-header">
            <span class="rc-dot rc-dot-pink"></span>
            <span class="rc-title">心跳日志</span>
            <span class="rc-count">{{ hbTotal }} 条</span>
          </div>
          <div class="rc-body">
            <div v-if="loadingHb" class="rc-loading">加载中...</div>
            <div v-else-if="!hbLogs.length" class="rc-empty">暂无记录</div>
            <div v-else class="rc-list">
              <div class="rc-item" v-for="row in hbLogs" :key="row.id">
                <div class="rci-top">
                  <span class="rci-user">{{ row.user_id }}</span>
                  <span class="rci-decision" :class="row.decision === 'send' ? 'dec-send' : 'dec-skip'">
                    {{ row.decision === 'send' ? '已发送' : '已跳过' }}
                  </span>
                  <span class="rci-date">{{ row.trigger_time_str }}</span>
                </div>
                <div class="rci-text" v-if="row.message">{{ row.message }}</div>
              </div>
            </div>
          </div>
          <div class="rc-footer" v-if="hbTotal > hbPageSize">
            <button class="pg-btn" :disabled="hbPage <= 1" @click="hbPage--; loadHeartbeatLogs()">‹</button>
            <span class="pg-info">{{ hbPage }}/{{ hbPageCount }}</span>
            <button class="pg-btn" :disabled="hbPage >= hbPageCount" @click="hbPage++; loadHeartbeatLogs()">›</button>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getXnCoreStatus, getXnCoreReflections, getXnCoreHeartbeatLogs } from '@/api'

const nowTs = ref(Math.floor(Date.now() / 1000))
setInterval(() => { nowTs.value = Math.floor(Date.now() / 1000) }, 10000)

const status = ref<any>(null)

// 健康分
const healthScore = computed(() => {
  const v = status.value?.last_reflection?.health_score
  return v != null ? Number(v) : 0
})

// 弧线：半圆周长 = π × r，用 dashoffset 控制填充比例
const arcLen = Math.PI * 60  // ≈ 188.5
const arcOffset = computed(() => arcLen * (1 - Math.max(0, Math.min(1, healthScore.value / 10))))

const gaugeColor = computed(() => {
  const s = healthScore.value
  if (s >= 7) return '#34c759'
  if (s >= 4) return '#ff9500'
  return '#ff6464'
})

const healthLabel = computed(() => {
  const s = healthScore.value
  if (s >= 8) return '对话充实，互动质量高'
  if (s >= 6) return '对话正常，有一定交流'
  if (s >= 4) return '对话较少，互动一般'
  if (s > 0) return '对话匮乏，需要更多陪伴'
  return '暂无数据'
})

function sleepPct(u: any) {
  if (!u.sleep_start_ts || !u.wake_time_ts) return 0
  const total = u.wake_time_ts - u.sleep_start_ts
  if (total <= 0) return 0
  const elapsed = nowTs.value - u.sleep_start_ts
  return Math.max(0, Math.min(100, (elapsed / total) * 100))
}

function formatRemain(wakeTs: number) {
  const diff = wakeTs - nowTs.value
  if (diff <= 0) return '即将醒来'
  const h = Math.floor(diff / 3600)
  const m = Math.floor((diff % 3600) / 60)
  if (h > 0) return `还剩 ${h}h${m}m`
  return `还剩 ${m}m`
}

// 反思
const reflections = ref<any[]>([])
const refTotal = ref(0)
const refPage = ref(1)
const refPageSize = ref(20)
const refPageCount = computed(() => Math.ceil(refTotal.value / refPageSize.value))
const loadingRef = ref(false)

async function loadReflections() {
  loadingRef.value = true
  try {
    const res = await getXnCoreReflections({ page: refPage.value, page_size: refPageSize.value })
    reflections.value = res.data.items
    refTotal.value = res.data.total
  } catch { /* ignore */ }
  loadingRef.value = false
}

// 心跳
const hbLogs = ref<any[]>([])
const hbTotal = ref(0)
const hbPage = ref(1)
const hbPageSize = ref(20)
const hbPageCount = computed(() => Math.ceil(hbTotal.value / hbPageSize.value))
const loadingHb = ref(false)

async function loadHeartbeatLogs() {
  loadingHb.value = true
  try {
    const res = await getXnCoreHeartbeatLogs({ page: hbPage.value, page_size: hbPageSize.value })
    hbLogs.value = res.data.items
    hbTotal.value = res.data.total
  } catch { /* ignore */ }
  loadingHb.value = false
}

onMounted(async () => {
  try {
    const res = await getXnCoreStatus()
    status.value = res.data
  } catch { /* ignore */ }
  await loadReflections()
  await loadHeartbeatLogs()
})
</script>

<style scoped>
.xn-root {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 84px);
}

/* 两栏布局 */
.xn-grid {
  display: flex;
  gap: 18px;
  flex: 1;
  min-height: 0;
}

.xn-left {
  flex: 0 0 320px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.xn-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

/* ── 左栏：总览卡片 ── */
.overview-card {
  padding: 20px;
}
.ov-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
}
.ov-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--primary), rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.5));
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 16px;
}
.ov-title {
  font-size: 15px;
  font-weight: 700;
  color: #1a4a7a;
}
.ov-badge {
  margin-left: auto;
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1px;
}
.ov-on {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}
.ov-off {
  background: rgba(160, 184, 204, 0.15);
  color: #7a9ab8;
}
.ov-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.ov-item {
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.04);
}
.ov-val {
  font-size: 20px;
  font-weight: 700;
  color: #1a4a7a;
}
.ov-label {
  font-size: 11px;
  color: #7a9ab8;
  margin-top: 2px;
}

/* ── 左栏：睡眠卡片 ── */
.sleep-card {
  padding: 16px 18px;
}
.sc-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1a4a7a;
  margin-bottom: 12px;
}
.sc-z { font-size: 16px; }
.sc-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sc-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sc-user {
  font-size: 12px;
  font-family: 'Consolas', monospace;
  color: #5a7a9a;
}
.sc-remain {
  font-size: 11px;
  font-weight: 600;
  color: var(--primary);
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.08);
  padding: 1px 8px;
  border-radius: 10px;
}
.sc-bar {
  height: 6px;
  border-radius: 3px;
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.1);
  overflow: hidden;
}
.sc-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--primary), rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.4));
  transition: width 0.5s;
}
.sc-time {
  font-size: 11px;
  color: #7a9ab8;
  font-family: 'Consolas', monospace;
}

/* ── 左栏：最近反思 ── */
.recent-ref {
  padding: 16px 18px;
}
.rr-header {
  font-size: 12px;
  font-weight: 600;
  color: #7a9ab8;
  margin-bottom: 10px;
  letter-spacing: 0.5px;
}
.rr-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.rr-user {
  font-size: 12px;
  font-family: 'Consolas', monospace;
  color: #5a7a9a;
}
.rr-score {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 700;
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.08);
  color: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.9);
}
.rr-high {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}
.rr-date {
  margin-left: auto;
  font-size: 10px;
  color: #a0b8cc;
  font-family: 'Consolas', monospace;
}
.rr-text {
  font-size: 12px;
  color: #3a5a7a;
  line-height: 1.7;
}

/* ── 左栏：空状态 ── */
.empty-card {
  padding: 40px 20px;
  text-align: center;
}
.empty-icon {
  font-size: 32px;
  margin-bottom: 10px;
  opacity: 0.4;
}
.empty-text {
  font-size: 13px;
  color: #a0b8cc;
}

/* ── 左栏：健康仪表盘 ── */
.gauge-card {
  padding: 16px 18px;
}
.gc-header {
  font-size: 12px;
  font-weight: 600;
  color: #7a9ab8;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}
.gc-body {
  display: flex;
  align-items: center;
  gap: 16px;
}
.gc-svg {
  width: 140px;
  height: 90px;
  flex-shrink: 0;
}
.gc-label {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}
.gc-empty {
  padding: 20px;
  text-align: center;
  color: #a0b8cc;
  font-size: 13px;
}

/* ── 右栏：记录卡片 ── */
.record-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.rc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.06);
  flex-shrink: 0;
}
.rc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.rc-dot-blue { background: #4a9eff; }
.rc-dot-pink { background: #f472b6; }
.rc-title {
  font-size: 14px;
  font-weight: 700;
  color: #1a4a7a;
}
.rc-count {
  margin-left: auto;
  font-size: 11px;
  color: #a0b8cc;
  font-family: 'Consolas', monospace;
}
.rc-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.rc-body::-webkit-scrollbar { width: 4px; }
.rc-body::-webkit-scrollbar-thumb { background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.15); border-radius: 2px; }
.rc-loading, .rc-empty {
  padding: 32px;
  text-align: center;
  color: #a0b8cc;
  font-size: 13px;
}
.rc-list {
  display: flex;
  flex-direction: column;
}
.rc-item {
  padding: 10px 18px;
  border-bottom: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.04);
  transition: background 0.15s;
}
.rc-item:hover {
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.03);
}
.rci-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.rci-user {
  font-size: 11px;
  font-family: 'Consolas', monospace;
  color: #5a7a9a;
}
.rci-score {
  padding: 1px 7px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
}
.score-high { background: rgba(52,199,89,0.12); color: #34c759; }
.score-mid  { background: rgba(255,149,0,0.12); color: #ff9500; }
.score-low  { background: rgba(255,100,100,0.12); color: #ff6464; }
.rci-decision {
  padding: 1px 7px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
}
.dec-send { background: rgba(52,199,89,0.12); color: #34c759; }
.dec-skip { background: rgba(160,184,204,0.12); color: #7a9ab8; }
.rci-date {
  margin-left: auto;
  font-size: 10px;
  color: #a0b8cc;
  font-family: 'Consolas', monospace;
}
.rci-time {
  font-size: 10px;
  color: #7a9ab8;
  font-family: 'Consolas', monospace;
  margin-bottom: 3px;
}
.rci-text {
  font-size: 12px;
  color: #3a5a7a;
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.rc-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px;
  border-top: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.06);
  flex-shrink: 0;
}
.pg-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.15);
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.05);
  color: var(--primary);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.pg-btn:hover:not(:disabled) { background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.12); }
.pg-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.pg-info {
  font-size: 11px;
  color: #7a9ab8;
  font-family: 'Consolas', monospace;
}
</style>
