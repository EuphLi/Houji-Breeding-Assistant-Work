import { ref } from 'vue'
import { defineStore } from 'pinia'
import { theme } from 'ant-design-vue'

export const useThemeStore = defineStore('theme', () => {
  // 从 localStorage 读取保存的主题，默认为浅色
  const isDark = ref(localStorage.getItem('theme') === 'dark')

  // 从 localStorage 读取保存的主题色方案，默认为紫色
  const accent = ref(localStorage.getItem('accent') || 'purple')

  // 主题色配置
  const accentConfigs = {
    purple: { mainColor: '#6b21a8', subColor: '#ec4899' },
    green: { mainColor: '#008f51', subColor: '#4dd996' },
    gold: { mainColor: '#7a4a0f', subColor: '#d89828' }
  }

  // 动态构建 Ant Design 主题配置
  function buildTheme() {
    const cfg = accentConfigs[accent.value]
    return {
      token: {
        fontFamily:
          "'HarmonyOS Sans SC', Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;",
        colorPrimary: cfg.mainColor,
        borderRadius: 8,
        wireframe: false
      },
      algorithm: isDark.value ? theme.darkAlgorithm : undefined
    }
  }

  // 当前主题配置（响应式）
  const currentTheme = ref(buildTheme())

  // 切换深色/浅色模式
  function toggleTheme() {
    setTheme(!isDark.value)
  }

  // 设置深色/浅色模式
  function setTheme(dark) {
    isDark.value = dark
    localStorage.setItem('theme', dark ? 'dark' : 'light')
    updateDocumentTheme()
    currentTheme.value = buildTheme()
  }

  // 更新 document 的主题类
  function updateDocumentTheme() {
    if (isDark.value) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  // 设置主题色方案
  function setAccent(scheme) {
    if (!accentConfigs[scheme]) return
    accent.value = scheme
    localStorage.setItem('accent', scheme)
    document.documentElement.dataset.accent = scheme
    currentTheme.value = buildTheme()
  }

  const accentCycle = { purple: 'green', green: 'gold', gold: 'purple' }

  // 切换主题色方案（purple → green → gold → purple）
  function toggleAccent() {
    setAccent(accentCycle[accent.value])
  }

  // 初始化
  updateDocumentTheme()
  document.documentElement.dataset.accent = accent.value

  return {
    isDark,
    accent,
    currentTheme,
    toggleTheme,
    setTheme,
    setAccent,
    toggleAccent
  }
})
