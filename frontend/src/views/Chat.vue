<template>
  <div class="chat-shell">
    <aside class="sidebar" :class="{ open: sidebarOpen }">
      <div class="sidebar-header">
        <span class="sidebar-title">我的对话</span>
        <van-button size="mini" type="primary" @click="createNewConversation">新建</van-button>
      </div>
      <div class="conversation-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          :class="['conversation-item', { active: conv.id === activeId }]"
          @click="selectConversation(conv.id)"
        >
          <div class="conversation-title">{{ conv.title || '新对话' }}</div>
          <div class="conversation-actions" @click.stop>
            <van-icon name="edit" @click="renamePrompt(conv)" />
            <van-icon name="delete-o" @click="deletePrompt(conv)" />
          </div>
        </div>
        <div v-if="!conversations.length" class="empty-tip">还没有对话，点击右上"新建"开始</div>
      </div>
      <div class="sidebar-footer">
        <div class="edu-status">
          <template v-if="eduLoggedIn">
            <span class="edu-tag online">📚 教务已登录 {{ eduUserid }}</span>
            <van-button size="mini" plain @click="handleEduLogout">退出教务</van-button>
          </template>
          <template v-else>
            <van-button size="mini" type="primary" plain @click="openEduLogin">📚 登录教务</van-button>
          </template>
        </div>
        <div class="account-row">
          <span class="username">{{ username }}</span>
          <van-button size="mini" plain @click="logout">登出</van-button>
        </div>
      </div>
    </aside>

    <div v-if="sidebarOpen" class="sidebar-mask" @click="sidebarOpen = false"></div>

    <div class="page chat-page">
      <van-nav-bar :title="activeTitle">
        <template #left>
          <van-icon name="bars" size="20" @click="sidebarOpen = !sidebarOpen" />
        </template>
        <template #right>
          <van-button size="mini" plain type="primary" @click="createNewConversation">+ 新对话</van-button>
        </template>
      </van-nav-bar>

      <main ref="messageListRef" class="messages">
        <section v-for="(message, index) in messages" :key="index" :class="['message-row', message.role]">
          <div class="bubble">
            <div class="bubble-text">{{ message.content }}</div>

            <div v-if="message.sources?.length" class="sources">
              <div class="sources-title">参考资料</div>
              <van-cell-group inset>
                <van-cell
                  v-for="source in message.sources.slice(0, 3)"
                  :key="source.title"
                  :title="source.title"
                  :label="source.content"
                />
              </van-cell-group>
            </div>
          </div>
        </section>

        <section v-if="loading" class="message-row assistant">
          <div class="bubble loading-bubble">
            <van-loading size="20" />
            <span>正在思考...</span>
          </div>
        </section>
      </main>

      <footer class="composer">
        <van-field
          v-model="input"
          class="composer-input"
          type="textarea"
          rows="1"
          autosize
          placeholder="问校园问题，或让我查 OA 通知"
          @keydown.enter.prevent="sendMessage"
        />
        <van-button round type="primary" :disabled="!input.trim() || loading" @click="sendMessage">发送</van-button>
      </footer>
    </div>

    <EduLoginDialog v-model:show="eduLoginVisible" @success="onEduLoginSuccess" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showFailToast, showToast } from 'vant'
import {
  chatWithAgent,
  checkHealth,
  createConversation,
  deleteConversation,
  eduLogout,
  eduStatus,
  getConversationMessages,
  listConversations,
  renameConversation,
  type Conversation,
  type ConversationMessage,
} from '../api/client'
import EduLoginDialog from './EduLoginDialog.vue'

const router = useRouter()
const username = ref(localStorage.getItem('username') || '')
const sidebarOpen = ref(false)

const conversations = ref<Conversation[]>([])
const activeId = ref<string | null>(null)
const messages = ref<ConversationMessage[]>([])
const input = ref('')
const loadingByConversation = ref<Record<string, boolean>>({})
const messageListRef = ref<HTMLElement | null>(null)

const eduLoginVisible = ref(false)
const eduLoggedIn = ref(false)
const eduUserid = ref('')

const loading = computed(() => {
  if (!activeId.value) return false
  return !!loadingByConversation.value[activeId.value]
})

const activeTitle = computed(() => {
  const conv = conversations.value.find((c) => c.id === activeId.value)
  return conv?.title || '吉大校园智能体'
})

const welcomeMessage: ConversationMessage = {
  role: 'assistant',
  content: '你好，我是吉大校园智能体。你可以问我校园卡、缓考、奖学金、大创等校园问题，也可以让我查 OA 通知。',
}

onMounted(async () => {
  try {
    await checkHealth()
  } catch {
    showFailToast('后端暂未连接，请先启动 FastAPI 服务')
  }
  await refreshConversations()
  await refreshEduStatus()
  if (conversations.value.length > 0) {
    await selectConversation(conversations.value[0].id)
  } else {
    messages.value = [welcomeMessage]
  }
})

async function refreshEduStatus() {
  try {
    const status = await eduStatus()
    eduLoggedIn.value = !!status.logged_in
    eduUserid.value = status.userid || ''
  } catch {
    eduLoggedIn.value = false
    eduUserid.value = ''
  }
}

function openEduLogin() {
  if (eduLoggedIn.value) return
  eduLoginVisible.value = true
}

