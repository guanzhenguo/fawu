<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, rows, type Page, type User } from './api'

interface TemplateVersion {
  id: string
  version: string
  status: string
  template_name: string
  template_label?: string
  template_clauses: Array<{ clause_code: string; content: string }>
}

interface Contract {
  id: string
  code: string
  title: string
  counterparty: string
  status: string
  risk_level: string
  template_version: string
  template_label: string
  created_at: string
  versions: Array<{ id: string; version_no: number }>
}

interface Finding {
  id: string
  severity: string
  title: string
  detail: string
  clause_code: string
}

interface Task {
  id: string
  name: string
  role_code: string
  status: string
  contract_code: string
  contract_title: string
}

interface Review {
  id: string
  contract_code: string
  contract_title: string
  risk_level: string
  status: string
  summary: string
  findings: Finding[]
  tasks: Task[]
  created_at: string
}

const token = ref(localStorage.getItem('fawu_token') || '')
const user = ref<User | null>(null)
const active = ref('dashboard')
const loading = ref(false)
const loginForm = reactive({ username: '', password: '' })
const contracts = ref<Contract[]>([])
const reviews = ref<Review[]>([])
const tasks = ref<Task[]>([])
const templateVersions = ref<TemplateVersion[]>([])
const showContractDialog = ref(false)
const contractForm = reactive({ code: '', title: '', counterparty: '', template_version: '', amount: '' })

const stats = computed(() => ({
  total: contracts.value.length,
  reviewing: contracts.value.filter((item) => item.status === 'IN_REVIEW').length,
  approved: contracts.value.filter((item) => item.status === 'APPROVED').length,
  pending: tasks.value.filter((item) => item.status === 'PENDING').length,
}))

const statusLabel: Record<string, string> = {
  DRAFT: '草稿', IN_REVIEW: '审核中', APPROVED: '已通过', REJECTED: '已驳回',
  SIGNED: '已签署', ARCHIVED: '已归档', PENDING: '待处理', COMPLETED: '已完成',
  CANCELLED: '已取消', PUBLISHED: '已发布', RETIRED: '已停用',
}

const riskLabel: Record<string, string> = { LOW: '低风险', MEDIUM: '中风险', HIGH: '高风险' }
const riskType = (value: string) => value === 'HIGH' ? 'danger' : value === 'MEDIUM' ? 'warning' : 'success'

async function login() {
  try {
    const result = await api<{ token: string; user: User }>('/auth/login/', {
      method: 'POST', body: JSON.stringify(loginForm),
    })
    token.value = result.token
    user.value = result.user
    localStorage.setItem('fawu_token', result.token)
    await loadAll()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  }
}

async function logout() {
  try { await api('/auth/logout/', { method: 'POST' }) } catch { /* token may already be invalid */ }
  localStorage.removeItem('fawu_token')
  token.value = ''
  user.value = null
}

async function loadAll() {
  loading.value = true
  try {
    const [me, contractPage, reviewPage, taskPage, versionPage] = await Promise.all([
      api<User>('/auth/me/'),
      api<Page<Contract>>('/contracts/?page_size=100'),
      api<Page<Review>>('/reviews/?page_size=100'),
      api<Page<Task>>('/approval-tasks/?page_size=100'),
      api<Page<TemplateVersion>>('/template-versions/?page_size=100'),
    ])
    user.value = me
    contracts.value = rows(contractPage)
    reviews.value = rows(reviewPage)
    tasks.value = rows(taskPage)
    templateVersions.value = rows(versionPage).filter((item) => item.status === 'PUBLISHED')
  } catch (error) {
    if (token.value) ElMessage.error(error instanceof Error ? error.message : '数据加载失败')
  } finally {
    loading.value = false
  }
}

async function createContract() {
  try {
    await api('/contracts/', {
      method: 'POST',
      body: JSON.stringify({ ...contractForm, amount: contractForm.amount || null }),
    })
    showContractDialog.value = false
    Object.assign(contractForm, { code: '', title: '', counterparty: '', template_version: '', amount: '' })
    ElMessage.success('合同已创建')
    await loadAll()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建失败')
  }
}

