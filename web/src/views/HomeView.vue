<template>
  <div class="home-container">
    <div v-if="isLoading" class="loading-container">
      <a-spin size="large" />
      <p class="loading-text">正在连接服务...</p>
    </div>

    <div v-else-if="error" class="error-container">
      <a-result status="error" :title="error.title" :sub-title="error.message">
        <template #extra>
          <a-button type="primary" @click="retryLoad">重试</a-button>
          <a-button :href="faqUrl" target="_blank" rel="noopener noreferrer">常见问题</a-button>
        </template>
      </a-result>
    </div>

    <template v-else>
      <header class="site-header">
        <div class="header-inner">
          <button class="brand" type="button" @click="scrollToTop">
            <img
              v-if="infoStore.organization?.logo"
              :src="infoStore.organization.logo"
              :alt="productName"
              class="brand-logo"
            />
            <span v-else class="brand-logo brand-logo-fallback">粟</span>
            <span class="brand-name">{{ productName }}</span>
          </button>

          <nav class="nav-links" aria-label="首页导航"></nav>

          <div class="header-actions">
            <button class="language-switch" type="button" @click="toggleLanguage">
              <Languages />
              <span>{{ languageLabel }}</span>
            </button>
            <UserInfoComponent :show-button="true" />
          </div>
        </div>
      </header>

      <main class="home-main">
        <section id="home" class="hero-section">
          <div class="tech-bg" aria-hidden="true">
            <span class="tech-node node-a"></span>
            <span class="tech-node node-b"></span>
            <span class="tech-node node-c"></span>
          </div>

          <div class="hero-inner">
            <div class="hero-copy reveal-up">
              <h1 class="hero-title">
                <span class="title-main">杂粮育种大模型</span>
                <span class="title-sub">让育种报告生成更证据化、更可追溯</span>
              </h1>

              <p class="hero-description">
                整合杂粮育种知识图谱、科学文献与开放资源证据，面向育种问题生成结构化、可验证、可追溯的分析报告
              </p>

              <div class="hero-actions">
                <button class="button-base primary" type="button" @click="openAgentChat">
                  <span>开始生成</span>
                  <ArrowRight />
                </button>
              </div>
            </div>

            <div class="agent-card reveal-up delay-1" aria-label="杂粮育种智能体聊天界面">
              <div class="agent-card-header">
                <div class="agent-card-icon">
                  <Bot />
                </div>
                <div>
                  <h2>杂粮育种 AI 助手</h2>
                  <p><span class="online-dot"></span>在线</p>
                </div>
              </div>

              <div class="agent-frame-wrap">
                <div v-if="!userStore.isLoggedIn" class="agent-login-mask">
                  <div class="agent-login-mask-icon">
                    <Bot />
                  </div>
                  <h3>登录后进入智能体对话</h3>
                  <p>请使用页面右上角登录，登录完成后这里会自动切换为聊天界面</p>
                </div>

                <div v-else class="agent-frame-stage">
                  <iframe
                    ref="agentIframeRef"
                    :key="agentFrameKey"
                    class="agent-frame"
                    :src="agentChatUrlWithTheme"
                    title="杂粮育种 Agent 聊天界面"
                    loading="eager"
                    referrerpolicy="no-referrer-when-downgrade"
                    allow="clipboard-read; clipboard-write; microphone"
                    @load="handleAgentFrameLoad"
                  ></iframe>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="workflow-section reveal-up">
          <div class="workflow-heading">
            <!-- <span class="workflow-tag">智能研发流程</span> -->
            <h2>从育种问题到证据追踪报告的智能生成流程</h2>
            <p>面向科研和育种团队，输出可执行、可验证、可追溯的分析过程</p>
          </div>

          <div class="workflow-cards">
            <article
              v-for="(item, index) in workflowSteps"
              :key="item.title"
              class="workflow-card"
            >
              <div class="workflow-card-top">
                <span class="workflow-index">{{ String(index + 1).padStart(2, '0') }}</span>
              </div>
              <h3>{{ item.title }}</h3>
              <p>{{ item.desc }}</p>
            </article>
          </div>
        </section>
      </main>

      <footer class="footer">
        <div class="footer-content">
          <p class="copyright">
            {{ infoStore.footer?.copyright || '© 山西省后稷实验室. 版权归属语析框架团队.' }}
          </p>

          <p class="record-info">
            <a
              class="record-link"
              href="https://beian.miit.gov.cn/"
              target="_blank"
              rel="noopener noreferrer"
            >
              备案号：晋ICP备2026005456号-1
            </a>
            <span class="record-divider">｜</span>
            <span>公安备案申请中</span>
          </p>
        </div>
      </footer>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useThemeStore } from '@/stores/theme'
