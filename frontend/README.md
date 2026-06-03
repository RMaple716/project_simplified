# 旅游行程规划前端系统

基于 React + TypeScript + Vite 构建的现代化前端应用。

## 技术栈

- **框架**: React 18
- **语言**: TypeScript
- **构建工具**: Vite
- **路由**: React Router v6
- **状态管理**: Redux Toolkit + React-Redux
- **UI组件库**: Ant Design 5
- **HTTP客户端**: Axios
- **日期处理**: Day.js

## 项目结构

```
frontend/
├── src/
│   ├── components/        # 可复用组件
│   ├── pages/            # 页面组件
│   │   ├── Home.tsx              # 首页
│   │   ├── RequirementForm.tsx   # 需求表单
│   │   ├── ItineraryList.tsx     # 行程列表
│   │   ├── ItineraryDetail.tsx   # 行程详情
│   │   └── TaskStatus.tsx        # 任务状态
│   ├── services/         # API服务层
│   │   ├── api.ts                # Axios配置和拦截器
│   │   ├── index.ts              # API统一导出
│   │   ├── requirementApi.ts     # 需求API
│   │   ├── taskApi.ts            # 任务API
│   │   ├── itineraryApi.ts       # 行程API
│   │   ├── validationApi.ts      # 验证API
│   │   ├── staticDataApi.ts      # 静态数据API
│   │   ├── agentApi.ts           # 智能体API（新增）
│   │   └── apiTest.ts            # API测试示例（新增）
│   ├── store/            # Redux状态管理
│   │   ├── index.ts              # Store配置
│   │   └── slices/               # Redux Slices
│   │       ├── requirementSlice.ts
│   │       ├── itinerarySlice.ts
│   │       └── uiSlice.ts
│   ├── routes/           # 路由配置
│   │   └── index.tsx
│   ├── App.tsx           # 主应用组件
│   ├── main.tsx          # 入口文件
│   └── index.css         # 全局样式
├── docs/                 # 文档目录
│   └── API对接指南.md    # API使用详细文档
├── index.html            # HTML模板
├── package.json          # 依赖配置
├── vite.config.ts        # Vite配置
├── tsconfig.json         # TypeScript配置
└── README.md             # 项目文档
```

## 快速开始

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

应用将在 `http://localhost:3000` 启动

### 3. 构建生产版本

```bash
npm run build
```

### 4. 预览生产构建

```bash
npm run preview
```

## 功能特性

### ✅ 已实现功能

1. **首页** - 展示系统概览和快捷入口
2. **需求提交** - 填写旅行偏好和需求
3. **任务追踪** - 实时显示行程生成进度
4. **行程列表** - 查看和管理所有行程
5. **行程详情** - 展示详细的日程安排
6. **响应式设计** - 支持移动端和桌面端

### 📋 API集成

前端已与后端API完全对接，包括：

- ✅ 用户需求提交和解析
- ✅ 任务分解和状态追踪
- ✅ 行程创建、查询、更新、删除
- ✅ 时间冲突检测
- ✅ 静态数据获取（景点、城市等）
- ✅ 智能体推荐（景点、交通、住宿、美食）

### 🔧 API服务架构

#### 1. 统一的API客户端

所有API请求通过 `src/services/api.ts` 中的Axios实例发送，具备：
- 自动Token认证
- 统一的错误处理
- 请求/响应拦截器
- 开发环境日志记录

#### 2. 模块化API服务

按功能域划分的API模块：
- `requirementApi` - 用户需求管理
- `taskApi` - 任务分解与追踪
- `itineraryApi` - 行程CRUD操作
- `validationApi` - 行程校验
- `staticDataApi` - 基础数据查询
- `agentApi` - 智能体推荐（新增）

#### 3. 完整的TypeScript类型定义

每个API模块都包含完整的接口类型定义，提供智能提示和类型检查。

## 开发指南

### 添加新页面

1. 在 `src/pages/` 创建新组件
2. 在 `src/routes/index.tsx` 添加路由配置
3. 在导航菜单中添加链接（如需要）

### 添加新的API接口

1. 在 `src/services/` 创建新的API文件
2. 定义TypeScript接口类型
3. 导出API方法
4. 在 `src/services/index.ts` 中导出（可选）

示例：

``typescript
// src/services/exampleApi.ts
import apiClient from './api';

