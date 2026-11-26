<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const examples = [
  '2026-11 华东成交单量是多少？',
  '2026-11 华东订单总数是多少？',
  '2026-11 全国净销售额是多少？',
]
const statusLabels = {
  QUEUED: '已接受问题',
  RUNNING: '正在检查口径与筛选条件',
  SUCCEEDED: '查询完成',
  CLARIFY: '需要补充条件',
  FAILED: '查询结束',
}
const terminal = new Set(['SUCCEEDED', 'CLARIFY', 'FAILED'])
const question = ref(examples[0])
const run = ref(null)
const events = ref([])
const network = ref('')
const submitting = ref(false)
const titleId = 'query-question'
let source
let pendingRequest
const storageKey = 'analytics-current-run'
const pendingKey = 'analytics-pending-request'

const busy = computed(() => submitting.value || (run.value && !terminal.has(run.value.status)))
const result = computed(() => run.value?.result)
const displayValue = computed(() =>
  new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(result.value?.value ?? 0)
)

async function read(response) {
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail || '请求失败，请重试')
  return body
}

function remember(view) {
  run.value = view
  sessionStorage.setItem(storageKey, view.id)
}

function subscribe(id) {
  source?.close()
  const stream = new EventSource('/api/runs/' + encodeURIComponent(id) + '/events')
  source = stream
  stream.onopen = () => { network.value = '' }
  stream.addEventListener('run', (event) => {
    if (source !== stream) return
    const view = JSON.parse(event.data)
    if (!events.value.some((step) => step.id === event.lastEventId)) {
      events.value.push({ id: event.lastEventId, status: view.status })
    }
    if (!terminal.has(run.value?.status) || terminal.has(view.status)) remember(view)
    if (terminal.has(view.status)) stream.close()
  })
  stream.onerror = () => {
    if (source === stream && !terminal.has(run.value?.status)) {
      network.value = '连接已断开，正在重新连接…'
    }
  }
}

async function submit() {
  const input = question.value.trim()
  if (!input || busy.value) return
  if (pendingRequest?.question !== input) {
    pendingRequest = { key: crypto.randomUUID(), question: input }
    sessionStorage.setItem(pendingKey, JSON.stringify(pendingRequest))
  }
  submitting.value = true
  network.value = ''
  events.value = []
  source?.close()
  try {
    const view = await read(await fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': pendingRequest.key },
      body: JSON.stringify({ question: input }),
    }))
    remember(view)
    pendingRequest = null
    sessionStorage.removeItem(pendingKey)
    subscribe(view.id)
  } catch (error) {
    network.value = error.message
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    pendingRequest = JSON.parse(sessionStorage.getItem(pendingKey) || 'null')
    if (pendingRequest) question.value = pendingRequest.question
  } catch {
    sessionStorage.removeItem(pendingKey)
  }
  const id = sessionStorage.getItem(storageKey)
  if (!id) return
  submitting.value = true
  try {
    remember(await read(await fetch('/api/runs/' + encodeURIComponent(id))))
    subscribe(id)
  } catch {
    sessionStorage.removeItem(storageKey)
  } finally {
    submitting.value = false
  }
})
onUnmounted(() => source?.close())
</script>

<template>
  <main class="page">
    <header class="page-header">
      <p class="context">商业分析 / 模拟数据</p>
      <h1>经营问数工作台</h1>
      <p>按月份和区域查询订单与营收，核对结果采用的指标口径。</p>
    </header>

    <section class="card">
      <form @submit.prevent="submit">
        <label :for="titleId">输入业务问题</label>
        <div class="input-row">
          <input :id="titleId" v-model="question" maxlength="400"
            placeholder="例如 2026-11 华东成交单量" required />
          <button class="primary" :disabled="busy">{{ busy ? '处理中…' : '查询指标' }}</button>
        </div>
      </form>
      <div class="examples" aria-label="示例问题">
        <button v-for="example in examples" :key="example" type="button" @click="question = example">
          {{ example }}
        </button>
      </div>
      <p v-if="network" class="notice" role="status">{{ network }}</p>
    </section>

    <div class="grid">
      <section class="card result-card" aria-live="polite">
        <h2>查询结果</h2>
        <template v-if="result">
          <p class="metric-label">{{ result.label }}</p>
          <p class="metric"><strong>{{ displayValue }}</strong> <span>{{ result.unit }}</span></p>
          <dl class="metadata">
            <div><dt>期间</dt><dd>{{ result.month }}</dd></div>
            <div><dt>区域</dt><dd>{{ result.region }}</dd></div>
            <div><dt>数据来源</dt><dd>{{ result.source === 'cache' ? 'Redis 缓存' : '数据库' }}</dd></div>
          </dl>
          <p class="definition">{{ result.reason }}</p>
          <p v-if="result.modelNote" class="model-note">模型辅助说明 · {{ result.modelNote }}</p>
        </template>
        <p v-else class="empty">{{ run?.message || (busy ? '正在处理问题。' : '提交问题后在这里查看指标。') }}</p>
      </section>

      <section class="card">
        <h2>处理进度</h2>
        <ol v-if="events.length" class="timeline" aria-live="polite">
          <li v-for="event in events" :key="event.id">{{ statusLabels[event.status] }}</li>
        </ol>
        <p v-else class="empty">{{ run ? statusLabels[run.status] : '等待查询' }}</p>
        <p v-if="run" class="trace">任务编号<br /><code>{{ run.id }}</code></p>
      </section>
    </div>
  </main>
</template>
