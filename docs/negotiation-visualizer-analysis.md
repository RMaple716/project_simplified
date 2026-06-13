# 协商过程可视化组件 — 现状分析与改进建议

> 文档日期：2025年  
> 分析范围：前端协商可视化全链路  
> 涉及文件：`NegotiationVisualizer.tsx`、`NegotiationProgressBar.tsx`、`NegotiationAdjustmentSummary.tsx`、`NegotiationMapOverlay.tsx`、`UtilityTrajectoryChart.tsx`、`ScrollableRouteTimeline.tsx`、`negotiationSlice.ts`、`negotiation.ts`、`negotiationApi.ts`、`ItineraryDetail.tsx`、`travel-theme.css`

---

## 一、整体架构概览

```
后端协商引擎 (negotiation_service.py)
  ↓ 通过 WebSocket / REST API
NegotiationEventBus (事件总线)
  ↓
negotiationApi.ts (前端 API 层)
  ↓
negotiationSlice.ts (Redux 状态管理)
  ↓
NegotiationVisualizer.tsx (主面板容器)
  ├─ NegotiationProgressBar       — 进度条
  ├─ ScrollableRouteTimeline      — 事件时间轴
  ├─ NegotiationAdjustmentSummary — 调整详情汇总
  ├─ UtilityTrajectoryChart       — 效用轨迹图
  └─ NegotiationMapOverlay        — 地图路线叠加层
```

### 前端已实现的能力

| 功能模块 | 当前状态 | 实现程度 |
|----------|----------|----------|
| 进度条显示 | ✅ 已完成 | 阶段+百分比+参与方标签 |
| 事件时间轴 | ✅ 已完成 | 可滚动+点击跳转+自动滚动 |
| 回放控制 | ✅ 已完成 | 播放/暂停/步进/倍速/重置 |
| 调整详情汇总 | ✅ 已完成 | 字段级变化 before→after 展示 |
| 效用轨迹图 | ✅ 已完成 | Canvas 自绘散点连线图+帕累托前沿 |
| 地图路线叠加 | ✅ 已完成 | 高德 API 多车辆虚线/实线路线 |
| WebSocket 实时推送 | ✅ 已完成 | 断线重连+心跳+订阅切换 |

---

## 二、各组件详细分析

### 2.1 NegotiationVisualizer.tsx — 主容器组件

#### ✅ 优点
1. **组件职责清晰**：将进度条、时间轴、效用图、地图叠加层、调整汇总等子组件合理拆分
2. **降级处理完善**：无事件时显示旧版纯进度条 + Empty 空状态
3. **回放控制完整**：播放/暂停/步进/倍速/重置，用 Redux 管理回放状态
4. **Redux 集成合理**：将 propEvents 同步到 Redux store，轮询时只追加新事件
5. **新旧会话检测**：通过 sessionId 判断是否为全新协商会话，支持重置

#### ❌ 不足之处

##### 问题 1：面板与行程页面脱节
- 在 `ItineraryDetail.tsx` 中，`NegotiationVisualizer` 被放在每日行程时间轴**之后**，用户需要滚动到页面最底部才能看到协商过程
- 协商可视化应该是**行程生成的"幕后故事"**，当前展示位置不直观
- **建议**：将协商面板放在行程详情顶部，或作为折叠面板默认展开的第一项

```tsx
// ItineraryDetail.tsx (当前)
// ... 每日行程安排 ...
<NegotiationVisualizer events={...} />  // ← 在页面底部，容易被忽略
```

##### 问题 2：事件同步逻辑有竞态风险
```typescript
// NegotiationVisualizer.tsx 中
if (isNewSession) {
  dispatch(resetNegotiation());
  setTimeout(() => dispatch(setEvents(propEvents)), 0); // ← setTimeout(0) 脆弱依赖
}
```
- 使用 `setTimeout(0)` 等待 Redux 状态更新，这是脆弱的竞态处理方式
- 如果 Redux dispatch 同步执行，reset 后的 setEvents 可能不会正确覆盖

##### 问题 3：缺少加载状态和错误边界
- 组件没有加载中（Skeleton）或错误状态（ErrorBoundary）的展示
- 当 WebSocket 连接失败或事件数据异常时，用户看不到任何反馈

