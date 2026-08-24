/*
环境配置文件
开发环境
测试环境
线上环境
*/
import { LOCAL_BACKEND_BASE_URL } from './backend'

//当前的环境
const env = 'local'

const EnvConfig = {
    local: {
        baseApi: LOCAL_BACKEND_BASE_URL,
    },
    prod: {
        baseApi: LOCAL_BACKEND_BASE_URL,

    },
}

export default {
    env,
    //mock的总开关
    ...EnvConfig[env]
}
