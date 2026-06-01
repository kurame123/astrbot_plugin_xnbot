<template>
  <div>
    <div class="page-title">图谱浏览</div>

    <div class="tab-bar glass-card">
      <button class="tab-btn" :class="{ active: tab === 'entities' }" @click="tab = 'entities'">实体</button>
      <button class="tab-btn" :class="{ active: tab === 'relations' }" @click="tab = 'relations'">关系</button>
    </div>

    <!-- 实体 -->
    <div v-if="tab === 'entities'">
      <div class="glass-card toolbar">
        <input v-model="entityKeyword" class="filter-input" placeholder="搜索实体名称或摘要..." @keyup.enter="loadEntities" />
        <button class="btn-primary" @click="loadEntities">搜索</button>
        <span class="total-hint">共 {{ entityTotal }} 个</span>
      </div>
      <div class="glass-card table-wrap">
        <div v-if="entityLoading" class="table-loading">加载中...</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>ID</th><th>名称</th><th>类型</th><th>摘要</th><th>用户</th><th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in entities" :key="e.id">
              <td class="td-id">{{ e.id }}</td>
              <td><span class="entity-name">{{ e.name }}</span></td>
              <td><span class="type-badge">{{ e.entity_type }}</span></td>
              <td class="td-text">{{ e.summary }}</td>
              <td class="td-user">{{ e.user_id }}</td>
              <td class="td-time">{{ e.created_at }}</td>
            </tr>
            <tr v-if="!entities.length"><td colspan="6" class="td-empty">暂无数据</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <button class="page-btn" :disabled="entityPage <= 1" @click="entityPage--; loadEntities()">‹</button>
        <span class="page-info">{{ entityPage }} / {{ entityPageCount || 1 }}</span>
        <button class="page-btn" :disabled="entityPage >= entityPageCount" @click="entityPage++; loadEntities()">›</button>
      </div>
    </div>

    <!-- 关系 -->
    <div v-if="tab === 'relations'">
      <div class="glass-card toolbar">
        <span class="total-hint">共 {{ relationTotal }} 条</span>
      </div>
      <div class="glass-card table-wrap">
        <div v-if="relationLoading" class="table-loading">加载中...</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>源实体</th><th>关系类型</th><th>目标实体</th><th>描述</th><th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in relations" :key="i">
              <td><span class="entity-name">{{ r.from }}</span></td>
              <td><span class="rel-badge">{{ r.rel_type }}</span></td>
              <td><span class="entity-name">{{ r.to }}</span></td>
              <td class="td-text">{{ r.description }}</td>
              <td class="td-time">{{ r.created_at }}</td>
            </tr>
            <tr v-if="!relations.length"><td colspan="5" class="td-empty">暂无数据</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <button class="page-btn" :disabled="relationPage <= 1" @click="relationPage--; loadRelations()">‹</button>
        <span class="page-info">{{ relationPage }} / {{ relationPageCount || 1 }}</span>
        <button class="page-btn" :disabled="relationPage >= relationPageCount" @click="relationPage++; loadRelations()">›</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getEntities, getRelations } from '@/api'

const tab = ref('entities')

const entityLoading = ref(false)
const entities = ref<any[]>([])
const entityTotal = ref(0)
const entityPage = ref(1)
const entityPageSize = 20
const entityPageCount = computed(() => Math.ceil(entityTotal.value / entityPageSize))
const entityKeyword = ref('')

async function loadEntities() {
  entityLoading.value = true
  try {
    const res = await getEntities({ page: entityPage.value, page_size: entityPageSize, keyword: entityKeyword.value || undefined })
    entities.value = res.data.items
    entityTotal.value = res.data.total
  } finally {
    entityLoading.value = false
  }
}

const relationLoading = ref(false)
const relations = ref<any[]>([])
const relationTotal = ref(0)
const relationPage = ref(1)
const relationPageSize = 20
const relationPageCount = computed(() => Math.ceil(relationTotal.value / relationPageSize))

async function loadRelations() {
  relationLoading.value = true
  try {
    const res = await getRelations({ page: relationPage.value, page_size: relationPageSize })
    relations.value = res.data.items
    relationTotal.value = res.data.total
  } finally {
    relationLoading.value = false
  }
}

onMounted(() => { loadEntities(); loadRelations() })
</script>

<style scoped>
.tab-bar {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
}

.tab-btn {
  padding: 7px 20px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: transparent;
  color: #5a7a9a;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.tab-btn.active {
  background: linear-gradient(135deg, rgba(74, 158, 255, 0.18), rgba(168, 212, 255, 0.12));
  color: #1a6bc4;
  font-weight: 600;
  border-color: rgba(74, 158, 255, 0.4);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: 12px;
}

.filter-input {
  padding: 7px 12px;
  border-radius: 7px;
  border: 1px solid rgba(74, 158, 255, 0.2);
  background: rgba(255, 255, 255, 0.6);
  color: #2a4a6a;
  font-size: 13px;
  outline: none;
  width: 240px;
  font-family: inherit;
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

.table-loading, .td-empty {
  padding: 40px;
  text-align: center;
  color: #7a9ab8;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th {
  padding: 10px 12px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: #5a7a9a;
  background: rgba(74, 158, 255, 0.05);
  border-bottom: 1px solid rgba(74, 158, 255, 0.1);
  white-space: nowrap;
}

.data-table td {
  padding: 9px 12px;
  border-bottom: 1px solid rgba(74, 158, 255, 0.06);
  color: #2a4a6a;
  vertical-align: top;
}

.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: rgba(74, 158, 255, 0.03); }

.td-id { color: #a0b8cc; width: 50px; }
.td-user { white-space: nowrap; width: 100px; font-size: 12px; color: #7a9ab8; }
.td-time { white-space: nowrap; width: 140px; font-size: 12px; color: #7a9ab8; }
.td-text { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.entity-name {
  font-weight: 500;
  color: #1a6bc4;
}

.type-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(74, 158, 255, 0.1);
  color: #2d7dd2;
  white-space: nowrap;
}

.rel-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(168, 85, 247, 0.1);
  color: #7c3aed;
  white-space: nowrap;
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
