<template>
  <div class="login-view" :class="{ 'has-alert': serverStatus === 'error' }">
    <!-- 服务状态提示 -->
    <div v-if="serverStatus === 'error'" class="server-status-alert">
      <div class="alert-content">
        <alert-circle-icon class="alert-icon" size="20" />
        <div class="alert-text">
          <div class="alert-title">服务端连接失败</div>
          <div class="alert-message">{{ serverError }}</div>
        </div>
        <a-button type="link" size="small" @click="checkServerHealth" :loading="healthChecking">
          重试
        </a-button>
      </div>
    </div>

    <!-- 背景舞台 -->
    <div class="stage" ref="stageRef">
      <div class="wheat-specimen">
        <img src="/pic_millet.png" alt="禾穗装饰" />
      </div>
    </div>

    <!-- 登录主体 -->
    <div class="login-wrapper">
      <!-- 左侧品牌区 -->
      <div class="brand-section">
        <div class="brand-content">
          <div class="logo-placeholder">
            <img :src="brandLogo" alt="logo" />
          </div>
          <h1>
            <span v-if="brandOrgName" class="brand-org">{{ brandOrgName }}</span>
            <!-- <span v-if="brandOrgName && brandName !== brandOrgName" class="brand-sep"></span>
            <span class="brand-main">{{ brandName }}</span> -->
          </h1>
          <div class="tagline">人工智能驱动的作物生长进化模拟</div>
        </div>
      </div>

      <!-- 右侧表单区 -->
      <div class="form-section">
        <div class="form-container">
          <!-- 初始化管理员表单 -->
          <div v-if="isFirstRun" class="init-form">
            <div class="form-header">
              <h2>系统初始化</h2>
              <span>创建超级管理员账户</span>
            </div>
            <a-form :model="adminForm" @finish="handleInitialize" layout="vertical">
              <a-form-item
                label="用户ID"
                name="user_id"
                :rules="[
                  { required: true, message: '请输入用户ID' },
                  {
                    pattern: /^[a-zA-Z0-9_]+$/,
                    message: '用户ID只能包含字母、数字和下划线'
                  },
                  {
                    min: 3,
                    max: 20,
                    message: '用户ID长度必须在3-20个字符之间'
                  }
                ]"
              >
                <a-input
                  v-model:value="adminForm.user_id"
                  placeholder="请输入用户ID（3-20个字符）"
                  :maxlength="20"
                />
              </a-form-item>

              <a-form-item
                label="手机号（可选）"
                name="phone_number"
                :rules="[
                  {
                    validator: async (_rule, value) => {
                      if (!value || value.trim() === '') return
                      const phoneRegex = /^1[3-9]\d{9}$/
                      if (!phoneRegex.test(value)) {
                        throw new Error('请输入正确的手机号格式')
                      }
                    }
                  }
                ]"
              >
                <a-input
                  v-model:value="adminForm.phone_number"
                  placeholder="可用于登录，可不填写"
                  :max-length="11"
                />
              </a-form-item>

              <a-form-item
                label="密码"
                name="password"
                :rules="[{ required: true, message: '请输入密码' }]"
              >
                <a-input-password v-model:value="adminForm.password" />
              </a-form-item>

              <a-form-item
                label="确认密码"
                name="confirmPassword"
                :rules="[
                  { required: true, message: '请确认密码' },
                  { validator: validateConfirmPassword }
                ]"
              >
                <a-input-password v-model:value="adminForm.confirmPassword" />
              </a-form-item>

              <a-form-item v-if="showAgreementConsent" class="agreement-form-item">
                <div class="agreement-row">
                  <a-checkbox v-model:checked="agreementAccepted">
                    登录即代表同意
                    <a
                      class="agreement-link"
                      :href="userAgreementUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                      >《用户协议》</a
                    >
                    <a
                      class="agreement-link"
                      :href="privacyPolicyUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                      >《隐私协议》</a
                    >
                  </a-checkbox>
                </div>
              </a-form-item>

              <a-form-item>
                <a-button type="primary" html-type="submit" :loading="loading" block size="large">
                  创建管理员账户
                </a-button>
              </a-form-item>
            </a-form>
          </div>

          <!-- 登录表单 -->
          <div v-else class="login-form">
            <div class="form-header">
              <h2>登录系统</h2>
              <span>请使用您的学术内网账号登录</span>
            </div>

            <div class="login-tabs">
              <button
                :class="['tab-btn', { active: loginMode === 'sms' }]"
                @click="switchTab('sms')"
              >
                验证码登录
              </button>
              <button
                :class="['tab-btn', { active: loginMode === 'password' }]"
                @click="switchTab('password')"
              >
                密码登录
              </button>
            </div>

            <!-- 密码登录表单 -->
            <a-form
              v-if="loginMode === 'password'"
              :model="loginForm"
              @finish="handleLogin"
              layout="vertical"
            >
              <a-form-item
                label="登录账号"
                name="loginId"
                :rules="[{ required: true, message: '请输入用户ID或手机号' }]"
              >
                <a-input v-model:value="loginForm.loginId" placeholder="用户ID或手机号">
                  <template #prefix>
                    <user-icon size="18" />
                  </template>
                </a-input>
              </a-form-item>

              <a-form-item
                label="密码"
                name="password"
                :rules="[{ required: true, message: '请输入密码' }]"
              >
                <a-input-password v-model:value="loginForm.password">
                  <template #prefix>
                    <lock-icon size="18" />
                  </template>
                </a-input-password>
              </a-form-item>

              <a-form-item v-if="showAgreementConsent" class="agreement-form-item">
                <div class="agreement-row">
                  <a-checkbox v-model:checked="agreementAccepted">
                    登录即代表同意
                    <a
                      class="agreement-link"
                      :href="userAgreementUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                      >《用户协议》</a
                    >
                    <a
                      class="agreement-link"
                      :href="privacyPolicyUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                      >《隐私协议》</a
                    >
                  </a-checkbox>
                </div>
              </a-form-item>

              <a-form-item>
                <a-button
                  type="primary"
                  html-type="submit"
                  :loading="loading"
                  :disabled="isLocked"
                  block
                  size="large"
                >
                  <span v-if="isLocked">账户已锁定 {{ formatTime(lockRemainingTime) }}</span>
                  <span v-else>登录</span>
                </a-button>
              </a-form-item>
            </a-form>

            <!-- 验证码登录表单 -->
            <a-form v-else :model="smsForm" @finish="handleSmsLogin" layout="vertical">
              <a-form-item
                label="手机号"
                name="phone"
                :rules="[
                  { required: true, message: '请输入手机号' },
                  { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号格式' }
                ]"
              >
                <a-input v-model:value="smsForm.phone" placeholder="请输入手机号" :maxlength="11">
                  <template #prefix>
                    <phone-icon size="18" />
                  </template>
                </a-input>
              </a-form-item>

              <a-form-item
                label="验证码"
                name="code"
                :rules="[
                  { required: true, message: '请输入验证码' },
                  { pattern: /^\d{6}$/, message: '验证码为6位数字' }
                ]"
              >
                <a-input
                  v-model:value="smsForm.code"
                  placeholder="请输入验证码"
                  :maxlength="6"
                  class="sms-code-input"
                >
                  <template #prefix>
                    <shield-check-icon size="18" />
                  </template>
                  <template #suffix>
                    <a-button
                      type="link"
                      :disabled="smsCooldown > 0"
                      :loading="smsSending"
                      @click="handleSendCode"
                    >
                      <span v-if="smsCooldown > 0">{{ smsCooldown }}s 后重试</span>
                      <span v-else>发送验证码</span>
                    </a-button>
                  </template>
                </a-input>
              </a-form-item>

              <a-form-item v-if="showAgreementConsent" class="agreement-form-item">
                <div class="agreement-row">
                  <a-checkbox v-model:checked="agreementAccepted">
                    登录即代表同意
                    <a
                      class="agreement-link"
                      :href="userAgreementUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                      >《用户协议》</a
                    >
                    <a
                      class="agreement-link"
                      :href="privacyPolicyUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                      >《隐私协议》</a
                    >
                  </a-checkbox>
                </div>
              </a-form-item>

              <a-form-item>
                <a-button type="primary" html-type="submit" :loading="loading" block size="large"
                  >登录/注册</a-button
                >
              </a-form-item>
            </a-form>

            <!-- OIDC 登录选项 -->
            <div v-if="oidcChecking || oidcEnabled" class="third-party-login">
              <div class="divider">
                <span>或使用以下方式登录</span>
              </div>
              <div class="login-icons">
                <div v-if="oidcChecking" class="login-skeleton">
                  <a-skeleton-button block size="large" :active="true" />
                </div>
                <a-button
                  v-else
                  type="default"
                  size="large"
                  block
                  :loading="oidcLoading"
                  @click="handleOIDCLogin"
                >
                  <template #icon>
                    <key-icon size="18" />
                  </template>
                  {{ oidcButtonText }}
                </a-button>
              </div>
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMessage" class="error-message">
            {{ errorMessage }}
          </div>
        </div>

        <!-- 版权信息 -->
        <div class="copyright-text">&copy; 2026 HouJi. All Rights Reserved.</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import { message } from 'ant-design-vue'