async function submitBaseline(contract: Contract) {
  const template = templateVersions.value.find((item) => item.id === contract.template_version)
  if (!template) return ElMessage.error('未找到合同使用的模板版本')
  try {
    await ElMessageBox.confirm('将按模板基线生成合同版本并立即提交审核。', '提交审核')
    const version = await api<{ id: string }>(`/contracts/${contract.id}/versions/`, {
      method: 'POST',
      body: JSON.stringify({
        snapshot: {
          variables: {},
          clauses: template.template_clauses.map((item) => ({
            code: item.clause_code, content: item.content,
          })),
        },
      }),
    })
    await api(`/contract-versions/${version.id}/submit/`, { method: 'POST', body: '{}' })
    ElMessage.success('已提交，未偏离模板的合同将自动通过')
    await loadAll()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '提交失败')
  }
}

async function decide(task: Task, decision: 'APPROVED' | 'REJECTED') {
  try {
    const { value } = await ElMessageBox.prompt('请输入审批意见', decision === 'APPROVED' ? '通过' : '驳回', {
      inputValue: decision === 'APPROVED' ? '同意' : '',
    })
    await api(`/approval-tasks/${task.id}/decide/`, {
      method: 'POST', body: JSON.stringify({ decision, comment: value }),
    })
    ElMessage.success('审批已处理')
    await loadAll()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '审批失败')
  }
}

onMounted(async () => {
  if (token.value) await loadAll()
})
</script>