import { healthApi } from '@/apis/system_api'
import UserInfoComponent from '@/components/UserInfoComponent.vue'
import { ArrowRight, Bot, Languages } from 'lucide-vue-next'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const themeStore = useThemeStore()

const faqUrl = 'https://xerrors.github.io/Yuxi/'
const productName = '杂粮育种大模型'

const agentChatUrl = import.meta.env.VITE_AGENT_CHAT_URL || '/agent'

const agentFrameKey = ref(0)
const agentFrameLoaded = ref(false)
const agentIframeRef = ref(null)
const isLoading = ref(true)
const error = ref(null)
const currentLanguage = ref('zh')

const authStorageKeys = [
  'token',
  'access_token',
  'refresh_token',
  'user',
  'userInfo',
  'user_info',
  'currentUser'
]
let authCheckTimer = null
let accentFrameRefreshTimer = null
let lastAuthSnapshot = ''
let syncingOuterLogout = false
let syncingAccentFromAgent = false

const languageLabel = computed(() => (currentLanguage.value === 'zh' ? '中文' : 'EN'))

const readThemeVars = () => {
  const styles = window.getComputedStyle(document.documentElement)

  return {
    primary: styles.getPropertyValue('--main-700').trim() || '#047857',
    primaryLight: styles.getPropertyValue('--main-500').trim() || '#10b981',
    primarySoft: styles.getPropertyValue('--main-50').trim() || '#ecfdf5',
    text: styles.getPropertyValue('--main-900').trim() || '#064e3b'
  }
}

const persistThemeForAgent = () => {
  const theme = readThemeVars()
  localStorage.setItem('agent_theme', JSON.stringify(theme))
  localStorage.setItem('theme_primary', theme.primary)
  localStorage.setItem('theme_primary_light', theme.primaryLight)
  return theme
}

const agentChatUrlWithTheme = computed(() => {
  const url = new URL(agentChatUrl, window.location.origin)
  const theme = persistThemeForAgent()

  url.searchParams.set('embedded', '1')
  url.searchParams.set('primary', theme.primary)
  url.searchParams.set('primaryLight', theme.primaryLight)

  return url.pathname + url.search + url.hash
})

const toggleLanguage = () => {
  currentLanguage.value = currentLanguage.value === 'zh' ? 'en' : 'zh'
}

const syncAccentToAgentFrame = () => {
  const iframeWindow = agentIframeRef.value?.contentWindow

  if (!iframeWindow) {
    return
  }

  iframeWindow.postMessage(
    {
      type: 'ACCENT_CHANGED_FROM_PARENT',
      accent: themeStore.accent
    },
    window.location.origin
  )
}

const setOuterAccentFromAgent = (accent) => {
  if (!accent || accent === themeStore.accent) {
    return
  }

  syncingAccentFromAgent = true
  themeStore.setAccent(accent)

  requestAnimationFrame(() => {
    syncAccentToAgentFrame()
    syncingAccentFromAgent = false
  })
}

