<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-root">
        <!-- 背景图 -->
        <div class="bg-image" :style="{ filter: `blur(${theme.bgBlur}px)` }" />

        <!-- 雪花 canvas（全屏覆盖，pointer-events:none 不拦截点击） -->
        <canvas ref="snowCanvas" class="snow-canvas" />

        <!-- 侧边栏 -->
        <aside class="sidebar">
          <div class="sidebar-logo">
            <span class="logo-dot" />
            <span class="logo-text">XNBot</span>
          </div>
          <nav class="sidebar-nav">
            <button
              v-for="(item, idx) in menuOptions"
              :key="item.key"
              class="nav-item"
              :class="{ active: activeKey === item.key }"
              :style="{ animationDelay: (idx * 0.05) + 's' }"
              @click="handleNav(item.key)"
            >
              <span class="nav-icon">{{ item.icon }}</span>
              <span class="nav-label">{{ item.label }}</span>
            </button>
          </nav>

          <!-- 主题面板 -->
          <div class="theme-panel">
            <button class="theme-toggle" @click="themeOpen = !themeOpen">
              <span>🎨</span>
              <span class="nav-label">主题</span>
              <span class="toggle-arrow" :class="{ open: themeOpen }">›</span>
            </button>
            <div class="theme-body" v-show="themeOpen">
              <!-- 预设主题色 -->
              <div class="theme-label">主题色</div>
              <div class="color-presets">
                <button
                  v-for="p in colorPresets"
                  :key="p.name"
                  class="color-dot"
                  :style="{ background: p.primary }"
                  :class="{ selected: theme.primary === p.primary }"
                  :title="p.name"
                  @click="applyPreset(p)"
                />
              </div>
              <!-- 自定义主色：HSL 色盘 -->
              <div class="theme-label" style="margin-top:8px">自定义</div>
              <div class="color-wheel-wrap">
                <canvas ref="hueCanvas" class="hue-ring" width="140" height="140"
                  @mousedown="startHueDrag" />
                <canvas ref="slCanvas" class="sl-square" width="70" height="70"
                  @mousedown="startSLDrag" />
                <div class="wheel-cursor" :style="hueCursorStyle" />
                <div class="sl-cursor" :style="slCursorStyle" />
              </div>
              <div class="color-preview-row">
                <div class="color-preview" :style="{ background: theme.primary }" />
                <span class="color-hex">{{ theme.primary }}</span>
              </div>

              <!-- 毛玻璃透明度 -->
              <div class="theme-label" style="margin-top:10px">
                卡片透明度 <span class="val-hint">{{ Math.round(theme.glassOpacity * 100) }}%</span>
              </div>
              <input type="range" min="0.1" max="0.95" step="0.01"
                v-model.number="theme.glassOpacity" class="theme-slider" @input="applyTheme" />

              <!-- 毛玻璃模糊度 -->
              <div class="theme-label" style="margin-top:8px">
                卡片模糊 <span class="val-hint">{{ theme.glassBlur }}px</span>
              </div>
              <input type="range" min="0" max="32" step="1"
                v-model.number="theme.glassBlur" class="theme-slider" @input="applyTheme" />

              <!-- 背景图模糊 -->
              <div class="theme-label" style="margin-top:8px">
                背景模糊 <span class="val-hint">{{ theme.bgBlur }}px</span>
              </div>
              <input type="range" min="0" max="20" step="1"
                v-model.number="theme.bgBlur" class="theme-slider" @input="applyTheme" />
            </div>
          </div>

          <div class="sidebar-footer">小雫的控制台</div>
        </aside>

        <!-- 顶部加载条 -->
        <div class="route-loading-bar" :class="{ active: routeLoading }" />

        <!-- 主内容区 -->
        <main class="main-content">
          <router-view v-slot="{ Component, route }">
            <Transition name="page" mode="out-in">
              <component :is="Component" :key="route.path" />
            </Transition>
          </router-view>
        </main>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const p = theme.value.primary
  const { r, g, b } = hexToRgb(p)
  const hover = `rgb(${Math.min(255, r + 30)},${Math.min(255, g + 30)},${Math.min(255, b + 30)})`
  const pressed = `rgb(${Math.max(0, r - 40)},${Math.max(0, g - 40)},${Math.max(0, b - 40)})`
  return {
    common: {
      primaryColor: p,
      primaryColorHover: hover,
      primaryColorPressed: pressed,
      borderRadius: '10px',
      fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif',
    },
    Button: { borderRadiusMedium: '8px', borderRadiusSmall: '6px' },
    Input: { borderRadius: '8px' },
    Card: { borderRadius: '12px' },
  }
})