<template>
  <div v-if="!token" class="login-page">
    <section class="login-brand">
      <div class="brand-mark">法</div>
      <p class="eyebrow">FAWU · CONTRACT INTELLIGENCE</p>
      <h1>让每一次签署<br><span>有据可循</span></h1>
      <p>从标准条款、风险审查到履约归档，把企业法务经验沉淀为可追溯的数字资产。</p>
    </section>
    <el-card class="login-card" shadow="never">
      <p class="eyebrow">欢迎回来</p>
      <h2>登录合同管理平台</h2>
      <el-form label-position="top" @submit.prevent="login">
        <el-form-item label="用户名"><el-input v-model="loginForm.username" size="large" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="loginForm.password" type="password" show-password size="large" /></el-form-item>
        <el-button type="primary" size="large" native-type="submit" class="wide">进入工作台</el-button>
      </el-form>
      <p class="login-tip">首次使用请由管理员在 Django Admin 创建账户。</p>
    </el-card>
  </div>

  <div v-else class="shell" v-loading="loading">
    <aside class="sidebar">
      <div class="logo"><span>法</span><strong>FAWU</strong></div>
      <nav>
        <button :class="{ active: active === 'dashboard' }" @click="active = 'dashboard'">总览</button>
        <button :class="{ active: active === 'contracts' }" @click="active = 'contracts'">合同管理</button>
        <button :class="{ active: active === 'reviews' }" @click="active = 'reviews'">风险审查</button>
        <button :class="{ active: active === 'tasks' }" @click="active = 'tasks'">审批任务</button>
        <button :class="{ active: active === 'templates' }" @click="active = 'templates'">模板中心</button>
      </nav>
      <div class="sidebar-foot"><small>{{ user?.name }}</small><button @click="logout">退出登录</button></div>
    </aside>

    <main>
      <header><div><p class="eyebrow">合同全生命周期</p><h2>{{ active === 'dashboard' ? '工作台总览' : active === 'contracts' ? '合同管理' : active === 'reviews' ? '风险审查' : active === 'tasks' ? '审批任务' : '模板中心' }}</h2></div><span class="date">规则版本 · 2026.09.1</span></header>

      <template v-if="active === 'dashboard'">
        <section class="hero"><div><p>今日工作台</p><h1>把风险挡在签署之前。</h1><span>系统依据发布时的模板基线进行确定性比对，所有审批动作进入不可变审计链。</span></div><div class="hero-seal">审<br>慎</div></section>
        <section class="stats">
          <article><span>合同总数</span><strong>{{ stats.total }}</strong></article>
          <article><span>审核中</span><strong>{{ stats.reviewing }}</strong></article>
          <article><span>已审核</span><strong>{{ stats.approved }}</strong></article>
          <article class="accent"><span>我的待办</span><strong>{{ stats.pending }}</strong></article>
        </section>
        <section class="panel"><div class="panel-head"><h3>最近合同</h3><button @click="active = 'contracts'">查看全部 →</button></div><el-table :data="contracts.slice(0, 6)"><el-table-column prop="code" label="编号" /><el-table-column prop="title" label="合同名称" /><el-table-column prop="counterparty" label="相对方" /><el-table-column label="状态"><template #default="scope"><el-tag effect="plain">{{ statusLabel[scope.row.status] }}</el-tag></template></el-table-column></el-table></section>
      </template>

      <template v-else-if="active === 'contracts'">
        <section class="panel"><div class="panel-head"><div><h3>合同清单</h3><p>起草、提交和跟踪合同审核状态</p></div><el-button type="primary" @click="showContractDialog = true">新建合同</el-button></div>
          <el-table :data="contracts"><el-table-column prop="code" label="编号" width="140" /><el-table-column prop="title" label="合同名称" min-width="180" /><el-table-column prop="counterparty" label="相对方" /><el-table-column prop="template_label" label="模板基线" /><el-table-column label="风险" width="100"><template #default="scope"><el-tag v-if="scope.row.risk_level" :type="riskType(scope.row.risk_level)" effect="light">{{ riskLabel[scope.row.risk_level] }}</el-tag><span v-else>—</span></template></el-table-column><el-table-column label="状态" width="100"><template #default="scope">{{ statusLabel[scope.row.status] }}</template></el-table-column><el-table-column label="操作" width="130"><template #default="scope"><el-button v-if="['DRAFT','REJECTED'].includes(scope.row.status)" link type="primary" @click="submitBaseline(scope.row)">按基线提交</el-button></template></el-table-column></el-table>
        </section>
      </template>

      <template v-else-if="active === 'reviews'">
        <section class="review-grid"><article v-for="review in reviews" :key="review.id" class="review-card"><div class="review-top"><div><small>{{ review.contract_code }}</small><h3>{{ review.contract_title }}</h3></div><el-tag :type="riskType(review.risk_level)">{{ riskLabel[review.risk_level] }}</el-tag></div><p>{{ review.summary }}</p><div v-if="review.findings.length" class="findings"><div v-for="finding in review.findings" :key="finding.id"><strong>{{ finding.clause_code || '字段规则' }} · {{ finding.title }}</strong><span>{{ finding.detail }}</span></div></div><footer>{{ statusLabel[review.status] }} · {{ new Date(review.created_at).toLocaleString() }}</footer></article><el-empty v-if="!reviews.length" description="暂无审查记录" /></section>
      </template>

      <template v-else-if="active === 'tasks'">
        <section class="panel"><div class="panel-head"><div><h3>审批任务</h3><p>只有任务指定人员、角色成员或管理员可以处理</p></div></div><el-table :data="tasks"><el-table-column prop="contract_code" label="合同编号" /><el-table-column prop="contract_title" label="合同名称" /><el-table-column prop="name" label="审批节点" /><el-table-column prop="role_code" label="角色" /><el-table-column label="状态"><template #default="scope">{{ statusLabel[scope.row.status] }}</template></el-table-column><el-table-column label="操作" width="160"><template #default="scope"><template v-if="scope.row.status === 'PENDING'"><el-button link type="primary" @click="decide(scope.row, 'APPROVED')">通过</el-button><el-button link type="danger" @click="decide(scope.row, 'REJECTED')">驳回</el-button></template></template></el-table-column></el-table></section>
      </template>

      <template v-else>
        <section class="panel"><div class="panel-head"><div><h3>已发布模板</h3><p>模板详细配置与发布目前由管理员后台维护</p></div><a class="admin-link" href="http://localhost:8000/admin/" target="_blank">打开管理后台 ↗</a></div><div class="template-grid"><article v-for="item in templateVersions" :key="item.id"><span>生效中</span><h3>{{ item.template_name }}</h3><p>版本 v{{ item.version }} · {{ item.template_clauses.length }} 个条款</p><small>基线 ID {{ item.id.slice(0, 8) }}</small></article></div><el-empty v-if="!templateVersions.length" description="暂无已发布模板" /></section>
      </template>
    </main>

    <el-dialog v-model="showContractDialog" title="新建合同" width="520px"><el-form label-position="top"><div class="form-row"><el-form-item label="合同编号"><el-input v-model="contractForm.code" placeholder="例如 HT-2026-001" /></el-form-item><el-form-item label="合同金额"><el-input v-model="contractForm.amount" placeholder="可选" /></el-form-item></div><el-form-item label="合同名称"><el-input v-model="contractForm.title" /></el-form-item><el-form-item label="合同相对方"><el-input v-model="contractForm.counterparty" /></el-form-item><el-form-item label="模板基线"><el-select v-model="contractForm.template_version" class="wide"><el-option v-for="item in templateVersions" :key="item.id" :label="`${item.template_name} v${item.version}`" :value="item.id" /></el-select></el-form-item></el-form><template #footer><el-button @click="showContractDialog = false">取消</el-button><el-button type="primary" @click="createContract">创建合同</el-button></template></el-dialog>
  </div>
</template>