const handleAgentMessage = (event) => {
  if (event.origin !== window.location.origin) {
    return
  }

  const { type, accent } = event.data || {}

  if (type === 'ACCENT_CHANGED_FROM_AGENT') {
    setOuterAccentFromAgent(accent)
  }
}

const workflowSteps = [
  {
    title: '提出育种科学问题',
    desc: '明确作物、目标性状、候选基因、研究场景和预期分析目标'
  },
  {
    title: '知识检索与证据整合',
    desc: '联合作物育种知识图谱、PubMed/bioRxiv 文献与开放资源，筛选问题相关证据'
  },
  {
    title: '证据支持的可追溯推理',
    desc: '围绕基因功能、调控网络、表型关联和育种价值形成可解释推理链'
  },
  {
    title: '生成结构化育种报告',
    desc: '输出包含问题解析、证据来源、推理过程、候选结论和后续验证建议的报告'
  }
]

const checkHealth = async () => {
  try {
    const response = await healthApi.checkHealth()
    if (response.status !== 'ok') {
      throw new Error('服务不可用')
    }
  } catch (e) {
    error.value = {
      title: '服务连接失败',
      message: '后端服务无法响应，请检查服务是否正常运行'
    }
    throw e
  }
}

const loadData = async () => {
  isLoading.value = true
  error.value = null

  try {
    await checkHealth()
    await infoStore.loadInfoConfig()
  } catch (e) {
    console.error('加载失败:', e)
  } finally {
    isLoading.value = false
  }
}

const retryLoad = () => {
  loadData()
}

const scrollToTop = () => {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const refreshAgentFrame = () => {
  persistThemeForAgent()
  agentFrameLoaded.value = false
  agentFrameKey.value += 1
}

const syncThemeToAgentFrame = () => {
  const iframeWindow = agentIframeRef.value?.contentWindow

  if (!iframeWindow) {
    return
  }

  iframeWindow.postMessage(
    {
      type: 'SYNC_THEME',
      payload: persistThemeForAgent()
    },
    window.location.origin
  )
}

const syncThemeAndReloadAgentFrame = () => {
  persistThemeForAgent()
  syncAccentToAgentFrame()
  syncThemeToAgentFrame()

  if (syncingAccentFromAgent || !userStore.isLoggedIn) {
    return
  }

  if (accentFrameRefreshTimer) {
    clearTimeout(accentFrameRefreshTimer)
  }

  accentFrameRefreshTimer = window.setTimeout(() => {
    refreshAgentFrame()
  }, 120)
}

const getAuthSnapshot = () => {
  return authStorageKeys
    .map((key) => `${key}:${localStorage.getItem(key) || ''}`)
    .join('|')
}

const hasAnyAuthStorage = (snapshot = getAuthSnapshot()) => {
  return snapshot.split('|').some((item) => {
    const [, value = ''] = item.split(':')
    return Boolean(value)
  })
}

const syncOuterLogout = async () => {
  if (syncingOuterLogout || !userStore.isLoggedIn) {
    return
  }

  syncingOuterLogout = true

  try {
    if (typeof userStore.logout === 'function') {
      await userStore.logout()
    } else if (typeof userStore.clearUser === 'function') {
      await userStore.clearUser()
    } else if (typeof userStore.clearAuth === 'function') {
      await userStore.clearAuth()
    } else if (typeof userStore.$reset === 'function') {
      userStore.$reset()
    } else if (typeof userStore.$patch === 'function') {
      userStore.$patch({ user: null, token: '', isLoggedIn: false })
    }

    authStorageKeys.forEach((key) => localStorage.removeItem(key))
    sessionStorage.removeItem('redirect')
    lastAuthSnapshot = getAuthSnapshot()
    refreshAgentFrame()
  } finally {
    syncingOuterLogout = false
  }
}

const handleAgentFrameLoad = async () => {
  agentFrameLoaded.value = true
  syncAccentToAgentFrame()
  syncThemeToAgentFrame()

  try {
    const iframeLocation = agentIframeRef.value?.contentWindow?.location
    const iframePath = `${iframeLocation?.pathname || ''}${iframeLocation?.hash || ''}`

    if (userStore.isLoggedIn && /login|sign-in|signin/i.test(iframePath)) {
      await syncOuterLogout()
    }
  } catch (error) {
    // 跨域 iframe 无法读取 location；同域 /agent 不会进入这里。
  }
}

const handleAuthStorageChange = async (event) => {
  if (!authStorageKeys.includes(event.key)) {
    return
  }

  const nextSnapshot = getAuthSnapshot()
  const hadAuth = hasAnyAuthStorage(lastAuthSnapshot)
  const hasAuth = hasAnyAuthStorage(nextSnapshot)
  lastAuthSnapshot = nextSnapshot

  if (userStore.isLoggedIn && hadAuth && !hasAuth) {
    await syncOuterLogout()
  }
}

const checkEmbeddedAuthState = async () => {
  if (!userStore.isLoggedIn) {
    lastAuthSnapshot = getAuthSnapshot()
    return
  }

  const nextSnapshot = getAuthSnapshot()
  const hadAuth = hasAnyAuthStorage(lastAuthSnapshot)
  const hasAuth = hasAnyAuthStorage(nextSnapshot)

  if (hadAuth && !hasAuth) {
    await syncOuterLogout()
    return
  }

  lastAuthSnapshot = nextSnapshot
}

const openAgentChat = () => {
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', '/agent')
    router.push('/login')
    return
  }

  router.push(agentChatUrl)
}

