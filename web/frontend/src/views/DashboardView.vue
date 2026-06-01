<template>
  <div class="home-root">

    <!-- 顶部诗句 -->
    <div class="top-poem">
      <div class="poem-deco-left">✦</div>
      <span class="poem-line">永不枯萎的祈祷，奏响所有的爱</span>
      <div class="poem-deco-right">✦</div>
    </div>

    <!-- 上半区：三栏 -->
    <div class="top-area">

      <!-- 左栏 -->
      <div class="col-left">
        <div class="glass-card identity-card">
          <div class="bot-avatar">雫</div>
          <div class="bot-info">
            <div class="bot-name">{{ stats?.bot_name || '小雫' }}</div>
            <div class="bot-status"><span class="dot-green" />运行中</div>
          </div>
        </div>
        <div class="glass-card sys-list">
          <div class="sys-row"><span class="sys-icon">🖥</span><span class="sys-key">操作系统</span><span class="sys-val">{{ stats?.sys?.os || '—' }}</span></div>
          <div class="sys-row"><span class="sys-icon">💬</span><span class="sys-key">对话记忆</span><span class="sys-val">{{ stats?.memory_count ?? '—' }} 条</span></div>
          <div class="sys-row"><span class="sys-icon">👤</span><span class="sys-key">用户数</span><span class="sys-val">{{ stats?.user_count ?? '—' }}</span></div>
          <div class="sys-row"><span class="sys-icon">🔮</span><span class="sys-key">图实体</span><span class="sys-val">{{ stats?.graph_entity_count ?? '—' }}</span></div>
          <div class="sys-row"><span class="sys-icon">🔗</span><span class="sys-key">图关系</span><span class="sys-val">{{ stats?.graph_relation_count ?? '—' }}</span></div>
        </div>
      </div>

      <!-- 中栏 -->
      <div class="col-mid">

        <!-- CPU -->
        <div class="glass-card detail-card">
          <div class="detail-header"><span class="detail-dot cpu-dot" />CPU</div>
          <div class="cpu-model">{{ stats?.sys?.cpu_name || '—' }}</div>
          <div class="detail-grid4">
            <div class="dg-item">
              <div class="dg-k">物理核心</div>
              <div class="dg-v">{{ stats?.sys?.cpu_cores ?? '—' }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">逻辑线程</div>
              <div class="dg-v">{{ stats?.sys?.cpu_threads ?? '—' }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">当前主频</div>
              <div class="dg-v accent">{{ stats?.sys?.cpu_freq_mhz ? (stats.sys.cpu_freq_mhz / 1000).toFixed(2) + ' GHz' : '—' }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">最大主频</div>
              <div class="dg-v">{{ stats?.sys?.cpu_freq_max_mhz ? (stats.sys.cpu_freq_max_mhz / 1000).toFixed(2) + ' GHz' : '—' }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">使用率</div>
              <div class="dg-v accent">{{ stats?.sys?.cpu_percent ?? '—' }}%</div>
            </div>
          </div>
        </div>

        <!-- 内存 + 磁盘 -->
        <div class="glass-card detail-card">
          <div class="detail-header"><span class="detail-dot mem-dot" />内存 &amp; 磁盘</div>
          <div class="detail-grid4">
            <div class="dg-item">
              <div class="dg-k">内存总量</div>
              <div class="dg-v">{{ stats?.sys?.mem_total_gb ?? '—' }} GB</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">已用内存</div>
              <div class="dg-v accent">{{ stats?.sys?.mem_used_gb ?? '—' }} GB</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">内存使用率</div>
              <div class="dg-v accent">{{ stats?.sys?.mem_percent ?? '—' }}%</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">磁盘总量</div>
              <div class="dg-v">{{ stats?.sys?.disk_total_gb ?? '—' }} GB</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">已用磁盘</div>
              <div class="dg-v accent">{{ stats?.sys?.disk_used_gb ?? '—' }} GB</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">磁盘使用率</div>
              <div class="dg-v accent">{{ stats?.sys?.disk_percent ?? '—' }}%</div>
            </div>
          </div>
        </div>

        <!-- Token -->
        <div class="glass-card detail-card">
          <div class="detail-header"><span class="detail-dot tok-dot" />Token 消耗</div>
          <div class="detail-grid4">
            <div class="dg-item">
              <div class="dg-k">今日消耗</div>
              <div class="dg-v accent">{{ fmtNum(stats?.tokens?.today_all) }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">今日输入</div>
              <div class="dg-v">{{ fmtNum(stats?.tokens?.today_prompt) }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">今日输出</div>
              <div class="dg-v">{{ fmtNum(stats?.tokens?.today_completion) }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">累计消耗</div>
              <div class="dg-v accent">{{ fmtNum(stats?.tokens?.total_all) }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">累计输入</div>
              <div class="dg-v">{{ fmtNum(stats?.tokens?.total_prompt) }}</div>
            </div>
            <div class="dg-item">
              <div class="dg-k">累计输出</div>
              <div class="dg-v">{{ fmtNum(stats?.tokens?.total_completion) }}</div>
            </div>
          </div>
          <div class="model-list">
            <div class="model-row" v-for="(v, m) in (stats?.tokens?.by_model || {})" :key="m">
              <span class="model-n">{{ m }}</span>
              <span class="model-v">{{ fmtNum(v.prompt + v.completion) }}</span>
            </div>
          </div>
        </div>

      </div>

      <!-- 右栏：圆形表盘，撑满左栏高度 -->
      <div class="col-right">
        <div class="glass-card gauge-card">
          <svg class="gauge-svg" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(74,158,255,0.12)" stroke-width="12"/>
            <circle cx="60" cy="60" r="50" fill="none" stroke="url(#cpuG)" stroke-width="12"
              stroke-linecap="round"
              :stroke-dasharray="`${cpuArc} 314`"
              stroke-dashoffset="78.5"
              transform="rotate(-90 60 60)"/>
            <defs>
              <linearGradient id="cpuG" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#4a9eff"/>
                <stop offset="100%" stop-color="#a8d4ff"/>
              </linearGradient>
            </defs>
            <text x="60" y="56" text-anchor="middle" font-size="20" font-weight="700" fill="#1a4a7a">{{ stats?.sys?.cpu_percent ?? 0 }}%</text>
            <text x="60" y="73" text-anchor="middle" font-size="10" fill="#7a9ab8">CPU 占用</text>
          </svg>
        </div>
        <div class="glass-card gauge-card">
          <svg class="gauge-svg" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(52,199,89,0.12)" stroke-width="12"/>
            <circle cx="60" cy="60" r="50" fill="none" stroke="url(#memG)" stroke-width="12"
              stroke-linecap="round"
              :stroke-dasharray="`${memArc} 314`"
              stroke-dashoffset="78.5"
              transform="rotate(-90 60 60)"/>
            <defs>
              <linearGradient id="memG" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#34c759"/>
                <stop offset="100%" stop-color="#a8f0c0"/>
              </linearGradient>
            </defs>
            <text x="60" y="56" text-anchor="middle" font-size="20" font-weight="700" fill="#1a4a7a">{{ stats?.sys?.mem_percent ?? 0 }}%</text>
            <text x="60" y="73" text-anchor="middle" font-size="10" fill="#7a9ab8">内存占用</text>
          </svg>
        </div>
        <div class="glass-card gauge-card">
          <svg class="gauge-svg" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,149,0,0.12)" stroke-width="12"/>
            <circle cx="60" cy="60" r="50" fill="none" stroke="url(#diskG)" stroke-width="12"
              stroke-linecap="round"
              :stroke-dasharray="`${diskArc} 314`"
              stroke-dashoffset="78.5"
              transform="rotate(-90 60 60)"/>
            <defs>
              <linearGradient id="diskG" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#ff9500"/>
                <stop offset="100%" stop-color="#ffd080"/>
              </linearGradient>
            </defs>
            <text x="60" y="56" text-anchor="middle" font-size="20" font-weight="700" fill="#1a4a7a">{{ stats?.sys?.disk_percent ?? 0 }}%</text>
            <text x="60" y="73" text-anchor="middle" font-size="10" fill="#7a9ab8">磁盘占用</text>
          </svg>
        </div>
      </div>

    </div>

    <!-- 下半区：播放器 -->
    <div class="bottom-area">
      <div class="glass-card player">
        <div class="player-top">
          <div class="player-title">{{ currentTrack.title }}</div>
          <div class="player-artist">{{ currentTrack.artist }}</div>
        </div>
        <div class="player-progress" @click="seek">
          <div class="progress-bar"><div class="progress-fill" :style="{ width: progressPct + '%' }"/></div>
          <div class="progress-time"><span>{{ fmtTime(currentTime) }}</span><span>{{ fmtTime(duration) }}</span></div>
        </div>
        <div class="player-controls">
          <button class="ctrl-btn" @click="prevTrack">⏮</button>
          <button class="ctrl-btn play-btn" @click="togglePlay">{{ playing ? '⏸' : '▶' }}</button>
          <button class="ctrl-btn" @click="nextTrack">⏭</button>
          <input type="range" min="0" max="1" step="0.01" v-model.number="volume" class="vol-slider" @input="setVolume"/>
        </div>
        <div class="playlist">
          <div v-if="!playlist.length" class="pl-item" style="color:#a0b8cc;cursor:default">暂无音乐文件</div>
          <div v-for="(t,i) in playlist" :key="i" class="pl-item" :class="{active:i===trackIndex}" @click="playTrack(i)">{{ t.title }} <span style="color:#a0b8cc;font-size:10px">— {{ t.artist }}</span></div>
        </div>
        <audio ref="audioEl" @timeupdate="onTimeUpdate" @ended="nextTrack" @loadedmetadata="onMeta"/>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getStats, getMusicList, getMusicFileUrl } from '@/api'

const stats = ref<any>(null)

function fmtNum(n?: number) {
  if (n == null) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

const cpuArc  = computed(() => ((stats.value?.sys?.cpu_percent  || 0) / 100) * 314)
const memArc  = computed(() => ((stats.value?.sys?.mem_percent  || 0) / 100) * 314)
const diskArc = computed(() => ((stats.value?.sys?.disk_percent || 0) / 100) * 314)

// ── 播放器 ──────────────────────────────────────────
const audioEl     = ref<HTMLAudioElement | null>(null)
const playing     = ref(false)
const currentTime = ref(0)
const duration    = ref(0)
const volume      = ref(0.7)
const trackIndex  = ref(0)
const playlist    = ref<{ title: string; artist: string; src: string }[]>([])
const currentTrack = computed(() => playlist.value[trackIndex.value] || { title: '暂无音乐', artist: '—', src: '' })
const progressPct  = computed(() => duration.value ? (currentTime.value / duration.value) * 100 : 0)

function fmtTime(s: number) {
  if (!s || isNaN(s)) return '0:00'
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function togglePlay() {
  if (!audioEl.value || !currentTrack.value.src) return
  if (playing.value) {
    audioEl.value.pause()
    playing.value = false
  } else {
    audioEl.value.play().catch(() => {})
    playing.value = true
  }
}

function playTrack(i: number) {
  if (!playlist.value.length) return
  trackIndex.value = i
  const el = audioEl.value
  if (!el) return
  el.src = currentTrack.value.src
  el.volume = volume.value
  el.load()
  el.play().catch(() => {})
  playing.value = true
}

function nextTrack() {
  if (!playlist.value.length) return
  playTrack((trackIndex.value + 1) % playlist.value.length)
}
function prevTrack() {
  if (!playlist.value.length) return
  playTrack((trackIndex.value - 1 + playlist.value.length) % playlist.value.length)
}
function onTimeUpdate() { if (audioEl.value) currentTime.value = audioEl.value.currentTime }
function onMeta()       { if (audioEl.value) duration.value = audioEl.value.duration }
function setVolume()    { if (audioEl.value) audioEl.value.volume = volume.value }

function seek(e: MouseEvent) {
  if (!audioEl.value || !duration.value) return
  const bar = (e.currentTarget as HTMLElement).querySelector('.progress-bar') as HTMLElement
  if (!bar) return
  const rect = bar.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  audioEl.value.currentTime = ratio * duration.value
}

async function loadPlaylist() {
  try {
    const res = await getMusicList()
    const tracks = (res.data.tracks as { title: string; artist: string; filename: string }[]).map(t => ({
      title: t.title,
      artist: t.artist,
      src: getMusicFileUrl(t.filename),
    }))
    if (tracks.length) {
      playlist.value = tracks
      // 自动加载第一首（不自动播放，等用户点击）
      const first = tracks[0]
      if (audioEl.value && first) {
        audioEl.value.src = first.src
        audioEl.value.volume = volume.value
        audioEl.value.load()
      }
    }
  } catch {
    // 加载失败时保持空列表
  }
}

let timer: ReturnType<typeof setInterval>
onMounted(async () => {
  const res = await getStats(); stats.value = res.data
  timer = setInterval(async () => { const r = await getStats(); stats.value = r.data }, 10000)
  await loadPlaylist()
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Ma+Shan+Zheng&display=swap');

.home-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: calc(100vh - 84px);
}

/* ── 顶部诗句 ── */
.top-poem {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 8px 0 0;
  user-select: none;
}
.poem-line {
  font-family: 'Ma Shan Zheng', 'STKaiti', 'KaiTi', serif;
  font-size: 22px;
  color: rgba(26,74,122,0.7);
  letter-spacing: 4px;
  white-space: nowrap;
  text-shadow: 0 1px 8px rgba(255,255,255,0.8), 0 0 20px rgba(255,255,255,0.5);
}
.poem-deco-left, .poem-deco-right {
  font-size: 10px;
  color: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.3);
  letter-spacing: 2px;
}

/* ── 三栏容器：等高对齐 ── */
.top-area {
  display: flex;
  gap: 16px;
  align-items: stretch;   /* 关键：三栏等高 */
}

/* 左栏 */
.col-left {
  flex: 0 0 210px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.identity-card {
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.bot-avatar {
  width: 48px; height: 48px; border-radius: 50%;
  background: linear-gradient(135deg, #4a9eff, #a8d4ff);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700; color: white; flex-shrink: 0;
}
.bot-name   { font-size: 15px; font-weight: 700; color: #1a4a7a; }
.bot-status { display: flex; align-items: center; gap: 5px; font-size: 12px; color: #34c759; margin-top: 3px; }
.dot-green  { width: 7px; height: 7px; border-radius: 50%; background: #34c759; display: inline-block; }

.sys-list {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  flex: 1;           /* 撑满剩余高度 */
}
.sys-row { display: flex; align-items: center; gap: 7px; font-size: 12px; }
.sys-icon { font-size: 13px; width: 18px; flex-shrink: 0; }
.sys-key  { color: #7a9ab8; flex-shrink: 0; min-width: 52px; }
.sys-val  { color: #1a6bc4; font-weight: 500; margin-left: auto; font-size: 12px; }

/* 中栏 */
.col-mid {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-card { padding: 14px 16px; flex: 1; }

.detail-header {
  display: flex; align-items: center; gap: 7px;
  font-size: 13px; font-weight: 700; color: #1a4a7a;
  margin-bottom: 8px;
}
.detail-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.cpu-dot { background: #4a9eff; }
.mem-dot { background: #34c759; }
.tok-dot { background: #a855f7; }

.cpu-model {
  font-size: 11px;
  color: #5a7a9a;
  margin-bottom: 10px;
  font-family: 'Consolas', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 4列网格 */
.detail-grid4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px 12px;
}
.dg-item { display: flex; flex-direction: column; gap: 3px; }
.dg-k    { font-size: 11px; color: #7a9ab8; white-space: nowrap; }
.dg-v    { font-size: 14px; font-weight: 600; color: #1a4a7a; }
.dg-v.accent { color: #1a6bc4; }

.model-list { margin-top: 10px; display: flex; flex-direction: column; gap: 3px; }
.model-row  {
  display: flex; justify-content: space-between;
  font-size: 11px; padding: 3px 0;
  border-top: 1px solid rgba(74,158,255,0.06);
}
.model-n { color: #7a9ab8; font-family: 'Consolas', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
.model-v { color: #1a6bc4; font-weight: 600; flex-shrink: 0; }

/* 右栏：三个表盘等高分布 */
.col-right {
  flex: 0 0 148px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gauge-card {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px;
  min-height: 0;
}
.gauge-svg { width: 100%; max-width: 120px; height: auto; }

/* ── 下半区 ── */
.bottom-area {
  display: flex;
  justify-content: flex-end;
  align-items: flex-end;
  padding: 0 4px;
}

.player { flex: 0 0 300px; padding: 14px 16px; }
.player-top    { margin-bottom: 8px; }
.player-title  { font-size: 13px; font-weight: 600; color: #1a4a7a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.player-artist { font-size: 11px; color: #7a9ab8; margin-top: 2px; }
.player-progress { cursor: pointer; margin-bottom: 8px; }
.progress-bar  { height: 3px; background: rgba(74,158,255,0.15); border-radius: 2px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg,#4a9eff,#a8d4ff); transition: width 0.3s linear; }
.progress-time { display: flex; justify-content: space-between; font-size: 10px; color: #a0b8cc; margin-top: 3px; }
.player-controls { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.ctrl-btn { background: none; border: none; cursor: pointer; font-size: 14px; color: #4a9eff; padding: 3px 5px; border-radius: 5px; transition: background 0.2s; }
.ctrl-btn:hover { background: rgba(74,158,255,0.1); }
.play-btn {
  font-size: 16px; width: 32px; height: 32px; border-radius: 50%;
  background: linear-gradient(135deg,#4a9eff,#2d7dd2) !important;
  color: white !important; display: flex; align-items: center; justify-content: center;
}
.vol-slider { flex: 1; accent-color: #4a9eff; cursor: pointer; }
.playlist { display: flex; flex-direction: column; gap: 1px; max-height: 72px; overflow-y: auto; }
.playlist::-webkit-scrollbar { width: 3px; }
.playlist::-webkit-scrollbar-thumb { background: rgba(74,158,255,0.2); border-radius: 2px; }
.pl-item { font-size: 11px; color: #5a7a9a; padding: 3px 6px; border-radius: 4px; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pl-item:hover  { background: rgba(74,158,255,0.08); }
.pl-item.active { color: #1a6bc4; font-weight: 600; background: rgba(74,158,255,0.1); }
</style>