##### 问题 4：所有子面板默认全部展开，信息过载
```tsx
<Collapse defaultActiveKey={['timeline', 'utility']} ...>
```
- 时间轴、调整详情、效用图默认全部展开，对于首次使用的用户来说信息密度过高
- 用户打开页面时看到大量信息，缺乏渐进式引导

---

### 2.2 NegotiationProgressBar.tsx — 进度条组件

#### ✅ 优点
1. **双模式支持**：有事件时显示详细模式（阶段+参与方+摘要），无事件时降级为纯百分比
2. **丰富的视觉元素**：阶段图标、颜色编码、参与方标签
3. **中文映射完善**：`PHASE_MAP_CN` 提供完整的中文阶段描述

#### ❌ 不足之处

##### 问题 5：进度计算与实际流程不符
进度值来自 `negotiationSlice.ts` 中的估算：
```typescript
const [minP, maxP] = PHASE_PROGRESS_RANGE[phase] || [0, 100];
const phasePercent = minP + (maxP - minP) * Math.min(idx / totalEstimate, 1);
state.progress.overallPercent = Math.round(phasePercent);
```
- 进度只是**根据事件数量的线性估算**，不是基于实际完成的工作量
- 例如：2次反提案和10次反提案都落在 `NEGOTIATE` 阶段（40%-80%），进度不能反映真实进展
- **用户看到的 60% 可能是 3 个事件，也可能是一百个事件**

##### 问题 6：缺少进度时间预估
- 没有显示预估剩余时间或已用时间
- 对于长时间运行的协商过程，用户无法判断还需要等多久

##### 问题 7：缺少"执行失败/回退"状态
- 进度条状态只有 `active | exception | success | normal` 四种
- 没有表示"协商回退到上一步"或"策略失败后切换方案"的状态变化

---

### 2.3 ScrollableRouteTimeline.tsx — 事件时间轴

#### ✅ 优点
1. **交互友好**：支持点击跳转到指定事件，当前事件高亮
2. **信息丰富**：事件类型、时间、参与方、阶段、提案信息、效用值、价格均有展示
3. **自动滚动**：新事件到达时自动滚动到底部
4. **索引偏移提示**：显示"前面还有 N 个事件..."

#### ❌ 不足之处

##### 问题 8：时间轴性能问题
- `maxItems = 50` 限制显示数量，但 `displayEvents = events.slice(-maxItems)` 会截断早期事件
- 当事件数量较多时（如 200+），用户无法查看完整的协商历史
- **建议**：添加"加载更多"或分页机制，而不是静默截断

##### 问题 9：调整详情展示在时间轴中显得拥挤
- 每个时间轴条目中同时展示了：事件类型标签、时间、参与方、阶段、提案信息、调整详情列表、效用值、价格
- 单条信息过长，特别是有多个 `adjustments` 时，可读性下降
- **建议**：将调整详情折叠在事件条目内，默认收起

##### 问题 10：缺少状态过滤功能
- 用户无法按事件类型（如只查看 ACCEPT/REJECT）或按参与方过滤
- 所有事件混在一起展示，当事件数量多时查找特定事件困难
- **建议**：添加筛选器 + 搜索功能

##### 问题 11：颜色对比度问题
- 非当前事件统一使用灰色（`color: 'gray'`），区分度不够
- `ACCEPT`（绿色）和 `FINALIZED`（青色）颜色接近，容易混淆

---

### 2.4 NegotiationAdjustmentSummary.tsx — 调整详情汇总

#### ✅ 优点
1. **清晰的 before→after 对比**：红色删除线表示旧值，绿色表示新值，箭头连接
2. **字段级变化展示**：显示哪个字段、哪个项目被调整
3. **按策略分组**：通过事件中的 `strategy` 字段展示采用的策略名

#### ❌ 不足之处

##### 问题 12：缺少变更量的数值对比
- 例如"游览时间：2小时 → 1.5小时"，但没显示变化量（"-30分钟"）
- **建议**：添加差值/变化百分比标签
- **建议**：对数值变化添加颜色渐变（大幅变化红色→小幅变化黄色→无变化绿色）

