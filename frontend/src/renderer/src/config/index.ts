/*
环境配置文件
开发环境
测试环境
线上环境
*/
//当前的环境
const env = 'local'

const EnvConfig = {
    local: {
        baseApi: 'http://localhost:8000',
    },
    prod: {
        baseApi: 'http://localhost:8000',

    },
}

export default {
    env,
    //mock的总开关
    ...EnvConfig[env]
}