const route = useRoute()
const router = useRouter()
const activeKey = computed(() => route.name as string)

// 路由加载条
const routeLoading = ref(false)
router.beforeEach(() => { routeLoading.value = true })
router.afterEach(() => { setTimeout(() => { routeLoading.value = false }, 300) })

const menuOptions = [
  { label: 'Home', key: 'dashboard', icon: '◈' },
  { label: '记忆', key: 'memories', icon: '◉' },
  { label: '图谱', key: 'graph', icon: '◎' },
  { label: '配置', key: 'config', icon: '◧' },
  { label: '日志', key: 'logs', icon: '◫' },
  { label: '内核', key: 'xn_core', icon: '♡' },
]

function handleNav(key: string) {
  router.push({ name: key })
}

// ── 主题系统 ──────────────────────────────────────────
interface Theme {
  primary: string
  glassOpacity: number
  glassBlur: number
  bgBlur: number
}

const STORAGE_KEY = 'xnbot-theme'

const defaultTheme: Theme = {
  primary: '#4a9eff',
  glassOpacity: 0.65,
  glassBlur: 12,
  bgBlur: 0,
}

const colorPresets = [
  { name: '天蓝', primary: '#4a9eff', overlay: 'rgba(220,240,255,' },
  { name: '薰衣草', primary: '#9b7fe8', overlay: 'rgba(235,225,255,' },
  { name: '樱粉', primary: '#f472b6', overlay: 'rgba(255,225,235,' },
  { name: '抹茶', primary: '#34c759', overlay: 'rgba(220,245,225,' },
  { name: '珊瑚', primary: '#ff6b6b', overlay: 'rgba(255,230,225,' },
  { name: '金橙', primary: '#ff9500', overlay: 'rgba(255,240,215,' },
  { name: '深海', primary: '#0ea5e9', overlay: 'rgba(210,235,255,' },
  { name: '暗紫', primary: '#6366f1', overlay: 'rgba(230,225,255,' },
]

const theme = ref<Theme>({ ...defaultTheme })
const themeOpen = ref(false)

function hexToRgb(hex: string) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return { r, g, b }
}