##### 问题 13：缺少"接受/拒绝"交互
- 当前只是静态展示，用户无法对调整做出反馈
- **用户无法**："我不接受这个调整，换一种方案"
- 尽管后端可能还未支持，但前端可以先预置交互框架

##### 问题 14：调整事件的点击跳转行为有 Bug
```typescript
onClick={() => onEventClick?.(event, eventIdx)}
```
- 注意这里传入的是 `eventIdx`（adjustmentEvents 中的索引），而不是原始 events 中的索引
- 当用户点击调整汇总中的事件时，时间轴会跳转到错误的索引位置
- **这是数据源的索引不一致 Bug**

---

### 2.5 UtilityTrajectoryChart.tsx — 效用轨迹图

#### ✅ 优点
1. **零外部依赖**：纯 Canvas 实现，不依赖 ECharts/Chart.js
2. **高 DPI 支持**：正确处理 `devicePixelRatio`
3. **视觉完整**：坐标轴、刻度标签、网格线、图例、箭头、帕累托前沿一应俱全
4. **响应式**：监听窗口大小变化自动重绘

#### ❌ 不足之处

##### 问题 15：Canvas 实现限制交互性
- 纯 Canvas 绘图意味着没有 hover 提示、点击交互、缩放、区域选择
- 用户无法悬停查看某个点的具体效用数值
- **建议**：至少添加 `onMouseMove` 坐标拾取和 tooltip 显示
- **建议**：考虑降级到 SVG 或使用轻量图表库（如 uPlot）以获得交互能力

##### 问题 16："帕累托前沿"标注可能误导
- 当前算法只是简单排序后的"右上角包络线"，并非严格意义上的帕累托前沿
```typescript
const sorted = [...chartData].sort((a, b) => b.dispatcher - a.dispatcher);
// 只取了 dispatcher 降序，然后找 vehicle 递增的点
```
- 当数据点较少时（<5），"帕累托前沿"的学术化标注显得夸大其词
- **建议**：点数量少于 5 时不显示帕累托前沿标签

##### 问题 17：缺少效用值变化趋势指示器
- 只展示了散点位置，没有展示效用值的变化趋势（单调递增/递减/波动）
- **建议**：添加整体趋势标注，如"调度效用稳步上升 ↗"或"车辆效用波动 📊"

##### 问题 18：坐标轴范围固定为 0-1
- 当前所有效用值都被映射到 [0,1] 区间
- 如果实际效用值分布范围较窄（如都在 0.6-0.8 之间），图表展示空间浪费
- **建议**：根据数据实际范围动态调整坐标轴刻度

##### 问题 19：Canvas 重绘无防抖
```typescript
window.addEventListener('resize', handleResize);
```
- `resize` 事件高频触发时，`requestAnimationFrame` 被不断调用
- 虽然有 `cancelAnimationFrame`，但连续 resize 仍会导致不必要的重绘
- **建议**：添加 debounce（200ms）

---

### 2.6 NegotiationMapOverlay.tsx — 地图路线叠加层

#### ✅ 优点
1. **完整的生命周期管理**：创建、更新、清除路线图层
2. **状态驱动的路线样式**：虚线（提案中）→ 实线（已接受）
3. **多车辆支持**：不同车辆用不同颜色区分
4. **价格标签**：在路线终点显示 proposal 价格

#### ❌ 不足之处

##### 问题 20：强依赖 AMap 全局变量
```typescript
if (!layerGroupRef.current && window.AMap) {
  layerGroupRef.current = new (window as any).AMap.LayerGroup();
}
```
- 所有代码使用 `(window as any).AMap`，类型不安全
- 高德地图 SDK 是异步加载的，可能出现 `window.AMap` 尚未准备好的情况
- **建议**：通过 prop 或 context 传入地图构造函数，避免全局变量依赖

##### 问题 21：地图颜色方案与主题不一致
- `DEFAULT_COLORS` 使用高饱和色（`#FF5733`、`#33B5FF` 等），与手工感主题（`travel-theme.css`）的"褪色墨水"风格不协调
- **建议**：使用主题色板中的 `stamp-red`、`stamp-blue`、`stamp-green` 等颜色