watch(
  () => themeStore.accent,
  () => {
    syncThemeAndReloadAgentFrame()
  },
  { flush: 'post' }
)

watch(
  () => userStore.isLoggedIn,
  (isLoggedIn) => {
    lastAuthSnapshot = getAuthSnapshot()

    if (isLoggedIn) {
      refreshAgentFrame()
    }
  }
)

onMounted(async () => {
  await loadData()
  lastAuthSnapshot = getAuthSnapshot()
  window.addEventListener('storage', handleAuthStorageChange)
  window.addEventListener('message', handleAgentMessage)
  authCheckTimer = window.setInterval(checkEmbeddedAuthState, 800)

  if (userStore.isLoggedIn) {
    refreshAgentFrame()
  }
})

onUnmounted(() => {
  window.removeEventListener('storage', handleAuthStorageChange)
  window.removeEventListener('message', handleAgentMessage)

  if (authCheckTimer) {
    clearInterval(authCheckTimer)
    authCheckTimer = null
  }

  if (accentFrameRefreshTimer) {
    clearTimeout(accentFrameRefreshTimer)
    accentFrameRefreshTimer = null
  }
})
</script>

<style lang="less" scoped>
.home-container {
  height: 100vh;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: var(--main-900);
  background:
    radial-gradient(circle at top right, var(--main-50), transparent 56%),
    radial-gradient(circle at 10% 20%, var(--main-20), transparent 32%),
    var(--main-5);
  position: relative;
  overflow: hidden;
}

.loading-container,
.error-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-container {
  flex-direction: column;
  gap: 1rem;
}

.loading-text {
  color: var(--gray-600);
  font-size: 0.95rem;
}

.site-header {
  height: 74px;
  flex-shrink: 0;
  background: var(--color-trans-light);
  border-bottom: 1px solid var(--main-30);
  backdrop-filter: blur(20px);
  z-index: 100;
  box-shadow: 0 6px 25px rgba(3, 80, 101, 0.03);
}

.header-inner {
  width: min(1220px, calc(100% - 48px));
  height: 100%;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  color: var(--main-900);
}

.brand-logo {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  object-fit: cover;
  box-shadow: 0 10px 22px rgba(3, 80, 101, 0.12);
}

.brand-logo-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--main-700), var(--main-500));
  color: var(--gray-0);
  font-weight: 800;
}