import { healthApi } from '@/apis/system_api'
import { authApi } from '@/apis/auth_api'
import {
  User as UserIcon,
  Lock as LockIcon,
  Key as KeyIcon,
  Phone as PhoneIcon,
  ShieldCheck as ShieldCheckIcon,
  AlertCircle as AlertCircleIcon
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

// 品牌展示数据
const brandLogo = computed(() => {
  return infoStore.organization?.logo || ''
})
const brandOrgName = computed(() => {
  return infoStore.organization?.name?.trim() || ''
})
const brandName = computed(() => {
  const orgName = brandOrgName.value
  const brandNameRaw = infoStore.branding?.name?.trim() || 'Yuxi'
  if (orgName && brandNameRaw && orgName !== brandNameRaw) {
    return brandNameRaw
  }
  return orgName || brandNameRaw
})
const userAgreementUrl = computed(() => {
  return infoStore.footer?.user_agreement_url?.trim() || ''
})
const privacyPolicyUrl = computed(() => {
  return infoStore.footer?.privacy_policy_url?.trim() || ''
})
const showAgreementConsent = computed(() => {
  return Boolean(userAgreementUrl.value && privacyPolicyUrl.value)
})

// 状态
const isFirstRun = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const agreementAccepted = ref(false)
const serverStatus = ref('loading')
const serverError = ref('')
const healthChecking = ref(false)

// OIDC 相关状态
const oidcEnabled = ref(false)
const oidcLoading = ref(false)
const oidcChecking = ref(true)
const oidcButtonText = ref('OIDC 登录')

// 登录锁定相关状态
const isLocked = ref(false)
const lockRemainingTime = ref(0)
const lockCountdown = ref(null)
const stageRef = ref(null)

// 登录模式
const loginMode = ref('sms')

const switchTab = (mode) => {
  loginMode.value = mode
  errorMessage.value = ''
}

// 登录表单
const loginForm = reactive({
  loginId: '',
  password: ''
})

// 验证码登录表单
const smsForm = reactive({
  phone: '',
  code: ''
})

// 发送验证码状态
const smsCooldown = ref(0)
const smsSending = ref(false)
let smsCooldownTimer = null

const clearSmsCooldown = () => {
  if (smsCooldownTimer) {
    clearInterval(smsCooldownTimer)
    smsCooldownTimer = null
  }
}

const startSmsCooldown = () => {
  clearSmsCooldown()
  smsCooldown.value = 60
  smsCooldownTimer = setInterval(() => {
    smsCooldown.value--
    if (smsCooldown.value <= 0) {
      clearSmsCooldown()
    }
  }, 1000)
}

// 管理员初始化表单
const adminForm = reactive({
  user_id: '',
  password: '',
  confirmPassword: '',
  phone_number: ''
})

// 清理倒计时器
const clearLockCountdown = () => {
  if (lockCountdown.value) {
    clearInterval(lockCountdown.value)
    lockCountdown.value = null
  }
}

// 启动锁定倒计时
const startLockCountdown = (remainingSeconds) => {
  clearLockCountdown()
  isLocked.value = true
  lockRemainingTime.value = remainingSeconds

  lockCountdown.value = setInterval(() => {
    lockRemainingTime.value--
    if (lockRemainingTime.value <= 0) {
      clearLockCountdown()
      isLocked.value = false
      errorMessage.value = ''
    }
  }, 1000)
}

// 格式化时间显示
const formatTime = (seconds) => {
  if (seconds < 60) {
    return `${seconds}秒`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}分${remainingSeconds}秒`
  } else if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}小时${minutes}分钟`
  } else {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    return `${days}天${hours}小时`
  }
}