##### 问题 22：缺少路线动画
- 当前路线是静态展示，没有"协商→接受"过程的动画过渡
- 用户体验上，路线从虚线变为实线时应该有平滑动画
- **建议**：使用 Canvas 或 AMap 的动画 API 实现路径生长动画

##### 问题 23：路线清理时机不精确
```typescript
useEffect(() => {
  return () => {
    cancelAnimationFrame(animFrameRef.current);
    clearAllRoutes();  // 组件卸载时清理
  };
}, [clearAllRoutes]);
```
- 依赖 `clearAllRoutes`（通过 `useCallback` 生成），但该函数引用了 `layerGroupRef`
- 在组件卸载时，如果 `layerGroupRef` 已经被置空，清理可能无效

---

### 2.7 negotiationSlice.ts — 状态管理

#### ✅ 优点
1. **完整的状态覆盖**：进度、事件列表、回放状态、速度
2. **摘要生成**：`generateSummary` 函数根据事件类型生成中文摘要
3. **进度估算**：基于阶段范围 + 事件位置估算百分比

#### ❌ 不足之处

##### 问题 24：进度状态与回放状态耦合
- `replayIndex = -1` 表示非回放模式，但同时也用于 `visibleEvents` 的计算
- 当用户手动查看特定事件时（非回放模式），`replayIndex` 被修改，影响了回放逻辑

##### 问题 25：缺少数据验证和错误处理
- `addEvent` 和 `setEvents` 没有对事件数据进行校验
- 如果后端返回了格式异常的事件（如缺少 `eventType`），前端会直接崩溃或显示异常

---

### 2.8 与手工感主题（travel-theme.css）的兼容性

#### ❌ 不足之处

##### 问题 26：可视化组件未使用主题样式
- `NegotiationVisualizer` 及其子组件大量使用内联样式（`style={{...}}`），绕过了 CSS 主题系统
- 例如：进度条颜色 `#108ee9`、`#87d068` 是 Ant Design 默认色，而非主题的 `stamp-blue`、`stamp-green`
- **结果**：协商面板的视觉风格与整体页面（手工感/旧纸张）脱节

##### 问题 27：Canvas 效用图与主题不匹配
- `UtilityTrajectoryChart` 使用硬编码颜色：`LINE_COLOR = '#1890ff'`、`FINAL_COLOR = '#52c41a'`
- 这些是 Ant Design 默认蓝色和绿色，而非主题色板中的色彩
- 主题目标是"旧地图美学"，而效用图呈现的是"科技感图表"，风格冲突

---

## 三、用户体验（UX）层面的问题

### 3.1 信息架构问题

##### 问题 28：缺少"协商概述"面板
- 用户打开页面时，看到的是时间轴、调整详情、效用图三个并列面板，缺少一个**高层概述**
- 应该有一块区域回答：**"这次协商改了什么？改了多少次？最终比初始好在哪里？"**

##### 问题 29：视觉层级不够清晰
- 进度条 → 回放控制栏 → 折叠面板（时间轴/调整详情/效用图），所有内容平铺
- 用户无法直观区分"最重要的信息"和"次要的细节"

### 3.2 交互问题

##### 问题 30：回放功能缺少使用引导
- 回放控制栏（播放/暂停/步进/倍速）没有使用说明
- 新用户可能不知道拖动时间轴事件可以跳转，或者播放按钮可以看动画

##### 问题 31：缺少协商过程的时间统计
- 没有显示协商的总耗时、迭代轮数、成功/失败率等关键指标

---

## 四、改进建议汇总及优先级