.brand-name {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--main-900);
  letter-spacing: -0.02em;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: clamp(1.2rem, 3vw, 2.2rem);
  margin-left: auto;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}

.language-switch {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0 0.85rem;
  border-radius: 999px;
  border: 1px solid var(--main-60);
  color: var(--main-800);
  background: var(--main-0);
  font-size: 0.9rem;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(3, 80, 101, 0.06);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;

  :deep(svg) {
    width: 16px;
    height: 16px;
  }

  &:hover {
    transform: translateY(-1px);
    border-color: var(--main-120, var(--main-100));
    background: var(--main-20);
  }
}

.home-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  overflow: hidden;
}

.hero-section {
  min-height: 0;
  display: flex;
  align-items: center;
  position: relative;
  overflow: hidden;
}

.tech-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.86;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(var(--main-20) 1px, transparent 1px),
      linear-gradient(90deg, var(--main-20) 1px, transparent 1px);
    background-size: 54px 54px;
    mask-image: radial-gradient(circle at 72% 48%, black, transparent 66%);
  }
}

.tech-node {
  position: absolute;
  border: 1px solid var(--main-100);
  background: var(--main-0);
  box-shadow: 0 18px 40px rgba(3, 80, 101, 0.08);
  animation: floatNode 8s ease-in-out infinite;
}

.node-a {
  width: 86px;
  height: 86px;
  right: 13%;
  top: 18%;
  border-radius: 26px;
}

.node-b {
  width: 54px;
  height: 54px;
  right: 7%;
  bottom: 20%;
  border-radius: 50%;
  animation-delay: 1.2s;
}

.node-c {
  width: 118px;
  height: 118px;
  left: 5%;
  bottom: 18%;
  border-radius: 34px;
  transform: rotate(12deg);
  animation-delay: 0.8s;
}

.hero-inner {
  width: min(1220px, calc(100% - 48px));
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(520px, 600px);
  align-items: center;
  gap: clamp(2rem, 5vw, 4.25rem);
  position: relative;
  z-index: 1;
}

.hero-copy {
  max-width: 660px;
}

.hero-title {
  margin: 0;
  color: var(--main-950, var(--main-900));
  font-family:
    Inter,
    'PingFang SC',
    'Microsoft YaHei',
    'Noto Sans SC',
    system-ui,
    -apple-system,
    sans-serif;
}

.title-main {
  display: block;
  font-size: clamp(2.65rem, 4.4vw, 4.15rem);
  line-height: 1.08;
  letter-spacing: -0.05em;
  font-weight: 900;
  background: linear-gradient(135deg, var(--main-900) 0%, var(--main-700) 45%, var(--main-500) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: 0 18px 34px rgba(3, 120, 88, 0.075);
}

.title-sub {
  display: block;
  max-width: 620px;
  margin-top: 0.42rem;
  font-size: clamp(1.46rem, 2.15vw, 2.08rem);
  line-height: 1.22;
  letter-spacing: -0.03em;
  font-weight: 850;
  background: linear-gradient(135deg, var(--main-800) 0%, var(--main-600) 54%, var(--main-400) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.hero-description {
  max-width: 620px;
  margin: 1rem 0 0;
  color: var(--gray-700);
  font-size: 1rem;
  line-height: 1.78;
  font-weight: 560;
}

.hero-actions {
  margin-top: 1.4rem;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.9rem;
}

.button-base {
  min-height: 50px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border-radius: 999px;
  padding: 0 1.55rem;
  font-size: 1rem;
  font-weight: 800;
  cursor: pointer;
  text-decoration: none;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;

  :deep(svg) {
    width: 18px;
    height: 18px;
  }

  &:hover {
    transform: translateY(-2px);
  }
}

.button-base.primary {
  border: 1px solid transparent;
  color: var(--gray-0);
  background: linear-gradient(135deg, var(--main-700), var(--main-500));
  box-shadow: 0 18px 34px rgba(3, 120, 88, 0.15);

  &:hover {
    background: linear-gradient(135deg, var(--main-700), var(--main-500));
  }
}

.agent-card {
  align-self: center;
  border-radius: 1.6rem;
  overflow: hidden;
  background: var(--main-0);
  border: 1px solid var(--main-60);
  box-shadow:
    0 18px 42px rgba(3, 80, 101, 0.08),
    0 1px 0 rgba(255, 255, 255, 0.8) inset;
  height: min(40vh, 430px);
  min-height: 360px;
  max-height: 430px;
  display: flex;
  flex-direction: column;
}

.agent-card-header {
  min-height: 74px;
  display: flex;
  align-items: center;
  gap: 0.95rem;
  padding: 0 1.35rem;
  color: var(--gray-0);
  background:
    radial-gradient(circle at 85% 0%, rgba(255, 255, 255, 0.24), transparent 34%),
    linear-gradient(135deg, var(--main-700), var(--main-500));
}

.agent-card-icon {
  width: 42px;
  height: 42px;
  border-radius: 1.25rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--main-700);
  background: var(--gray-0);

  :deep(svg) {
    width: 24px;
    height: 24px;
  }
}

.agent-card-header h2 {
  margin: 0;
  font-size: 1.06rem;
  font-weight: 900;
}

.agent-card-header p {
  margin: 0.25rem 0 0;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.86rem;
  font-weight: 700;
}

.online-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--gray-0);
}

