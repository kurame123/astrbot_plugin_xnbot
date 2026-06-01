import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  // 生产环境挂载在 /web/app 下，base 要对齐
  history: createWebHistory('/web/app/'),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/memories', name: 'memories', component: () => import('@/views/MemoriesView.vue') },
    { path: '/graph', name: 'graph', component: () => import('@/views/GraphView.vue') },
    { path: '/config', name: 'config', component: () => import('@/views/ConfigView.vue') },
    { path: '/logs', name: 'logs', component: () => import('@/views/LogsView.vue') },
    { path: '/xn_core', name: 'xn_core', component: () => import('@/views/XN_CoreView.vue') },
  ],
})

export default router