// 密码确认验证
const validateConfirmPassword = async (_rule, value) => {
  if (value === '') {
    throw new Error('请确认密码')
  }
  if (value !== adminForm.password) {
    throw new Error('两次输入的密码不一致')
  }
}

const ensureAgreementAccepted = () => {
  if (!showAgreementConsent.value || agreementAccepted.value) {
    return true
  }
  message.warning('请先阅读并同意《用户协议》《隐私协议》')
  return false
}

// 处理登录
const handleLogin = async () => {
  if (isLocked.value) {
    message.warning(`账户被锁定，请等待 ${formatTime(lockRemainingTime.value)}`)
    return
  }

  if (!ensureAgreementAccepted()) {
    return
  }

  try {
    loading.value = true
    errorMessage.value = ''
    clearLockCountdown()

    await userStore.login({
      loginId: loginForm.loginId,
      password: loginForm.password
    })

    message.success('登录成功')

    const redirectPath = sessionStorage.getItem('redirect') || '/'
    sessionStorage.removeItem('redirect')

    if (redirectPath === '/') {
      try {
        await agentStore.initialize()
        router.push('/agent')
      } catch (error) {
        console.error('获取智能体信息失败:', error)
        router.push('/agent')
      }
    } else {
      router.push(redirectPath)
    }
  } catch (error) {
    console.error('登录失败:', error)

    if (error.status === 423) {
      let remainingTime = 0
      if (error.headers && error.headers.get) {
        const lockRemainingHeader = error.headers.get('X-Lock-Remaining')
        if (lockRemainingHeader) {
          remainingTime = parseInt(lockRemainingHeader)
        }
      }

      if (remainingTime === 0) {
        const lockTimeMatch = error.message.match(/(\d+)\s*秒/)
        if (lockTimeMatch) {
          remainingTime = parseInt(lockTimeMatch[1])
        }
      }

      if (remainingTime > 0) {
        startLockCountdown(remainingTime)
        errorMessage.value = `由于多次登录失败，账户已被锁定 ${formatTime(remainingTime)}`
      } else {
        errorMessage.value = error.message || '账户被锁定，请稍后再试'
      }
    } else {
      errorMessage.value = error.message || '登录失败，请检查用户名和密码'
    }
  } finally {
    loading.value = false
  }
}