.agent-frame-wrap {
  flex: 1;
  width: 100%;
  min-height: 0;
  position: relative;
  background: var(--main-5);
  overflow: hidden;
}

.agent-login-mask {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  text-align: center;
  background:
    radial-gradient(circle at 50% 15%, var(--main-20), transparent 36%),
    var(--main-0);
}

.agent-login-mask-icon {
  width: 54px;
  height: 54px;
  border-radius: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--main-700);
  background: var(--main-30);
  margin-bottom: 1rem;

  :deep(svg) {
    width: 26px;
    height: 26px;
  }
}

.agent-login-mask h3 {
  margin: 0;
  color: var(--main-900);
  font-size: 1.05rem;
  font-weight: 900;
}

.agent-login-mask p {
  max-width: 320px;
  margin: 0.65rem 0 0;
  color: var(--gray-600);
  font-size: 0.9rem;
  line-height: 1.7;
  font-weight: 600;
}

.agent-frame-stage {
  --agent-scale: 0.5;
  width: 100%;
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.agent-frame {
  width: calc(100% / var(--agent-scale));
  height: calc(100% / var(--agent-scale));
  border: 0;
  display: block;
  background: var(--main-0);
  transform: scale(var(--agent-scale));
  transform-origin: left top;
}

.workflow-section {
  width: min(1220px, calc(100% - 48px));
  height: 100%;
  min-height: 0;
  margin: 0 auto;
  padding: clamp(1.2rem, 2.4vh, 1.85rem) 0 clamp(1.3rem, 2.6vh, 2rem);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.workflow-heading {
  text-align: center;
  margin: 0 auto clamp(1.15rem, 2.5vh, 1.85rem);
}

.workflow-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 26px;
  padding: 0 0.8rem;
  margin-bottom: 0.55rem;
  border-radius: 999px;
  color: var(--main-600);
  background: var(--main-30);
  border: 1px solid var(--main-50);
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.workflow-heading h2 {
  max-width: 840px;
  margin: 0 auto;
  color: var(--main-900);
  font-size: clamp(1.75rem, 2.65vw, 2.55rem);
  line-height: 1.16;
  font-weight: 950;
  letter-spacing: -0.045em;
}

.workflow-heading p {
  max-width: 720px;
  margin: 0.72rem auto 0;
  color: var(--gray-600);
  font-size: 0.96rem;
  line-height: 1.65;
  font-weight: 650;
}

.workflow-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: clamp(1rem, 1.8vw, 1.35rem);
}

.workflow-card {
  position: relative;
  min-height: clamp(140px, 16vh, 172px);
  padding: clamp(1.1rem, 1.8vh, 1.45rem);
  overflow: hidden;
  border-radius: 1.35rem;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.97), rgba(255, 255, 255, 0.84)),
    var(--main-0);
  border: 1px solid var(--main-50);
  box-shadow: 0 18px 42px rgba(3, 80, 101, 0.07);
  transition:
    transform 0.22s ease,
    box-shadow 0.22s ease,
    border-color 0.22s ease;

  &::before {
    content: '';
    position: absolute;
    inset: 0 0 auto;
    height: 4px;
    background: linear-gradient(90deg, var(--main-700), var(--main-400));
    opacity: 0.86;
  }

  &::after {
    content: '';
    position: absolute;
    right: -42px;
    top: -46px;
    width: 118px;
    height: 118px;
    border-radius: 50%;
    background: var(--main-30);
    opacity: 0.75;
  }

  &:hover {
    transform: translateY(-4px);
    border-color: var(--main-100);
    box-shadow: 0 24px 54px rgba(3, 80, 101, 0.1);
  }

  h3 {
    position: relative;
    z-index: 1;
    margin: 0.65rem 0 0.55rem;
    color: var(--main-900);
    font-size: 1.08rem;
    line-height: 1.3;
    font-weight: 900;
  }

  p {
    position: relative;
    z-index: 1;
    max-width: 13.5rem;
    margin: 0;
    color: var(--gray-600);
    font-size: 0.92rem;
    line-height: 1.66;
    font-weight: 600;
  }
}