export interface ExampleRequest {
  name: string;
}

export const exampleApi = {
  getData: (data: ExampleRequest) => 
    apiClient.post('/example', data),
};
```

### 状态管理

使用Redux Toolkit管理全局状态：

``typescript
// 在组件中使用
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '../store';

const data = useSelector((state: RootState) => state.requirement);
dispatch(setLoading(true));
```

### API使用最佳实践

#### 1. 导入API服务

``typescript
// 方式一：按需导入（推荐）
import { requirementApi, itineraryApi } from '@/services';

// 方式二：从索引文件导入
import { requirementApi } from '@/services/index';
```

#### 2. 调用API并处理响应

``typescript
const handleSubmit = async () => {
  try {
    setLoading(true);
    
    const response = await requirementApi.submit({
      user_id: 'user_123',
      requirement: {
        city_name: '北京',
        travel_days: 3,
        total_budget: 5000,
        // ...
      }
    });
    
    if (response.code === 200) {
      message.success('提交成功');
      // 处理成功逻辑
    }
  } catch (error) {
    // 错误已由拦截器处理并显示message
    console.error('详细错误:', error);
  } finally {
    setLoading(false);
  }
};
```

#### 3. 使用TypeScript类型

``typescript
import type { Requirement } from '@/services';

const requirement: Requirement = {
  city_name: '北京',
  travel_days: 3,
  // TypeScript会提供智能提示和类型检查
};
```

更多API使用示例请参考：
- 📖 [API对接指南](./docs/API对接指南.md)
- 💻 [API测试示例](./src/services/apiTest.ts)

## 代理配置

开发环境下，Vite已配置API代理：

```
// vite.config.ts
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:9091',
      changeOrigin: true,
    }
  }
}
```

所有 `/api/v1/*` 的请求会自动转发到后端服务。

## 代码规范

- 使用TypeScript严格模式
- 遵循React Hooks最佳实践
- 组件采用函数式编程
- 使用ESLint和Prettier保持代码风格一致

## 浏览器支持

- Chrome (最新)
- Firefox (最新)
- Safari (最新)
- Edge (最新)

## 常见问题

### Q1: 如何修改后端API地址？

修改 `vite.config.ts` 中的 `proxy.target` 配置。

### Q2: 如何添加认证token？

在 `src/services/api.ts` 的请求拦截器中已预留token添加逻辑：

```
localStorage.setItem('token', 'your_token_here');
```

### Q3: 如何自定义主题？

使用Ant Design的主题配置，参考官方文档：https://ant.design/docs/react/customize-theme

### Q4: API请求失败怎么办？

1. 检查后端服务是否启动（`http://127.0.0.1:9091/docs`）
2. 查看浏览器控制台的网络请求
3. 检查Vite代理配置是否正确
4. 参考 [API对接指南](./docs/API对接指南.md) 的错误处理章节

### Q5: 如何调试API请求？

打开浏览器开发者工具 → Network标签页 → 过滤XHR请求，可以查看：
- 请求URL和方法
- 请求头和请求体
- 响应状态码和响应数据
- 请求耗时

## 相关文档

- 📘 [API对接指南](./docs/API对接指南.md) - 完整的API使用说明
- 🧪 [API测试示例](./src/services/apiTest.ts) - 可直接运行的测试代码
- 📋 [快速开始](./QUICKSTART.md)
- 🏗️ [项目架构](./ARCHITECTURE.md)
- 📝 [更新日志](#更新日志)

## 更新日志

### v1.1.0 (2026-05-24)
- ✨ 新增智能体API服务（agentApi）
- ✨ 增强API客户端错误处理和日志记录
- ✨ 创建API统一导出文件（index.ts）
- ✨ 编写完整的API对接指南文档
- ✨ 添加API测试示例代码
- 🐛 修复图标导入错误（RestaurantOutlined → RestOutlined）
- 🐛 修复TypeScript空值检查问题

### v1.0.0 (2026-05-22)
- ✨ 初始版本发布
- ✨ 完整的前端架构搭建
- ✨ 5个核心页面实现
- ✨ Redux状态管理
- ✨ API完整对接

---

**最后更新**: 2026-05-24  
**版本**: v1.1.0  
**API文档**: [查看完整API文档](./docs/API对接指南.md)