// 发送验证码
const handleSendCode = async () => {
  if (!/^1[3-9]\d{9}$/.test(smsForm.phone)) {
    message.warning('请先输入正确的手机号')
    return
  }

  try {
    smsSending.value = true
    errorMessage.value = ''
    await authApi.sendSmsCode(smsForm.phone)
    message.success('验证码已发送')
    startSmsCooldown()
  } catch (error) {
    if (error.status === 429) {
      startSmsCooldown()
      errorMessage.value = error.message || '发送过于频繁，请稍后再试'
    } else {
      errorMessage.value = error.message || '发送验证码失败'
    }
  } finally {
    smsSending.value = false
  }
}

// 处理验证码登录
const handleSmsLogin = async () => {
  if (!ensureAgreementAccepted()) {
    return
  }

  try {
    loading.value = true
    errorMessage.value = ''

    await userStore.smsLogin(smsForm.phone, smsForm.code)

    message.success('登录成功')

    const redirectPath = sessionStorage.getItem('redirect') || '/'
    sessionStorage.removeItem('redirect')

    if (redirectPath === '/') {
      try {
        await agentStore.initialize()
        router.push('/agent')
      } catch (error) {
        console.error('获取智能体信息失败:', error)
        router.push('/agent')
      }
    } else {
      router.push(redirectPath)
    }
  } catch (error) {
    console.error('验证码登录失败:', error)
    errorMessage.value = error.message || '验证码登录失败'
  } finally {
    loading.value = false
  }
}

// 处理 OIDC 登录
const handleOIDCLogin = async () => {
  if (!ensureAgreementAccepted()) {
    return
  }

  try {
    oidcLoading.value = true
    errorMessage.value = ''

    const response = await authApi.getOIDCLoginUrl()
    if (response.login_url) {
      const redirectPath =
        sessionStorage.getItem('redirect') || router.currentRoute.value.query.redirect || '/'
      sessionStorage.setItem('oidc_redirect', redirectPath)

      window.location.href = response.login_url
    } else {
      errorMessage.value = '获取 OIDC 登录地址失败'
    }
  } catch (error) {
    console.error('OIDC 登录失败:', error)
    errorMessage.value = error.message || 'OIDC 登录失败，请重试'
  } finally {
    oidcLoading.value = false
  }
}

// 检查 OIDC 配置
const checkOIDCConfig = async () => {
  oidcChecking.value = true
  try {
    const config = await authApi.getOIDCConfig()
    oidcEnabled.value = config.enabled
    if (config.provider_name) {
      oidcButtonText.value = config.provider_name
    }
  } catch (error) {
    console.error('检查 OIDC 配置失败:', error)
    oidcEnabled.value = false
  } finally {
    oidcChecking.value = false
  }
}

