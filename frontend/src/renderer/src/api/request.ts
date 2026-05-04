import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage, ElLoading } from 'element-plus'

function resolveBaseUrl(): string {
  const platform = import.meta.env.VITE_APP_PLATFORM

  if (platform === 'web') {
    return ''
  }

  const explicitApiBase = import.meta.env.VITE_API_BASE_URL?.trim()

  if (explicitApiBase) {
    return explicitApiBase.replace(/\/$/, '')
  }

  return 'http://127.0.0.1:54321'
}

export const BASE_URL: string = resolveBaseUrl()

// 带 /api 前缀的基础 URL，供流式接口使用
export const API_BASE_URL: string = BASE_URL
  ? `${BASE_URL.replace(/\/$/, '')}/api`
  : '/api'

// API响应格式，与后端约定一致
interface ApiResponse<T> {
  status: 'success' | 'error'
  data: T
  message?: string
}

class HttpClient {
  private instance: AxiosInstance
  private loadingInstance: any
  private loadingCount = 0

  constructor(config: AxiosRequestConfig) {
    this.instance = axios.create(config)

    this.instance.interceptors.request.use(
      (config) => {
        const showLoading = (config as any).showLoading !== false
        if (showLoading) {
          if (this.loadingCount === 0) {
            this.loadingInstance = ElLoading.service({
              lock: true,
              text: '加载中...',
              background: 'rgba(0, 0, 0, 0.7)'
            })
          }
          this.loadingCount++
        }
        return config
      },
      (error) => {
        try { this.loadingCount = Math.max(0, this.loadingCount - 1); if (this.loadingCount === 0) this.loadingInstance?.close() } catch { }
        return Promise.reject(error)
      }
    )

    this.instance.interceptors.response.use(
      (response: AxiosResponse<any>) => {
        const showLoading = (response.config as any).showLoading !== false
        if (showLoading) {
          try {
            this.loadingCount = Math.max(0, this.loadingCount - 1)
            if (this.loadingCount === 0) this.loadingInstance?.close()
          } catch { }
        }
        // 检查是否有由于请求触发的工作流运行
        const startedWorkflows = response.headers['x-workflows-started']
        if (startedWorkflows) {
          const runIds = startedWorkflows.split(',').map(Number)
          if (runIds.length > 0) {
            window.dispatchEvent(new CustomEvent('workflow-started', { detail: runIds }))
          }
        }

        // 允许透传原始响应（用于读取 headers）
        if ((response.config as any).rawResponse === true) {
          return response as any
        }
        const res = response.data
        // 只有当 status 是 'success' 或 'error' 时才认为是包装格式
        // 避免误判业务对象中的 status 字段（如 WorkflowRunRead.status）
        if (res.status === 'success' || res.status === 'error') {
          if (res.status === 'error') {
            ElMessage.error(res.message || '操作失败')
            return Promise.reject(new Error(res.message || 'Error'))
          }
          return res.data
        }
        // 其他情况直接返回原始数据
        return res
      },
      (error) => {
        const showLoading = (error.config as any)?.showLoading !== false
        if (showLoading) {
          try {
            this.loadingCount = Math.max(0, this.loadingCount - 1)
            if (this.loadingCount === 0) this.loadingInstance?.close()
          } catch { }
        }
        if (axios.isCancel(error) || error?.code === 'ERR_CANCELED') {
          console.info('Request canceled:', error.config?.url || '')
          return Promise.reject(error)
        }
        if (error.response && error.response.status === 422) {
          const validationErrors = error.response.data.detail
          if (Array.isArray(validationErrors)) {
            const errorMessages = validationErrors.map((err: any) => {
              const fieldName = err.loc.slice(1).join(' -> ')
              return `字段 '${fieldName}': ${err.msg}`
            }).join('<br/>')
            ElMessage({ type: 'error', dangerouslyUseHTMLString: true, message: `<strong>输入校验失败:</strong><br/>${errorMessages}`, duration: 5000 })
          } else {
            ElMessage.error('发生了一个未知的校验错误')
          }
        } else {
          const errorMessage = error.response?.data?.message || error.response?.data?.detail || error.message || '请求失败'
          ElMessage.error(errorMessage)
        }
        console.error('请求错误:', error.response?.data || error)
        return Promise.reject(error)
      }
    )
  }

  public request<T>(config: AxiosRequestConfig): Promise<T> {
    return this.instance.request(config)
  }

  public get<T>(url: string, params?: object, prefix: string = '/api', options?: { showLoading?: boolean, signal?: AbortSignal }): Promise<T> {
    let normalizedUrl = url
    if (normalizedUrl === '/projects') normalizedUrl = '/projects/'
    const fullUrl = prefix ? `${prefix}${normalizedUrl}` : normalizedUrl
    return this.request<T>({ method: 'GET', url: fullUrl, params, signal: options?.signal, ...(options || {}) })
  }

  public post<T>(url: string, data?: object, prefix: string = '/api', options?: { showLoading?: boolean, signal?: AbortSignal }): Promise<T> {
    const fullUrl = prefix ? `${prefix}${url}` : url
    return this.request<T>({ method: 'POST', url: fullUrl, data, signal: options?.signal, ...(options || {}) })
  }

  public put<T>(url: string, data?: object, prefix: string = '/api', options?: { showLoading?: boolean, rawResponse?: boolean, signal?: AbortSignal }): Promise<T> {
    const fullUrl = prefix ? `${prefix}${url}` : url
    return this.request<T>({ method: 'PUT', url: fullUrl, data, signal: options?.signal, ...(options || {}) })
  }

  public delete<T>(url: string, params?: object, prefix: string = '/api', options?: { showLoading?: boolean, signal?: AbortSignal }): Promise<T> {
    const fullUrl = prefix ? `${prefix}${url}` : url
    return this.request<T>({ method: 'DELETE', url: fullUrl, params, signal: options?.signal, ...(options || {}) })
  }
}

export default new HttpClient({
  baseURL: BASE_URL,
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' }
})

export const aiHttpClient = new HttpClient({
  baseURL: BASE_URL,
  timeout: 300000,
  headers: { 'Content-Type': 'application/json' }
})