function applyTheme() {
  const { r, g, b } = hexToRgb(theme.value.primary)
  const root = document.documentElement
  root.style.setProperty('--primary', theme.value.primary)
  root.style.setProperty('--primary-r', String(r))
  root.style.setProperty('--primary-g', String(g))
  root.style.setProperty('--primary-b', String(b))
  root.style.setProperty('--glass-opacity', String(theme.value.glassOpacity))

  // backdrop-filter 不支持 CSS 变量，用动态 <style> 注入
  let styleEl = document.getElementById('xnbot-dynamic-style') as HTMLStyleElement | null
  if (!styleEl) {
    styleEl = document.createElement('style')
    styleEl.id = 'xnbot-dynamic-style'
    document.head.appendChild(styleEl)
  }
  styleEl.textContent = `
    .glass-card {
      background: rgba(255,255,255,${theme.value.glassOpacity}) !important;
      backdrop-filter: blur(${theme.value.glassBlur}px) !important;
      -webkit-backdrop-filter: blur(${theme.value.glassBlur}px) !important;
      border: 1.5px solid rgba(${r},${g},${b},0.35) !important;
      box-shadow: 0 4px 24px rgba(${r},${g},${b},0.12), inset 0 0 0 0.5px rgba(${r},${g},${b},0.15) !important;
    }
    .sidebar {
      backdrop-filter: blur(${theme.value.glassBlur}px) !important;
      -webkit-backdrop-filter: blur(${theme.value.glassBlur}px) !important;
      border-right: 1.5px solid rgba(${r},${g},${b},0.25) !important;
    }
    .page-title { color: rgb(${Math.round(r*0.3)},${Math.round(g*0.3+20)},${Math.round(b*0.4+40)}) !important; }
    .bot-name, .dg-v, .sys-val, .iv, .info-val { color: rgb(${Math.round(r*0.25)},${Math.round(g*0.25+15)},${Math.round(b*0.35+30)}) !important; }
    .detail-header, .info-title { color: rgb(${Math.round(r*0.35)},${Math.round(g*0.35+10)},${Math.round(b*0.45+20)}) !important; }
    .dg-v.accent, .sys-val, .model-v, .token-num { color: rgba(${r},${g},${b},0.9) !important; }
    .nav-item.active { color: rgba(${r},${g},${b},1) !important; }
    .nav-item:hover { color: rgba(${r},${g},${b},0.85) !important; }
    .logo-text { background: linear-gradient(135deg, rgba(${r},${g},${b},1), rgba(${r},${g},${b},0.6)) !important; -webkit-background-clip: text !important; background-clip: text !important; }
    .logo-dot { background: linear-gradient(135deg, rgba(${r},${g},${b},1), rgba(${r},${g},${b},0.4)) !important; box-shadow: 0 0 8px rgba(${r},${g},${b},0.6) !important; }
    .section-title, .detail-dot.cpu-dot ~ *, .detail-header { color: rgba(${r},${g},${b},0.85) !important; }
    .status-badge { background: rgba(52,199,89,0.12) !important; }
    .imp-badge { background: rgba(${r},${g},${b},0.1) !important; color: rgba(${r},${g},${b},0.9) !important; }
    .type-badge { background: rgba(${r},${g},${b},0.1) !important; color: rgba(${r},${g},${b},0.9) !important; }
    .btn-primary { background: linear-gradient(135deg, rgba(${r},${g},${b},1), rgba(${Math.round(r*0.7)},${Math.round(g*0.7)},${Math.round(b*0.7)},1)) !important; }
    .play-btn { background: linear-gradient(135deg, rgba(${r},${g},${b},1), rgba(${Math.round(r*0.7)},${Math.round(g*0.7)},${Math.round(b*0.7)},1)) !important; }
    .progress-fill, .bar { background: linear-gradient(90deg, rgba(${r},${g},${b},1), rgba(${r},${g},${b},0.5)) !important; }
    .ctrl-btn { color: rgba(${r},${g},${b},0.9) !important; }
    .config-tab.active, .tab-btn.active, .log-tab.active { color: rgba(${r},${g},${b},1) !important; border-color: rgba(${r},${g},${b},0.4) !important; }
    .pl-item.active, .playlist-item.active { color: rgba(${r},${g},${b},1) !important; }
  `

  localStorage.setItem(STORAGE_KEY, JSON.stringify(theme.value))
}

function applyPreset(p: typeof colorPresets[0]) {
  theme.value.primary = p.primary
  // 同步 HSL 状态
  const rgb = hexToRgb(p.primary)
  const hsl = rgbToHsl(rgb.r, rgb.g, rgb.b)
  hueVal.value = hsl.h
  satVal.value = hsl.s
  lightVal.value = hsl.l
  drawHueRing()
  drawSLSquare()
  applyTheme()
}

// ── HSL 色盘 ──────────────────────────────────────────
const hueCanvas = ref<HTMLCanvasElement | null>(null)
const slCanvas = ref<HTMLCanvasElement | null>(null)
const hueVal = ref(210)   // 0-360
const satVal = ref(100)   // 0-100
const lightVal = ref(65)  // 0-100

function hslToHex(h: number, s: number, l: number): string {
  s /= 100; l /= 100
  const k = (n: number) => (n + h / 30) % 12
  const a = s * Math.min(l, 1 - l)
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
  const toHex = (x: number) => Math.round(x * 255).toString(16).padStart(2, '0')
  return `#${toHex(f(0))}${toHex(f(8))}${toHex(f(4))}`
}