// 处理初始化管理员
const handleInitialize = async () => {
  if (!ensureAgreementAccepted()) {
    return
  }

  try {
    loading.value = true
    errorMessage.value = ''

    if (adminForm.password !== adminForm.confirmPassword) {
      errorMessage.value = '两次输入的密码不一致'
      return
    }

    await userStore.initialize({
      user_id: adminForm.user_id,
      password: adminForm.password,
      phone_number: adminForm.phone_number || null
    })

    message.success('管理员账户创建成功')
    router.push('/')
  } catch (error) {
    console.error('初始化失败:', error)
    errorMessage.value = error.message || '初始化失败，请重试'
  } finally {
    loading.value = false
  }
}

// 检查是否是首次运行
const checkFirstRunStatus = async () => {
  try {
    loading.value = true
    const isFirst = await userStore.checkFirstRun()
    isFirstRun.value = isFirst
  } catch (error) {
    console.error('检查首次运行状态失败:', error)
    errorMessage.value = '系统出错，请稍后重试'
  } finally {
    loading.value = false
  }
}

// 检查服务器健康状态
const checkServerHealth = async () => {
  try {
    healthChecking.value = true
    const response = await healthApi.checkHealth()
    if (response.status === 'ok') {
      serverStatus.value = 'ok'
    } else {
      serverStatus.value = 'error'
      serverError.value = response.message || '服务端状态异常'
    }
  } catch (error) {
    console.error('检查服务器健康状态失败:', error)
    serverStatus.value = 'error'
    serverError.value = error.message || '无法连接到服务端，请检查网络连接'
  } finally {
    healthChecking.value = false
  }
}

// 禾穗图标 SVG 路径
const ICON_PATH =
  'M772.7 516.8c-4.4-4.4-13.7-6.9-26.2-7.5-12.7-0.6-20.1-14.3-13.5-25.1 40.4-66.3 53.6-162.7 36.7-179.7-12.9-12.8-67-9.1-121 9.6-12.2 4.2-24.3-6.8-21.3-19.2 2.6-11.1 4.1-22.3 4.1-33.8 0-115.8-84.6-198.2-115.7-198.2-32.3 0-115.7 83.8-115.7 198.2 0 11.5 1.5 22.8 4.1 33.8 3 12.5-9.3 23.4-21.3 19.2-54-18.6-108.2-22.4-120.9-9.6-16.9 16.9-3.7 113.4 36.7 179.7 6.6 10.9-0.8 24.5-13.6 25.1-12.5 0.6-21.8 3.1-26.2 7.5-20.4 20.4 2.5 154.5 63.6 215.6 18.6 18.6 42.3 32.2 67 41.4 6.5 2.4 10.8 8.6 10.8 15.4v83.1c0 9.2 7.4 16.5 16.5 16.5 9.2 0 16.5-7.4 16.5-16.5V805c0-10 8.7-17.4 18.5-16.4 10.9 1.2 21.1 1.6 30.4 1.2 9.4-0.4 17.2 7.1 17.2 16.5v132.2c0 9.2 7.4 16.5 16.5 16.5 9.2 0 16.5-7.4 16.5-16.5V806.4c0-9.4 7.8-16.8 17.2-16.5 9.2 0.4 19.4 0 30.4-1.2 9.9-1.1 18.5 6.5 18.5 16.4v67.3c0 9.2 7.4 16.5 16.5 16.5 9.2 0 16.5-7.4 16.5-16.5v-83.1c0-6.9 4.3-13.1 10.8-15.4 24.6-9.3 48.4-22.8 67-41.4 60.9-61.2 83.8-195.2 63.4-215.7z m-26-189.2c12.7 12.8-14.1 118.2-63.2 167.3-48.9 49.1-138 59.2-150.4 46.7-0.8-0.8-1.6-2-2.2-3.4 1.7-12.7 1.6-28.5-0.5-45.7 5.7-32.4 21.2-73.5 49.3-101.6 49.1-49.2 154.5-76 167-63.3zM515.8 646.4c-9.3-24.3-22.8-47.7-41.1-66.1-1.8-1.8-3.6-3.5-5.5-5.2 20.2 0.7 37.1-1.8 46.6-6.7 9.7 5 26.4 7.4 46.6 6.7-1.9 1.7-3.7 3.4-5.5 5.2-18.3 18.4-31.7 41.8-41.1 66.1z m-2.7-220.3c0.9 0.1 1.9 0.2 2.7 0.2 0.9 0 1.8-0.1 2.7-0.2-1 2.3-1.9 4.6-2.7 6.9l-2.7-6.9z m2.7-330.6c19.5 0 82.6 74.2 82.6 165.5 0 69.9-63.5 132.4-82.6 132.4-20.3 0-82.6-62.5-82.6-132.4 0-94.6 63.3-165.5 82.6-165.5zM284.9 327.6c12.7-12.7 117.9 14.1 167 63.3 48.9 49.1 59.8 137.5 46.6 150.7C486 554 397.1 543.9 348 494.8c-49-49.1-75.8-154.6-63.1-167.2zM498.3 756c-12.7 12.7-102.6 2.4-152.2-47.1-49.5-49.5-76.7-156-63.9-168.8 12.8-12.8 119.3 14.2 168.9 63.9 26.1 26 41.4 63.1 48.2 94.2v56.5c-0.3 0.4-0.7 0.9-1 1.3z m187.3-47.1C636 758.4 546 768.7 533.3 756c-0.4-0.4-0.7-0.8-1.1-1.3v-17.2c0.1-3 0.1-6.1 0-9.3v-30.1c6.8-31.2 22.2-68.2 48.2-94.3 49.5-49.5 156.1-76.6 168.9-63.9 13 13-14.1 119.4-63.7 169z m0 0'