async function handleEduLogout() {
  try {
    await showConfirmDialog({ title: '退出教务登录', message: '退出后查询课表/成绩等需要重新登录，是否继续？' })
  } catch {
    return
  }
  try {
    await eduLogout()
    eduLoggedIn.value = false
    eduUserid.value = ''
    showToast('已退出教务登录')
  } catch {
    showFailToast('退出失败')
  }
}

async function onEduLoginSuccess() {
  await refreshEduStatus()
}

async function refreshConversations() {
  try {
    conversations.value = await listConversations()
  } catch (error: any) {
    if (error.response?.status === 401) {
      logout()
    }
  }
}

async function selectConversation(id: string) {
  activeId.value = id
  sidebarOpen.value = false
  try {
    const detail = await getConversationMessages(id)
    messages.value = detail.messages.length ? detail.messages : [welcomeMessage]
    await scrollToBottom()
  } catch {
    showFailToast('加载对话失败')
  }
}

async function createNewConversation() {
  try {
    const conv = await createConversation()
    await refreshConversations()
    activeId.value = conv.id
    messages.value = [welcomeMessage]
    sidebarOpen.value = false
    await scrollToBottom()
  } catch {
    showFailToast('创建对话失败')
  }
}

async function renamePrompt(conv: Conversation) {
  const next = window.prompt('输入新标题', conv.title)
  if (!next || !next.trim()) return
  try {
    await renameConversation(conv.id, next.trim())
    await refreshConversations()
  } catch {
    showFailToast('重命名失败')
  }
}

async function deletePrompt(conv: Conversation) {
  try {
    await showConfirmDialog({ title: '删除对话', message: `确定删除“${conv.title}”？` })
  } catch {
    return
  }
  try {
    await deleteConversation(conv.id)
    if (activeId.value === conv.id) {
      activeId.value = null
      messages.value = [welcomeMessage]
    }
    await refreshConversations()
    showToast('已删除')
  } catch {
    showFailToast('删除失败')
  }
}

function logout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('username')
  router.push('/login')
}

async function sendMessage() {
  const content = input.value.trim()
  if (!content || loading.value) return

  let convId = activeId.value
  if (!convId) {
    try {
      const created = await createConversation()
      await refreshConversations()
      convId = created.id
      activeId.value = convId
      messages.value = [welcomeMessage]
    } catch {
      showFailToast('创建对话失败')
      return
    }
  }

  const targetConversationId = convId

  if (activeId.value === targetConversationId) {
    messages.value.push({ role: 'user', content })
  }
  input.value = ''
  loadingByConversation.value = { ...loadingByConversation.value, [targetConversationId]: true }
  await scrollToBottom()

  try {
    const response = await chatWithAgent({
      message: content,
      conversation_id: targetConversationId,
    })
    const finalConvId = response.conversation_id || targetConversationId

    if (activeId.value === finalConvId) {
      messages.value.push({
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
      })
      await scrollToBottom()
    }
    if (response.needs_edu_login && !eduLoggedIn.value) {
      eduLoginVisible.value = true
    }
    await refreshConversations()
  } catch (error: any) {
    if (error.response?.status === 401) {
      showFailToast('登录状态已过期，请重新登录')
      logout()
      return
    }
    if (activeId.value === targetConversationId) {
      const message = error instanceof Error ? error.message : '请求失败'
      messages.value.push({ role: 'assistant', content: `处理失败：${message}` })
    }
  } finally {
    const next = { ...loadingByConversation.value }
    delete next[targetConversationId]
    loadingByConversation.value = next
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-shell {
  display: flex;
  height: 100vh;
  background: #f7f8fa;
}

.sidebar {
  width: 240px;
  background: #fff;
  border-right: 1px solid #edf0f5;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #edf0f5;
}

.sidebar-title {
  font-weight: 600;
  font-size: 15px;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  font-size: 14px;
  color: #1f2933;
}

.conversation-item:hover {
  background: #f1f4f9;
}

.conversation-item.active {
  background: #e8f0ff;
  color: #1677ff;
  font-weight: 600;
}

.conversation-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.conversation-actions {
  display: flex;
  gap: 8px;
  color: #94a3b8;
  font-size: 16px;
}

.conversation-actions :deep(.van-icon):hover {
  color: #1677ff;
}

.empty-tip {
  padding: 16px;
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
}

.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #edf0f5;
  font-size: 13px;
}

.edu-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.edu-tag {
  font-size: 12px;
  color: #16a34a;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edu-tag.online {
  color: #16a34a;
}

.account-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.username {
  color: #1677ff;
  font-weight: 500;
}

.sidebar-mask {
  display: none;
}

.chat-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 12px 86px;
}

.message-row {
  display: flex;
  margin-bottom: 12px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 86%;
  padding: 12px;
  border-radius: 16px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.user .bubble {
  border-top-right-radius: 4px;
  background: #1677ff;
  color: #fff;
}

.assistant .bubble {
  border-top-left-radius: 4px;
  background: #fff;
  color: #1f2933;
  box-shadow: 0 2px 10px rgb(0 0 0 / 4%);
}

.loading-bubble {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.sources {
  margin-top: 12px;
}

.sources-title {
  margin-bottom: 6px;
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
}

.composer {
  position: sticky;
  bottom: 0;
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
  border-top: 1px solid #edf0f5;
  background: #fff;
}

.composer-input {
  flex: 1;
  border-radius: 20px;
  background: #f7f8fa;
}

@media (max-width: 720px) {
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 50;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }
  .sidebar.open {
    transform: translateX(0);
  }
  .sidebar-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgb(0 0 0 / 30%);
    z-index: 40;
  }
}
</style>
