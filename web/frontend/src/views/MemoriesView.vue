<template>
  <div>
    <div class="page-title">记忆管理</div>

    <div class="glass-card toolbar">
      <select v-model="filterUserId" class="filter-select" @change="handleFilter">
        <option value="">全部用户</option>
        <option v-for="u in userOptions" :key="u.value" :value="u.value">{{ u.label }}</option>
      </select>
      <input
        v-model="filterKeyword"
        class="filter-input"
        placeholder="搜索关键词..."
        @keyup.enter="handleFilter"
      />
      <button class="btn-primary" @click="handleFilter">搜索</button>
      <span class="total-hint">共 {{ total }} 条</span>
    </div>

    <div class="glass-card table-wrap">
      <div v-if="loading" class="table-loading">加载中...</div>
      <table v-else class="mem-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户</th>
            <th>时间</th>
            <th>重要性</th>
            <th>用户说</th>
            <th>小雫回复</th>
            <th>关键词</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="td-id">{{ row.id }}</td>
            <td class="td-user">{{ row.nickname || row.user_id }}</td>
            <td class="td-time">{{ row.created_at_str }}</td>
            <td class="td-imp">
              <span class="imp-badge" :class="row.importance >= 0.7 ? 'imp-high' : ''">
                {{ row.importance?.toFixed(2) }}
              </span>
            </td>
            <td class="td-text">{{ row.user_text }}</td>
            <td class="td-text">{{ row.bot_text }}</td>
            <td class="td-kw">{{ row.keywords }}</td>
            <td class="td-action">
              <button class="btn-del" @click="handleDelete(row.id)">删除</button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="8" class="td-empty">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pagination">
      <button class="page-btn" :disabled="page <= 1" @click="page--; load()">‹</button>
      <span class="page-info">{{ page }} / {{ pageCount || 1 }}</span>
      <button class="page-btn" :disabled="page >= pageCount" @click="page++; load()">›</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { getMemories, deleteMemory, getMemoryUsers } from '@/api'

const loading = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pageCount = computed(() => Math.ceil(total.value / pageSize.value))
const filterUserId = ref('')
const filterKeyword = ref('')
const userOptions = ref<{ label: string; value: string }[]>([])
const message = useMessage()

async function load() {
  loading.value = true
  try {
    const res = await getMemories({
      page: page.value,
      page_size: pageSize.value,
      user_id: filterUserId.value || undefined,
      keyword: filterKeyword.value || undefined,
    })
    rows.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleFilter() {
  page.value = 1
  load()
}

async function handleDelete(id: number) {
  if (!confirm('确认删除这条记忆？')) return
  await deleteMemory(id)
  message.success('已删除')
  load()
}

onMounted(async () => {
  const res = await getMemoryUsers()
  userOptions.value = res.data.map((u: any) => ({
    label: `${u.nickname || u.user_id} (${u.count})`,
    value: u.user_id,
  }))
  load()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.filter-select, .filter-input {
  padding: 7px 12px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: rgba(255, 255, 255, 0.6);
  color: #2a4a6a;
  font-size: 13px;
  outline: none;
  font-family: inherit;
}

.filter-input { width: 200px; }
.filter-select { width: 160px; }

.filter-input:focus, .filter-select:focus {
  border-color: rgba(74, 158, 255, 0.5);
}

.btn-primary {
  padding: 7px 16px;
  border-radius: 7px;
  border: none;
  background: linear-gradient(135deg, #4a9eff, #2d7dd2);
  color: white;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}

.total-hint {
  font-size: 12px;
  color: #7a9ab8;
  margin-left: auto;
}

.table-wrap {
  padding: 0;
  overflow: hidden;
  margin-bottom: 12px;
}

.table-loading {
  padding: 40px;
  text-align: center;
  color: #7a9ab8;
}

.mem-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.mem-table th {
  padding: 10px 12px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: #5a7a9a;
  background: rgba(74, 158, 255, 0.05);
  border-bottom: 1px solid rgba(74, 158, 255, 0.1);
  white-space: nowrap;
}

.mem-table td {
  padding: 9px 12px;
  border-bottom: 1px solid rgba(74, 158, 255, 0.06);
  color: #2a4a6a;
  vertical-align: top;
}

.mem-table tr:last-child td { border-bottom: none; }
.mem-table tr:hover td { background: rgba(74, 158, 255, 0.03); }

.td-id { color: #a0b8cc; width: 50px; }
.td-user { white-space: nowrap; width: 90px; }
.td-time { white-space: nowrap; width: 140px; font-size: 12px; color: #7a9ab8; }
.td-imp { width: 70px; }
.td-text { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td-kw { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: #7a9ab8; }
.td-action { width: 60px; }
.td-empty { text-align: center; color: #a0b8cc; padding: 40px; }

.imp-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(74, 158, 255, 0.1);
  color: #2d7dd2;
}

.imp-badge.imp-high {
  background: rgba(255, 149, 0, 0.12);
  color: #c07000;
}

.btn-del {
  padding: 3px 10px;
  border-radius: 5px;
  border: 1px solid rgba(220, 50, 50, 0.2);
  background: transparent;
  color: #c0392b;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.btn-del:hover {
  background: rgba(220, 50, 50, 0.08);
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.page-btn {
  width: 32px;
  height: 32px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: rgba(255, 255, 255, 0.5);
  color: #2d7dd2;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.page-btn:not(:disabled):hover { background: rgba(74, 158, 255, 0.1); }

.page-info {
  font-size: 13px;
  color: #5a7a9a;
  min-width: 60px;
  text-align: center;
}
</style>