// 初始化背景动画
const initBackground = () => {
  const stage = stageRef.value
  if (!stage) return

  const formulas = [
    'R = h² × S',
    'ΔG = (i·σa·r)/L',
    'P = G + E',
    'y = Xb + Zu + e',
    'H² = Vg / Vp',
    'ATCG-GCTA'
  ]

  const iconCount = 20
  for (let i = 0; i < iconCount; i++) {
    createFloatingIcon(stage)
  }

  for (let i = 0; i < 8; i++) {
    const f = document.createElement('div')
    f.className = 'formula-float'
    f.innerText = formulas[Math.floor(Math.random() * formulas.length)]
    f.style.left = Math.random() * 80 + 5 + '%'
    f.style.top = Math.random() * 80 + 5 + '%'
    f.style.animationDelay = Math.random() * -15 + 's'
    stage.appendChild(f)
  }
}

const createFloatingIcon = (container) => {
  const svgNS = 'http://www.w3.org/2000/svg'
  const svg = document.createElementNS(svgNS, 'svg')
  const path = document.createElementNS(svgNS, 'path')

  const size = Math.random() * 30 + 20
  svg.setAttribute('viewBox', '0 0 1024 1024')
  svg.setAttribute('width', size)
  svg.setAttribute('height', size)
  svg.classList.add('floating-icon')

  path.setAttribute('d', ICON_PATH)
  svg.appendChild(path)

  svg.style.left = Math.random() * 100 + '%'
  svg.style.animationDuration = Math.random() * 12 + 10 + 's'
  svg.style.animationDelay = Math.random() * -20 + 's'

  container.appendChild(svg)
}

// 组件挂载时
onMounted(async () => {
  if (userStore.isLoggedIn) {
    router.push('/')
    return
  }

  if (route.query.oidc_error) {
    errorMessage.value = String(route.query.oidc_error)
  }

  await checkServerHealth()
  await checkFirstRunStatus()
  checkOIDCConfig()

  setTimeout(initBackground, 100)
})

onUnmounted(() => {
  clearLockCountdown()
  clearSmsCooldown()
})
</script>

<style lang="less">
.login-view {
  min-height: 100vh;
  width: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  background-color: var(--gray-10);

  &.has-alert {
    padding-top: 60px;
  }
}

/* 背景舞台 */
.stage {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, var(--main-600) 0%, var(--main-300) 100%);
  z-index: 1;
  overflow: hidden;
}

/* purple / green 主题恢复原来的深度 */
[data-accent="purple"] .stage,
[data-accent="green"] .stage {
  background: linear-gradient(135deg, var(--main-800) 0%, var(--main-500) 100%);
}

/* 飘动的图标样式 */
.floating-icon {
  position: absolute;
  z-index: 2;
  bottom: -100px;
  fill: #e9c46a;
  filter: drop-shadow(0 0 5px rgba(233, 196, 106, 0.4));
  animation: icon-float linear infinite;
  pointer-events: none;
  opacity: 0;
}