.workflow-card-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.workflow-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  height: 2.35rem;
  padding: 0 0.65rem;
  border-radius: 0.9rem;
  color: var(--main-700);
  background: var(--main-30);
  border: 1px solid var(--main-60);
  font-size: 1.35rem;
  line-height: 1;
  font-weight: 950;
  letter-spacing: -0.03em;
}

.footer {
  min-height: 58px;
  background: color-mix(in srgb, var(--main-0) 92%, transparent);
  border-top: 1px solid var(--main-20);
  flex-shrink: 0;
  backdrop-filter: blur(14px);
}

.footer-content {
  width: min(1220px, calc(100% - 48px));
  min-height: 58px;
  margin: 0 auto;
  padding: 0.38rem 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.18rem;
  text-align: center;
}

.copyright {
  margin: 0;
  color: var(--main-700);
  font-size: 0.8rem;
  line-height: 1.35;
  font-weight: 650;
  opacity: 0.86;
}

.record-info {
  margin: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0.2rem;
  color: var(--gray-500);
  font-size: 0.76rem;
  line-height: 1.35;
  font-weight: 560;
}

.record-link {
  color: var(--gray-500);
  text-decoration: none;
  transition: color 0.2s ease;

  &:hover {
    color: var(--main-700);
  }
}

.record-divider {
  color: var(--main-200);
}

.reveal-up {
  opacity: 0;
  transform: translateY(14px);
  animation: revealUp 0.7s ease forwards;
}

.reveal-up.delay-1 {
  animation-delay: 120ms;
}

