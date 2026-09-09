import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import router from './router'
import App from './App.vue'
// 样式导入顺序为冻结约定(风格规范 11.2):Element Plus 整包 → tokens → 主题桥接 → 基础样式
import 'element-plus/dist/index.css'
import './styles/tokens.css'
import './styles/element-theme.css'
import './styles/base.css'

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