@keyframes icon-float {
  0% {
    transform: translateY(0) rotate(0deg);
    opacity: 0;
  }
  10% {
    opacity: 0.6;
  }
  90% {
    opacity: 0.6;
  }
  100% {
    transform: translateY(-120vh) rotate(360deg);
    opacity: 0;
  }
}

/* 科技公式层 */
.formula-float {
  position: absolute;
  color: #e9c46a;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  z-index: 2;
  opacity: 0;
  animation: formula-fade 15s linear infinite;
}

@keyframes formula-fade {
  0% {
    opacity: 0;
    transform: translateY(20px);
  }
  20% {
    opacity: 0.3;
  }
  80% {
    opacity: 0.3;
  }
  100% {
    opacity: 0;
    transform: translateY(-100px);
  }
}

/* 禾穗装饰 */
.wheat-specimen {
  position: absolute;
  top: 0;
  left: 40px;
  z-index: 3;
  opacity: 0.5;
  transform-origin: bottom center;
  animation: wheat-sway 4s ease-in-out infinite;
  pointer-events: none;

  img {
    width: 160px;
  }
}

@keyframes wheat-sway {
  0%,
  100% {
    transform: rotate(-1deg);
  }
  50% {
    transform: rotate(2deg);
  }
}

/* 登录主体 */
.login-wrapper {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  position: relative;
  z-index: 10;
}

/* 左侧品牌区 */
.brand-section {
  flex: 1.4;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: white;
  position: relative;
  padding: 40px;

  &::after {
    content: '';
    position: absolute;
    inset: 0;
    background-image: radial-gradient(rgba(255, 255, 255, 0.1) 1px, transparent 1px);
    background-size: 40px 40px;
    z-index: 1;
  }
}

.brand-content {
  position: relative;
  z-index: 2;
  text-align: center;

  h1 {
    font-size: 2.5rem;
    margin: 0;
    letter-spacing: 6px;
    font-weight: 600;
    text-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
  }

  .brand-org {
    color: rgba(255, 255, 255, 0.9);
  }

  .brand-sep {
    width: 6px;
    height: 6px;
    background-color: rgba(255, 255, 255, 0.5);
    border-radius: 50%;
    flex-shrink: 0;
  }

  .brand-main {
    color: white;
  }
}

.logo-placeholder {
  width: 100px;
  height: 100px;
  background: white;
  border-radius: 16px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
  overflow: hidden;

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
}

.tagline {
  margin-top: 40px;
  padding: 8px 20px;
  border: 1px solid rgba(233, 196, 106, 0.5);
  border-radius: 40px;
  color: #e9c46a;
  font-size: 0.9rem;
  display: inline-block;
}

/* 右侧表单区 */
.form-section {
  flex: 1;
  background: var(--gray-0);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 60px;
  position: relative;
}

.form-container {
  width: 100%;
  max-width: 400px;
}

.form-header {
  margin-bottom: 40px;

  h2 {
    font-size: 28px;
    color: var(--gray-1000);
    margin-bottom: 8px;
  }

  span {
    color: var(--gray-500);
    font-size: 14px;
  }
}

/* 登录方式切换 */
.login-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--gray-200);
}

.tab-btn {
  flex: 1;
  padding: 10px 16px;
  font-size: 15px;
  font-weight: 500;
  color: var(--gray-500);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition:
    color 0.2s,
    border-color 0.2s;

  &:hover {
    color: var(--main-color);
  }

  &.active {
    color: var(--main-color);
    border-bottom-color: var(--main-color);
  }
}

/* 验证码输入框：重置 suffix 内按钮样式，避免被 .login-form .ant-btn 撑高 */
.sms-code-input .ant-input-suffix {
  margin-left: 4px;
}

.sms-code-input .ant-input-suffix .ant-btn {
  height: auto;
  padding: 0;
  font-size: 14px;
  font-weight: 400;
  border: none;
}

/* 表单样式 */
.login-form,
.init-form {
  .ant-input-affix-wrapper {
    padding: 12px 15px;
    border-radius: 6px;
  }

  .ant-input {
    font-size: 16px;
  }

  .ant-input-prefix {
    margin-right: 10px;
    color: var(--gray-500);
  }

  .ant-btn {
    height: 48px;
    font-size: 16px;
    border-radius: 6px;
    font-weight: 600;
  }

  .ant-form-item-label > label {
    font-size: 14px;
    color: var(--gray-900);
  }
}

.init-form .ant-form-item {
  margin-bottom: 14px;
}