@keyframes revealUp {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes floatNode {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }

  50% {
    transform: translateY(-18px) rotate(4deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .reveal-up,
  .tech-node {
    opacity: 1;
    transform: none;
    animation: none;
  }
}

@media (max-width: 1120px) {
  .home-container {
    height: auto;
    min-height: 100vh;
    overflow-x: hidden;
    overflow-y: auto;
  }

  .home-main {
    display: block;
  }

  .hero-section {
    padding: 3rem 0 2rem;
  }

  .hero-inner {
    grid-template-columns: 1fr;
  }

  .agent-card {
    width: min(100%, 620px);
    max-width: 620px;
    height: 500px;
    min-height: 500px;
    max-height: 500px;
    margin-top: 1rem;
  }

  .workflow-section {
    height: auto;
    padding: 2rem 0 2.4rem;
  }

  .workflow-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .home-container {
    height: auto;
    min-height: 100vh;
    overflow-x: hidden;
    overflow-y: auto;
  }

  .site-header {
    height: auto;
  }

  .header-inner {
    width: min(100% - 28px, 1220px);
    min-height: 68px;
    flex-wrap: nowrap;
    padding: 0.7rem 0;
    gap: 0.75rem;
  }

  .brand {
    min-width: 0;
  }

  .brand-logo {
    width: 32px;
    height: 32px;
    border-radius: 10px;
    flex-shrink: 0;
  }

  .brand-name {
    max-width: 9.5rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 1rem;
  }

  .header-actions {
    flex-shrink: 0;
    gap: 0.45rem;
  }

  .language-switch {
    min-height: 32px;
    padding: 0 0.65rem;
    font-size: 0.82rem;
  }

  .home-main {
    display: block;
  }

  .hero-section {
    padding: 2rem 0 1.5rem;
  }

  .hero-inner,
  .workflow-section,
  .footer-content {
    width: min(100% - 28px, 1220px);
  }

  .hero-inner {
    grid-template-columns: 1fr;
    gap: 1.75rem;
  }

  .hero-copy {
    max-width: none;
  }

  .title-main {
    font-size: clamp(2.15rem, 11vw, 2.75rem);
    line-height: 1.08;
    letter-spacing: -0.045em;
  }

  .title-sub {
    margin-top: 0.35rem;
    font-size: clamp(1.25rem, 6vw, 1.6rem);
    line-height: 1.28;
  }

  .hero-description {
    margin-top: 0.9rem;
    font-size: 0.95rem;
    line-height: 1.75;
  }

  .hero-actions {
    margin-top: 1.25rem;
  }

  .button-base {
    width: 100%;
    min-height: 48px;
  }

  .agent-card {
    width: 100%;
    height: min(64vh, 480px);
    min-height: 380px;
    max-height: 480px;
    margin-top: 0;
    border-radius: 1.25rem;
  }

  .agent-card-header {
    min-height: 66px;
    padding: 0 1rem;
  }

  .agent-card-icon {
    width: 38px;
    height: 38px;
    border-radius: 1rem;
  }

  .agent-card-header h2 {
    font-size: 0.98rem;
  }

  .agent-card-header p {
    font-size: 0.8rem;
  }

  .agent-login-mask {
    padding: 1.5rem;
  }

  .agent-login-mask h3 {
    font-size: 1rem;
  }

  .agent-login-mask p {
    font-size: 0.86rem;
  }

  .agent-frame-stage {
    --agent-scale: 0.42;
    overflow-x: auto;
  }

  .workflow-section {
    height: auto;
    padding: 2rem 0 2.2rem;
  }

  .workflow-heading {
    text-align: left;
    margin-bottom: 1.2rem;
  }

  .workflow-heading h2,
  .workflow-heading p {
    margin-left: 0;
    margin-right: 0;
  }

  .workflow-heading h2 {
    font-size: clamp(1.45rem, 7vw, 1.9rem);
    line-height: 1.25;
  }

  .workflow-heading p {
    margin-top: 0.6rem;
    font-size: 0.92rem;
    line-height: 1.7;
  }

  .workflow-cards {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .workflow-card {
    min-height: auto;
    padding: 1.15rem;
    border-radius: 1.15rem;
  }

  .workflow-card h3 {
    font-size: 1rem;
  }

  .workflow-card p {
    max-width: none;
    font-size: 0.9rem;
  }

 .footer {
  height: auto;
  min-height: 62px;
}

.footer-content {
  width: min(100% - 28px, 1220px);
  min-height: 62px;
  padding: 0.5rem 0;
}

.copyright {
  font-size: 0.74rem;
  line-height: 1.45;
}

.record-info {
  font-size: 0.72rem;
  line-height: 1.45;
}
}
</style>
