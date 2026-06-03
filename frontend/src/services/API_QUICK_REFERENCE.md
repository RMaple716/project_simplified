# API快速参考卡片

## 🚀 快速开始

### 1. 导入API

```typescript
import { requirementApi, taskApi, itineraryApi } from '@/services';
```

### 2. 调用API

```typescript
const response = await requirementApi.submit(data);
if (response.code === 200) {
  console.log('成功:', response.data);
}
```

---

## 📦 API模块速查

### 用户需求 (requirementApi)

```typescript
// 提交需求
await requirementApi.submit({ user_id, requirement })

// 解析需求
await requirementApi.parse(requirementId)

// 获取详情
await requirementApi.getById(requirementId)
```

### 任务管理 (taskApi)

```typescript
// 任务分解
await taskApi.decompose(requirementId, structuredRequirement)

// 查询状态
await taskApi.getById(taskId)

// 更新结果
await taskApi.update(taskId, { status, result })
```

### 行程管理 (itineraryApi)

```typescript
// 创建行程
await itineraryApi.create(itineraryData)

// 获取详情
await itineraryApi.getById(itineraryId)

// 更新行程
await itineraryApi.update(itineraryId, updates)

// 删除行程
await itineraryApi.delete(itineraryId)

// 用户行程列表
await itineraryApi.getByUser(userId)
```

### 行程校验 (validationApi)

```typescript
// 时间冲突检测
await validationApi.checkTimeConflict({ schedule })

// 完整校验
await validationApi.validateItinerary({ day_plans, structured_requirement })
```

### 静态数据 (staticDataApi)

```typescript
// 城市列表
await staticDataApi.getCities()

// 城市景点
await staticDataApi.getAttractionsByCity(cityName)

// 所有景点
await staticDataApi.getAttractions()
```

### 智能体推荐 (agentApi)

```typescript
// 景点推荐
await agentApi.getAttractions({ city_name, travel_days, preferences })

// 住宿推荐
await agentApi.getHotels({ city_name, check_in_date, nights, budget_per_night })

// 美食推荐
await agentApi.getFood({ city_name, budget_per_person, cuisine_preference })

// 交通推荐
await agentApi.getTransport({ city_name, travel_days, budget })
```

---

## 🔧 常用类型

### Requirement

```typescript
interface Requirement {
  city_name: string;
  travel_days: number;
  total_budget: number;
  travel_date: string;
  traveler_count: number;
  preferences: string[];
  travel_type?: string;
  special_needs?: string;
}
```

### Itinerary

```typescript
interface Itinerary {
  itinerary_id?: string;
  user_id: string;
  requirement_id: string;
  title?: string;
  city_name: string;
  travel_days: number;
  total_budget?: number;
  day_plans?: DayPlan[];
  status?: string;
  created_at?: string;
}
```

### Task

```typescript
interface Task {
  task_id: string;
  requirement_id: string;
  task_type: string;
  status: string;
  progress: number;
  result?: any;
}
```

---

## ⚡ 最佳实践

### ✅ 推荐做法

```typescript
// 1. 使用try-catch处理错误
try {
  const response = await api.call();
  if (response.code === 200) {
    // 成功处理
  }
} catch (error) {
  // 错误已由拦截器处理
}

// 2. 添加加载状态
const [loading, setLoading] = useState(false);
setLoading(true);
try { /* ... */ } finally { setLoading(false); }

// 3. 使用TypeScript类型
import type { Requirement } from '@/services';
const req: Requirement = { /* ... */ };

// 4. 防止重复提交
const [submitting, setSubmitting] = useState(false);
if (submitting) return;
```

### ❌ 避免做法

```typescript
// 不要忽略错误
await api.call(); // ❌

// 不要忘记清理加载状态
setLoading(true);
await api.call(); // ❌ 如果出错，loading永远是true

// 不要硬编码URL
axios.get('http://localhost:9091/api/...'); // ❌ 使用apiClient
```

---

## 🐛 常见问题

### Q: API请求失败？

**检查清单**:
- [ ] 后端服务是否启动？访问 http://127.0.0.1:9091/docs
- [ ] Vite代理配置是否正确？查看 `vite.config.ts`
- [ ] 浏览器控制台是否有错误？
- [ ] Network标签页中请求状态码是多少？

### Q: 如何查看请求详情？

打开浏览器开发者工具 → Network → 过滤XHR → 点击请求查看详情

### Q: Token如何设置？

```typescript
localStorage.setItem('token', 'your_token_here');
// API客户端会自动在请求头中添加
```

### Q: 如何自定义错误处理？

```typescript
try {
  await api.call();
} catch (error) {
  // 拦截器已显示message
  // 这里可以添加额外逻辑
  if (error.response?.status === 400) {
    // 特殊处理
  }
}
```

---

## 📖 更多资源

- 📘 [完整API文档](./API对接指南.md)
- 💻 [测试示例代码](../src/services/apiTest.ts)
- 📋 [项目README](../README.md)
- 🏗️ [架构说明](../ARCHITECTURE.md)

---

**最后更新**: 2026-05-24  
**版本**: v1.1.0