/* OIDC 第三方登录 */
.third-party-login {
  margin-top: 16px;

  .divider {
    position: relative;
    text-align: center;
    margin: 24px 0 16px;

    &::before,
    &::after {
      content: '';
      position: absolute;
      top: 50%;
      width: 30%;
      height: 1px;
      background-color: var(--gray-200);
    }

    &::before {
      left: 0;
    }

    &::after {
      right: 0;
    }

    span {
      display: inline-block;
      padding: 0 8px;
      background-color: var(--gray-0);
      color: var(--gray-400);
      font-size: 12px;
    }
  }

  .login-icons {
    .ant-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border-color: var(--gray-300);
      color: var(--gray-700);

      &:hover {
        border-color: var(--main-color);
        color: var(--main-color);
        background-color: var(--main-10);
      }

      svg {
        color: var(--main-color);
      }
    }
  }

  .login-skeleton {
    .ant-skeleton-button {
      width: 100% !important;
      height: 44px;
      border-radius: 8px;
    }
  }
}

/* 协议勾选 */
.agreement-form-item {
  margin-bottom: 12px;
}

.agreement-row {
  font-size: 13px;
  color: var(--gray-600);
  line-height: 1.6;

  .ant-checkbox-wrapper {
    display: inline-flex;
    align-items: flex-start;
  }

  .ant-checkbox + span {
    padding-inline-start: 8px;
  }
}

.agreement-link {
  color: var(--main-color);

  &:hover {
    text-decoration: underline;
  }
}

/* 错误提示 */
.error-message {
  margin-top: 16px;
  padding: 10px 12px;
  background-color: var(--color-error-50);
  border: 1px solid color-mix(in srgb, var(--color-error-500) 25%, transparent);
  border-radius: 6px;
  color: var(--color-error-700);
  font-size: 13px;
  text-align: center;
}

/* 版权信息 */
.copyright-text {
  position: absolute;
  bottom: 20px;
  right: 60px;
  font-size: 12px;
  color: var(--gray-400);
}

/* 服务状态警报 */
.server-status-alert {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 12px 20px;
  background: var(--color-error-500);
  color: var(--gray-0);
  z-index: 1000;

  .alert-content {
    display: flex;
    align-items: center;
    max-width: 1500px;
    margin: 0 auto;

    .alert-icon {
      font-size: 20px;
      margin-right: 12px;
    }

    .alert-text {
      flex: 1;

      .alert-title {
        font-weight: 600;
        font-size: 16px;
        margin-bottom: 2px;
      }

      .alert-message {
        font-size: 14px;
        opacity: 0.9;
      }
    }

    .ant-btn-link {
      color: var(--gray-0);
      border-color: var(--gray-0);

      &:hover {
        color: var(--gray-0);
        background-color: color-mix(in srgb, var(--gray-0) 10%, transparent);
      }
    }
  }
}

/* 移动端适配 */
@media screen and (max-width: 768px) {
  .login-wrapper {
    flex-direction: column;
    height: auto;
    min-height: 100vh;
  }

  .brand-section {
    flex: none;
    height: 30vh;
    min-height: 200px;
    padding: 15px;

    &::after {
      background: none;
    }
  }

  .brand-content {
    h1 {
      font-size: 1.8rem;
      letter-spacing: 2px;
      gap: 8px;
      flex-wrap: wrap;
    }
  }

  .logo-placeholder {
    width: 60px;
    height: 60px;
    margin-bottom: 8px;
    border-radius: 12px;
  }

  .tagline {
    margin-top: 12px;
    font-size: 0.7rem;
    padding: 5px 12px;
  }

  .form-section {
    flex: 1;
    padding: 20px 24px;
    min-height: 0;
  }

  .form-container {
    max-width: 100%;
  }

  .form-header {
    margin-bottom: 20px;

    h2 {
      font-size: 20px;
      margin-bottom: 4px;
    }

    span {
      font-size: 12px;
    }
  }

  .login-form,
  .init-form {
    .ant-input-affix-wrapper {
      padding: 11px 12px;
      font-size: 14px;
    }

    .ant-btn {
      height: 44px;
      font-size: 14px;
    }
  }

  .copyright-text {
    position: static;
    margin-top: 16px;
    text-align: center;
    font-size: 11px;
  }

  .stage .floating-icon {
    animation-duration: 15s;
  }

  .stage .formula-float {
    font-size: 11px;
  }

  .wheat-specimen {
    left: 20px;
    transform: scale(0.6);
    transform-origin: top left;
  }
}
</style>