function rgbToHsl(r: number, g: number, b: number): { h: number; s: number; l: number } {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return { h: 0, s: 0, l: Math.round(l * 100) }
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h = 0
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6
  else if (max === g) h = ((b - r) / d + 2) / 6
  else h = ((r - g) / d + 4) / 6
  return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) }
}

function drawHueRing() {
  const c = hueCanvas.value?.getContext('2d')
  if (!c || !hueCanvas.value) return
  const cx = 70, cy = 70, outerR = 66, innerR = 48
  c.clearRect(0, 0, 140, 140)
  for (let deg = 0; deg < 360; deg++) {
    const startA = (deg - 1) * Math.PI / 180
    const endA = (deg + 1) * Math.PI / 180
    c.beginPath()
    c.arc(cx, cy, outerR, startA, endA)
    c.arc(cx, cy, innerR, endA, startA, true)
    c.closePath()
    c.fillStyle = `hsl(${deg}, 100%, 50%)`
    c.fill()
  }
}

function drawSLSquare() {
  const c = slCanvas.value?.getContext('2d')
  if (!c || !slCanvas.value) return
  const w = 70
  c.clearRect(0, 0, w, w)
  const gradH = c.createLinearGradient(0, 0, w, 0)
  gradH.addColorStop(0, '#ffffff')
  gradH.addColorStop(1, `hsl(${hueVal.value}, 100%, 50%)`)
  c.fillStyle = gradH
  c.fillRect(0, 0, w, w)
  const gradV = c.createLinearGradient(0, 0, 0, w)
  gradV.addColorStop(0, 'rgba(0,0,0,0)')
  gradV.addColorStop(1, 'rgba(0,0,0,1)')
  c.fillStyle = gradV
  c.fillRect(0, 0, w, w)
}

const hueCursorStyle = computed(() => {
  const angle = hueVal.value * Math.PI / 180
  const r = 57
  const x = 70 + Math.cos(angle) * r - 6
  const y = 70 + Math.sin(angle) * r - 6
  return { left: x + 'px', top: y + 'px' }
})

const slCursorStyle = computed(() => {
  // SL 方块在 wheel-wrap 内偏移 35px（(140-70)/2）
  const x = 35 + (satVal.value / 100) * 70 - 5
  const y = 35 + (1 - lightVal.value / 100) * 70 - 5
  return { left: x + 'px', top: y + 'px' }
})

function updateFromHSL() {
  theme.value.primary = hslToHex(hueVal.value, satVal.value, lightVal.value)
  drawSLSquare()
  applyTheme()
}

function startHueDrag(e: MouseEvent) {
  const handle = (ev: MouseEvent) => {
    const rect = hueCanvas.value!.getBoundingClientRect()
    const cx = 70, cy = 70
    const x = ev.clientX - rect.left - cx
    const y = ev.clientY - rect.top - cy
    let deg = Math.atan2(y, x) * 180 / Math.PI
    if (deg < 0) deg += 360
    hueVal.value = Math.round(deg)
    updateFromHSL()
  }
  handle(e)
  const up = () => { window.removeEventListener('mousemove', handle); window.removeEventListener('mouseup', up) }
  window.addEventListener('mousemove', handle)
  window.addEventListener('mouseup', up)
}

function startSLDrag(e: MouseEvent) {
  const handle = (ev: MouseEvent) => {
    const rect = slCanvas.value!.getBoundingClientRect()
    let x = (ev.clientX - rect.left) / 70
    let y = (ev.clientY - rect.top) / 70
    x = Math.max(0, Math.min(1, x))
    y = Math.max(0, Math.min(1, y))
    satVal.value = Math.round(x * 100)
    lightVal.value = Math.round((1 - y) * 100)
    updateFromHSL()
  }
  handle(e)
  const up = () => { window.removeEventListener('mousemove', handle); window.removeEventListener('mouseup', up) }
  window.addEventListener('mousemove', handle)
  window.addEventListener('mouseup', up)
}

