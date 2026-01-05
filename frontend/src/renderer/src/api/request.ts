import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage, ElLoading } from 'element-plus'

// 后端API的基础URL
export const BASE_URL =
  import.meta.env.VITE_APP_PLATFORM === 'web'
    ? (import.meta.env.DEV ? '' : 'http://127.0.0.1:8000')
    : 'http://127.0.0.1:8000'

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
        try { this.loadingCount = Math.max(0, this.loadingCount - 1); if (this.loadingCount === 0) this.loadingInstance?.close() } catch {}
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
          } catch {}
        }
        // 允许透传原始响应（用于读取 headers）
        if ((response.config as any).rawResponse === true) {
          return response as any
        }
        const res = response.data
        if (res.status === undefined) {
          return res
        }
        if (res.status === 'error') {
          ElMessage.error(res.message || '操作失败')
          return Promise.reject(new Error(res.message || 'Error'))
        }
        return res.data
      },
      (error) => {
        const showLoading = (error.config as any)?.showLoading !== false
        if (showLoading) {
          try {
            this.loadingCount = Math.max(0, this.loadingCount - 1)
            if (this.loadingCount === 0) this.loadingInstance?.close()
          } catch {}
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
    const fullUrl = prefix ? `${prefix}${url}` : url
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
