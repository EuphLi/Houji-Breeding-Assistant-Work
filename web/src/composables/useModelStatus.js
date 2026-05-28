import { reactive } from 'vue'
import { modelProviderApi } from '@/apis/system_api'

/**
 * 模型状态检查 composable，供 Chat/Embedding/Rerank 模型选择器共用。
 */
export function useModelStatus() {
  const statusMap = reactive({})

  const isNetworkStatusMessage = (message = '') => {
    const text = String(message).toLowerCase()
    return (
      text.includes('temporary failure in name resolution') ||
      text.includes('name or service not known') ||
      text.includes('dns') ||
      text.includes('connectionerror') ||
      text.includes('network is unreachable') ||
      text.includes('timed out') ||
      text.includes('timeout') ||
      text.includes('connecttimeout') ||
      text.includes('readtimeout') ||
      text.includes('failed to establish a new connection')
    )
  }

  const getStatusIcon = (key) => {
    const status = statusMap[key]
    if (!status) return '○'
    if (status.status === 'available') return '✓'
    if (status.status === 'unsupported') return '×'
    if (status.status === 'unavailable' || status.status === 'error') {
      return isNetworkStatusMessage(status.message) ? '?' : '✗'
    }
    return '○'
  }

  const getStatusClass = (key) => {
    return statusMap[key]?.status || ''
  }

  const getStatusTooltip = (key) => {
    const status = statusMap[key]
    if (!status) return '状态未知'
    if (status.status === 'available') return '可用: 连接正常'
    if (status.status === 'unsupported') return `不支持: ${status.message || '无详细信息'}`
    if (isNetworkStatusMessage(status.message)) {
      return `网络不可达 / 状态未知: ${status.message || '无详细信息'}`
    }
    const text = { unavailable: '不可用', error: '错误' }[status.status] || '未知'
    return `${text}: ${status.message || '无详细信息'}`
  }

  const checkV2Status = async (spec) => {
    try {
      const response = await modelProviderApi.getModelStatusBySpec(spec)
      if (response.data) {
        statusMap[spec] = response.data
      }
    } catch {
      statusMap[spec] = { spec, status: 'error', message: '检查失败' }
    }
  }

  const checkV2Statuses = async (models) => {
    for (const model of models || []) {
      await checkV2Status(model.spec)
    }
  }

  return {
    statusMap,
    getStatusIcon,
    getStatusClass,
    getStatusTooltip,
    checkV2Status,
    checkV2Statuses
  }
}