// ── 雪花系统 ──────────────────────────────────────────
const snowCanvas = ref<HTMLCanvasElement | null>(null)

interface Flake {
  x: number; y: number
  r: number          // 半径
  speed: number      // 下落速度
  drift: number      // 水平漂移幅度
  phase: number      // 漂移相位
  opacity: number
  rotation: number   // 当前旋转角度（弧度）
  rotSpeed: number   // 旋转速度（弧度/帧）
  type: 'fall' | 'burst'
  // burst 专用
  vx?: number; vy?: number; life?: number; maxLife?: number
}

let flakes: Flake[] = []
let animId = 0
let ctx: CanvasRenderingContext2D | null = null

function resize() {
  if (!snowCanvas.value) return
  snowCanvas.value.width  = window.innerWidth
  snowCanvas.value.height = window.innerHeight
}

// 雪花形状：六角星
function drawSnowflake(c: CanvasRenderingContext2D, x: number, y: number, r: number, opacity: number, rotation: number = 0) {
  c.save()
  c.globalAlpha = opacity
  c.strokeStyle = 'white'
  c.lineWidth = r * 0.18
  c.translate(x, y)
  c.rotate(rotation)
  for (let i = 0; i < 6; i++) {
    c.rotate(Math.PI / 3)
    c.beginPath()
    c.moveTo(0, 0)
    c.lineTo(0, r)
    // 小分支
    c.moveTo(0, r * 0.4)
    c.lineTo(r * 0.22, r * 0.62)
    c.moveTo(0, r * 0.4)
    c.lineTo(-r * 0.22, r * 0.62)
    c.stroke()
  }
  c.restore()
}

function initFallFlakes() {
  const count = 18
  flakes = Array.from({ length: count }, () => ({
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    r: 4 + Math.random() * 6,
    speed: 0.4 + Math.random() * 0.7,
    drift: 0.3 + Math.random() * 0.5,
    phase: Math.random() * Math.PI * 2,
    opacity: 0.25 + Math.random() * 0.35,
    rotation: Math.random() * Math.PI * 2,
    rotSpeed: (Math.random() - 0.5) * 0.03,  // 随机旋转速度，可正可负
    type: 'fall' as const,
  }))
}

function spawnBurst(cx: number, cy: number) {
  const count = 10 + Math.floor(Math.random() * 6)
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i) / count + Math.random() * 0.4
    const speed = 1.5 + Math.random() * 3
    flakes.push({
      x: cx, y: cy,
      r: 3 + Math.random() * 5,
      speed: 0, drift: 0, phase: 0,
      opacity: 0.8 + Math.random() * 0.2,
      rotation: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.08,  // 爆发雪花旋转更快
      type: 'burst',
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 0,
      maxLife: 40 + Math.random() * 30,
    })
  }
}

let t = 0
function animate() {
  animId = requestAnimationFrame(animate)
  if (!ctx || !snowCanvas.value) return
  ctx.clearRect(0, 0, snowCanvas.value.width, snowCanvas.value.height)
  t += 0.012

  const W = snowCanvas.value.width
  const H = snowCanvas.value.height

  flakes = flakes.filter(f => {
    if (f.type === 'fall') {
      f.y += f.speed
      f.x += Math.sin(t + f.phase) * f.drift
      f.rotation += f.rotSpeed  // 更新旋转角度
      if (f.y > H + f.r) { f.y = -f.r; f.x = Math.random() * W }
      if (f.x < -f.r) f.x = W + f.r
      if (f.x > W + f.r) f.x = -f.r
      drawSnowflake(ctx!, f.x, f.y, f.r, f.opacity, f.rotation)
      return true
    } else {
      // burst
      f.life! += 1
      const progress = f.life! / f.maxLife!
      f.x += f.vx! * (1 - progress * 0.6)
      f.y += f.vy! * (1 - progress * 0.6) + progress * 0.5  // 轻微重力
      f.rotation += f.rotSpeed * (1 - progress)  // 旋转逐渐减速
      const op = f.opacity * (1 - progress)
      if (op <= 0.01) return false
      drawSnowflake(ctx!, f.x, f.y, f.r * (1 - progress * 0.3), op, f.rotation)
      return true
    }
  })
}