| 优先级 | 问题编号 | 问题描述 | 建议方案 | 工作量 |
|--------|----------|----------|----------|--------|
| 🔴 **P0** | 问题 2 | 事件同步竞态 | 用 `useEffect` 监听 `propEvents` 变化，统一在 effect 中处理 | 小 |
| 🔴 **P0** | 问题 12 | 调整详情索引 Bug | 修正 `onEventClick` 中的索引映射 | 小 |
| 🔴 **P0** | 问题 26 | 主题不一致 | 将硬编码颜色替换为 CSS 变量或主题色 | 中 |
| 🔴 **P0** | 问题 1 | 面板位置不佳 | 将协商可视化移到行程详情顶部区域 | 小 |
| 🟡 **P1** | 问题 5 | 进度估算不准 | 后端返回真实进度，或基于策略执行轮数计算 | 中 |
| 🟡 **P1** | 问题 15 | Canvas 无交互 | 添加鼠标 hover tooltip + 点击显示详情 | 中 |
| 🟡 **P1** | 问题 8 | 时间轴截断 | 改为虚拟滚动或分页加载 | 中 |
| 🟡 **P1** | 问题 4 | 信息过载 | 默认只展开时间轴，其他面板收起 | 小 |
| 🟡 **P1** | 问题 28 | 缺少概述 | 添加"协商摘要"卡片：改动项数、迭代轮数、满意度变化 | 中 |
| 🟡 **P1** | 问题 10 | 缺少过滤 | 添加事件类型筛选器 + 关键词搜索 | 中 |
| 🟢 **P2** | 问题 6 | 缺时间预估 | 后端返回预估轮数/时间，前端展示 | 小 |
| 🟢 **P2** | 问题 7 | 缺回退状态 | 增加 `ROLLBACK` 事件类型和对应 UI | 小 |
| 🟢 **P2** | 问题 12 | 缺变更量 | 添加差值/变化百分比展示 | 小 |
| 🟢 **P2** | 问题 13 | 缺用户反馈 | 预置"接受/拒绝当前调整"按钮框架 | 中 |
| 🟢 **P2** | 问题 16 | 帕累托前沿 | 数据点少于 5 时不显示该标注 | 小 |
| 🟢 **P2** | 问题 17 | 缺趋势指示 | 添加效用变化趋势文本标注 | 小 |
| 🟢 **P2** | 问题 18 | 坐标轴固定 | 根据数据范围动态计算坐标轴刻度 | 小 |
| 🟢 **P2** | 问题 19 | 重绘无防抖 | 添加 debounce(200ms) | 小 |
| 🟢 **P2** | 问题 20 | 全局变量依赖 | 通过 props 注入地图构造函数 | 中 |
| 🟢 **P2** | 问题 21 | 地图颜色 | 使用主题色板色值 | 小 |
| 🟢 **P2** | 问题 22 | 路线动画 | 添加路径生长动画 | 中 |
| 🟢 **P2** | 问题 27 | 图表颜色 | 使用主题色板色值 | 小 |
| 🟢 **P2** | 问题 29 | 视觉层级 | 重新设计面板布局，突出关键信息 | 中 |
| 🟢 **P2** | 问题 30 | 回放引导 | 添加首次使用引导提示或 Tooltip | 小 |
| 🟢 **P2** | 问题 31 | 缺统计指标 | 添加协商过程统计展示 | 小 |

---

## 五、关键改进建议详述

### 5.1 🔴 建议一：修复事件同步竞态（P0）

**问题**：`setTimeout(0)` 脆弱依赖

**建议方案**：改用 Redux thunk 或统一在 useEffect 中处理

```typescript
// 推荐方案：统一在 useEffect 中处理
useEffect(() => {
  if (!propEvents || propEvents.length === 0) return;
  
  const isNewSession = negotiationState.events.length > 0 &&
    propEvents[0]?.sessionId &&
    propEvents[0].sessionId !== negotiationState.events[0]?.sessionId;

  if (isNewSession) {
    dispatch(resetAndSetEvents(propEvents)); // 使用 thunk 原子化操作
  } else if (propEvents.length > negotiationState.events.length) {
    dispatch(appendNewEvents(propEvents));
  } else if (negotiationState.events.length === 0) {
    dispatch(setEvents(propEvents));
  }
}, [propEvents?.length, propEvents?.[0]?.sessionId]);
```

### 5.2 🔴 建议二：主题颜色对齐（P0）

**问题**：硬编码的 Ant Design 默认色与手工感主题脱节

**建议方案**：使用 CSS 变量或 theme token

