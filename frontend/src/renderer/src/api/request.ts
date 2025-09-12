import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage, ElLoading } from 'element-plus'

// 后端API的基础URL
const BASE_URL = 'http://127.0.0.1:8000'

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
        // 允许通过 config.showLoading = false 关闭本次请求的全局 Loading
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
        // request 阶段异常，尝试安全关闭
        try { this.loadingCount = Math.max(0, this.loadingCount - 1); if (this.loadingCount === 0) this.loadingInstance?.close() } catch {}
        return Promise.reject(error)
      }
    )

    this.instance.interceptors.response.use(
      // 我们期望从后端获取的数据结构是 ApiResponse<T>
      (response: AxiosResponse<any>) => {
        const showLoading = (response.config as any).showLoading !== false
        if (showLoading) {
          try {
            this.loadingCount = Math.max(0, this.loadingCount - 1)
            if (this.loadingCount === 0) this.loadingInstance?.close()
          } catch {}
        }
        const res = response.data

        // 如果响应的数据中不包含我们约定的 status 字段，
        // 那么就认为它是一个非标准的、原始的响应（比如 openapi.json），
        // 此时应该直接返回整个响应数据本身。
        if (res.status === undefined) {
          return res;
        }

        // 如果HTTP状态码是200，但业务状态是error，则认为是错误
        if (res.status === 'error') {
          ElMessage.error(res.message || '操作失败')
          return Promise.reject(new Error(res.message || 'Error'))
        }
        // 如果成功，直接返回data部分
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
        
        // --- 详细的错误处理增强 ---
        if (error.response && error.response.status === 422) {
          // 专门处理 FastAPI 的校验错误
          const validationErrors = error.response.data.detail
          if (Array.isArray(validationErrors)) {
            const errorMessages = validationErrors.map((err: any) => {
              // 从 loc 数组中提取有意义的字段名
              const fieldName = err.loc.slice(1).join(' -> ')
              return `字段 '${fieldName}': ${err.msg}`
            }).join('<br/>')
            
            ElMessage({
              type: 'error',
              dangerouslyUseHTMLString: true, // 允许使用<br/>换行
              message: `<strong>输入校验失败:</strong><br/>${errorMessages}`,
              duration: 5000 // 持续时间长一点，方便查看
            })
          } else {
             ElMessage.error('发生了一个未知的校验错误')
          }
        } else {
          // 对其他类型的错误使用通用处理（优先后端 detail 信息）
          const errorMessage = error.response?.data?.message || error.response?.data?.detail || error.message || '请求失败'
          ElMessage.error(errorMessage)
        }

        console.error('请求错误:', error.response?.data || error)
        return Promise.reject(error)
      }
    )
  }

  // request方法现在返回Promise<T>
  public request<T>(config: AxiosRequestConfig): Promise<T> {
    // 拦截器已经处理了数据解包，所以这里可以直接返回实例的请求结果
    return this.instance.request(config)
  }

  public get<T>(url: string, params?: object, prefix: string = '/api', options?: { showLoading?: boolean }): Promise<T> {
    const fullUrl = prefix ? `${prefix}${url}` : url
    return this.request<T>({ method: 'GET', url: fullUrl, params, ...(options || {}) })
  }

  public post<T>(url: string, data?: object, prefix: string = '/api', options?: { showLoading?: boolean }): Promise<T> {
    const fullUrl = prefix ? `${prefix}${url}` : url
    return this.request<T>({ method: 'POST', url: fullUrl, data, ...(options || {}) })
  }

  public put<T>(url: string, data?: object, prefix: string = '/api', options?: { showLoading?: boolean }): Promise<T> {
    const fullUrl = prefix ? `${prefix}${url}` : url
    return this.request<T>({ method: 'PUT', url: fullUrl, data, ...(options || {}) })
  }

  public delete<T>(url: string, params?: object, prefix: string = '/api', options?: { showLoading?: boolean }): Promise<T> {
    const fullUrl = prefix ? `${prefix}${url}` : url
    return this.request<T>({ method: 'DELETE', url: fullUrl, params, ...(options || {}) })
  }
}

// 默认HTTP客户端（用于普通请求）
export default new HttpClient({
  baseURL: BASE_URL,
  timeout: 120000, // 增加到120秒，适合AI生成任务
  headers: { 'Content-Type': 'application/json' }
})

// AI生成专用HTTP客户端（更长的超时时间）
export const aiHttpClient = new HttpClient({
  baseURL: BASE_URL,
  timeout: 300000, // 5分钟超时，适合复杂的AI生成任务
  headers: { 'Content-Type': 'application/json' }
})

// --- 调用示例 ---
// 普通业务接口（自动加/api）
// http.get('/projects')  // 实际请求 /api/projects
// http.post('/ai/generate', data) // 实际请求 /api/ai/generate
// 特殊接口（不加前缀）
// http.get('/openapi.json', undefined, '') // 实际请求 /openapi.json