function onClick(e: MouseEvent) {
  spawnBurst(e.clientX, e.clientY)
}

onMounted(() => {
  // 恢复主题
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) Object.assign(theme.value, JSON.parse(saved))
  } catch {}
  // 同步 HSL 色盘状态
  const rgb = hexToRgb(theme.value.primary)
  const hsl = rgbToHsl(rgb.r, rgb.g, rgb.b)
  hueVal.value = hsl.h
  satVal.value = hsl.s
  lightVal.value = hsl.l
  drawHueRing()
  drawSLSquare()
  applyTheme()

  if (!snowCanvas.value) return
  ctx = snowCanvas.value.getContext('2d')
  resize()
  initFallFlakes()
  animate()
  window.addEventListener('resize', resize)
  window.addEventListener('click', onClick)
})

onUnmounted(() => {
  cancelAnimationFrame(animId)
  window.removeEventListener('resize', resize)
  window.removeEventListener('click', onClick)
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

/* CSS 变量默认值 */
:root {
  --primary: #4a9eff;
  --primary-r: 74;
  --primary-g: 158;
  --primary-b: 255;
  --glass-opacity: 0.65;
  --glass-blur: 12px;
  --overlay-opacity: 0.85;
}

.app-root {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  position: relative;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* 背景图层 */
.bg-image {
  position: fixed;
  inset: 0;
  background: url('./assets/ygyz.jpg') center center / cover no-repeat;
  z-index: 0;
  transform: scale(1.05); /* 防止 blur 边缘露白 */
  transform-origin: center;
  transition: filter 0.3s ease;
}

/* 雪花 canvas */
.snow-canvas {
  position: fixed;
  inset: 0;
  z-index: 5;
  pointer-events: none;
}

/* 侧边栏 */
.sidebar {
  position: relative;
  z-index: 10;
  width: 180px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 24px 12px 16px;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-right: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.15);
  box-shadow: 2px 0 20px rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.08);
  animation: sidebar-in 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes sidebar-in {
  from { opacity: 0; transform: translateX(-24px); }
  to   { opacity: 1; transform: translateX(0); }
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 24px;
  animation: logo-in 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes logo-in {
  from { opacity: 0; transform: translateY(-10px); }
  to   { opacity: 1; transform: translateY(0); }
}

.logo-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary), rgba(var(--primary-r),var(--primary-g),var(--primary-b),0.4));
  box-shadow: 0 0 8px rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.6);
  flex-shrink: 0;
  animation: dot-pulse 2s ease-in-out infinite;
}
@keyframes dot-pulse {
  0%, 100% { box-shadow: 0 0 6px rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.5); }
  50%      { box-shadow: 0 0 14px rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.9); }
}

.logo-text {
  font-size: 17px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--primary), rgba(var(--primary-r),var(--primary-g),var(--primary-b),0.6));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: 0.5px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, box-shadow 0.2s, transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  color: #5a7a9a;
  font-size: 14px;
  font-family: inherit;
  text-align: left;
  width: 100%;
  /* 逐个弹入 */
  opacity: 0;
  animation: nav-pop-in 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes nav-pop-in {
  from { opacity: 0; transform: translateX(-16px) scale(0.92); }
  to   { opacity: 1; transform: translateX(0) scale(1); }
}

.nav-item:hover {
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.1);
  color: var(--primary);
  transform: scale(1.03);
}

.nav-item:active {
  transform: scale(0.97);
}

.nav-item.active {
  background: linear-gradient(135deg,
    rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.18),
    rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.08));
  color: var(--primary);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.25);
}

.nav-icon {
  font-size: 15px;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}

.nav-label { font-size: 14px; }