```typescript
// 在 NegotiationProgressBar.tsx 中
const PHASE_COLORS = {
  INIT: 'var(--ink-light, #8a7a70)',
  CFP: 'var(--stamp-blue, #4a7a8c)',
  BIDDING: 'var(--stamp-blue, #4a7a8c)',
  NEGOTIATE: 'var(--stamp-red, #c45a4a)',
  FINALIZING: 'var(--stamp-green, #6a8f6a)',
  FINALIZED: 'var(--stamp-green, #6a8f6a)',
};
```

### 5.3 🟡 建议三：添加"协商摘要"概览面板（P1）

**当前缺失**：用户看不到对协商过程的全局理解

**建议方案**：在折叠面板顶部添加一个摘要行

```
┌─ 协商摘要 ──────────────────────────────────┐
│  📊 迭代 3 轮  │  🔄 调整 12 项  │  ✅ 全部解决 │
│  调度效用: 0.52 → 0.85 ↗  车辆效用: 0.48 → 0.72 ↗ │
│  主要策略: 时间平移(4次) 时段交换(2次) 时长压缩(3次) │
└──────────────────────────────────────────────┘
```

### 5.4 🟡 建议四：Canvas 效用图增加交互（P1）

**问题**：纯展示无法交互

**建议方案**：在 Canvas 上层添加透明 div 做事件捕获

```typescript
// 添加 onMouseMove 处理
const handleMouseMove = useCallback((e: React.MouseEvent) => {
  const rect = canvasRef.current?.getBoundingClientRect();
  if (!rect) return;
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  // 计算最近的数据点
  const nearestPoint = findNearestPoint(x, y, chartData);
  if (nearestPoint) {
    setTooltip({ ...nearestPoint, x: e.clientX, y: e.clientY });
  }
}, [chartData]);
```

### 5.5 🟡 建议五：添加事件筛选与搜索（P1）

**问题**：时间轴事件无法筛选

**建议方案**：在时间轴面板头部添加筛选器

```tsx
<div style={{ marginBottom: 8 }}>
  <Select
    mode="multiple"
    placeholder="筛选事件类型"
    onChange={handleTypeFilter}
    size="small"
    style={{ minWidth: 160, marginRight: 8 }}
  >
    {EVENT_TYPES.map(type => (
      <Option key={type} value={type}>
        {EVENT_TYPE_CN[type]} ({counts[type]})
      </Option>
    ))}
  </Select>
  {/* 参与方筛选、搜索框等 */}
</div>
```

---

## 六、总结

### 总体评价

前端协商可视化组件在**功能完整性**上已经做得相当不错：
- 6 个子组件覆盖了进度展示、事件回溯、调整详情、效用分析、地图预览等维度
- 回放控制（播放/暂停/步进/倍速）提供了良好的过程演示体验
- Redux 状态管理合理，事件同步机制基本可用
- WebSocket 客户端支持断线重连和心跳保持

### 最需要优先改进的 3 个方面

| 排名 | 改进项 | 理由 |
|------|--------|------|
| 1️⃣ | **修复事件同步竞态和索引 Bug** | 代码正确性是基础，当前存在潜在崩溃风险 |
| 2️⃣ | **统一视觉风格到手工感主题** | 多处硬编码颜色与 `travel-theme.css` 风格冲突，影响整体质感 |
| 3️⃣ | **添加协商概述面板 + 改善信息架构** | 用户需要"概览→细节"的渐进式信息获取路径，而非平铺所有数据 |

### 未来展望

随着后端协商引擎向**真正的多智能体协商**演进（Agent 间双向通信、LLM 仲裁、效用最大化博弈），前端可视化也需要相应升级：
- **Agent 对话气泡视图**：展示 Agent 间的消息流通
- **多方案对比面板**：同时展示多个候选方案
- **效用变化瀑布图**：展示每轮协商的效用增益来源
- **实时协商热力图**：在地图上展示各方案的时空密度

---

*本文档基于对 `frontend/src/components/`、`frontend/src/store/slices/negotiationSlice.ts`、`frontend/src/types/negotiation.ts`、`frontend/src/services/negotiationApi.ts`、`frontend/src/pages/ItineraryDetail.tsx`、`frontend/src/styles/travel-theme.css` 的全面代码分析生成。*