/* 主题面板 */
.theme-panel {
  border-top: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.1);
  padding-top: 8px;
  margin-bottom: 8px;
  animation: panel-in 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.35s both;
}
@keyframes panel-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.theme-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 14px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: #5a7a9a;
  font-size: 14px;
  font-family: inherit;
  transition: background 0.2s, transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.theme-toggle:hover {
  transform: scale(1.02);
}

.theme-toggle:hover {
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.08);
}

.toggle-arrow {
  margin-left: auto;
  font-size: 16px;
  transition: transform 0.2s;
  display: inline-block;
}
.toggle-arrow.open { transform: rotate(90deg); }

.theme-body {
  padding: 6px 10px 10px;
}

.theme-label {
  font-size: 10px;
  color: #a0b8cc;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.val-hint {
  font-size: 11px;
  color: var(--primary);
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
}

.color-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.color-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s;
  padding: 0;
}

.color-dot:hover { transform: scale(1.2); }
.color-dot.selected {
  border-color: white;
  box-shadow: 0 0 0 2px var(--primary);
  transform: scale(1.15);
}

.color-picker {
  width: 100%;
  height: 28px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  padding: 0;
  background: none;
}

/* HSL 色盘 */
.color-wheel-wrap {
  position: relative;
  width: 140px;
  height: 140px;
  margin: 4px auto 8px;
}
.hue-ring {
  position: absolute;
  top: 0; left: 0;
  width: 140px; height: 140px;
  cursor: crosshair;
}
.sl-square {
  position: absolute;
  top: 35px; left: 35px;
  width: 70px; height: 70px;
  border-radius: 4px;
  cursor: crosshair;
}
.wheel-cursor {
  position: absolute;
  width: 12px; height: 12px;
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 0 4px rgba(0,0,0,0.4);
  pointer-events: none;
}
.sl-cursor {
  position: absolute;
  width: 10px; height: 10px;
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 0 3px rgba(0,0,0,0.5);
  pointer-events: none;
}
.color-preview-row {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  margin-bottom: 6px;
}
.color-preview {
  width: 20px; height: 20px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.6);
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
}
.color-hex {
  font-size: 11px;
  font-family: 'Consolas', monospace;
  color: #5a7a9a;
}

.theme-slider {
  width: 100%;
  accent-color: var(--primary);
  cursor: pointer;
  height: 4px;
}

.sidebar-footer {
  font-size: 11px;
  color: #a0b8cc;
  text-align: center;
  padding-top: 12px;
  border-top: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.1);
  letter-spacing: 0.3px;
  animation: panel-in 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.45s both;
}

/* 主内容区 */
.main-content {
  position: relative;
  z-index: 10;
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
}

.main-content::-webkit-scrollbar { width: 6px; }
.main-content::-webkit-scrollbar-track { background: transparent; }
.main-content::-webkit-scrollbar-thumb {
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.25);
  border-radius: 3px;
}
.main-content::-webkit-scrollbar-thumb:hover {
  background: rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.45);
}

/* 全局卡片 */
.glass-card {
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.12);
  border-radius: 14px;
  box-shadow: 0 4px 24px rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.06);
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a4a7a;
  margin-bottom: 20px;
  letter-spacing: 0.3px;
}

/* ── 顶部加载条 ── */
.route-loading-bar {
  position: fixed;
  top: 0;
  left: 0;
  width: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--primary), rgba(var(--primary-r), var(--primary-g), var(--primary-b), 0.4));
  z-index: 9999;
  transition: width 0.3s ease, opacity 0.2s;
  opacity: 0;
  pointer-events: none;
}
.route-loading-bar.active {
  width: 80%;
  opacity: 1;
  animation: loading-shimmer 1s ease-in-out infinite;
}
@keyframes loading-shimmer {
  0%   { width: 0;    opacity: 1; }
  50%  { width: 60%;  opacity: 1; }
  100% { width: 80%;  opacity: 0.6; }
}

/* ── 页面切换动画 ── */
.page-enter-active {
  transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform, opacity;
}
.page-leave-active {
  transition: all 0.2s cubic-bezier(0.55, 0, 1, 0.45);
  will-change: transform, opacity;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
