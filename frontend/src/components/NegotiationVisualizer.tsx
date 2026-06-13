/**
 * 协商全流程可视化面板
 *
 * 功能：
 * 1. 进度条（阶段 + 百分比）
 * 2. 动画地图路线预览动画（高德 overlays）
 * 3. 效用轨迹图（ECharts 散点图）
 * 4. 可滚动路线时间轴（事件日志）
 * 5. 回放控制（播放/暂停/步进/倍速）
 *
 * 使用方式（在 ItineraryDetail 中使用）：
 *
 *   // 从 itinerary 数据中提取事件
 *   const events = extractEventsFromItinerary(itinerary);
 *
 *   <NegotiationVisualizer
 *     events={events}
 *     map={mapInstance}  // 可选，传入高德地图实例
 *   />
 *
 * 传统降级：当 events 为空时，显示旧版纯进度条
 */
import React, { useEffect, useMemo, useCallback, useState, useRef } from 'react';
import { Card, Collapse, Space, Typography, Empty, Button, Slider, Switch, Tag, Select, Tooltip, Popover } from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StepForwardOutlined,
  ReloadOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  SwapOutlined,
  RiseOutlined,
  FallOutlined,
  MinusOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import type { RootState, AppDispatch } from '../store';
import {
  setEvents,
  resetNegotiation,
  startReplay,
  stopReplay,
  nextReplayEvent,
  seekReplay,
  setReplaySpeed,
} from '../store/slices/negotiationSlice';
import NegotiationProgressBar from './NegotiationProgressBar';
import ScrollableRouteTimeline from './ScrollableRouteTimeline';
import UtilityTrajectoryChart from './UtilityTrajectoryChart';
import NegotiationMapOverlay from './NegotiationMapOverlay';
import type { NegotiationEvent, NegotiationEventType } from '../types/negotiation';
import { EVENT_TYPE_CN } from '../types/negotiation';
import NegotiationAdjustmentSummary from './NegotiationAdjustmentSummary';

const { Panel } = Collapse;
const { Text } = Typography;

interface NegotiationVisualizerProps {
  /** 从 itinerary 中提取的协商事件 */
  events?: NegotiationEvent[];
  /** 高德地图实例（传入则显示路线图层） */
  map?: any;
  /** 是否展示完整面板 */
  showFullPanel?: boolean;
}

/** 事件类型选项（用于筛选器） */
const EVENT_TYPES_LIST: NegotiationEventType[] = ['CFP', 'PROPOSE', 'COUNTER', 'ACCEPT', 'REJECT', 'ROLLBACK', 'FINALIZED', 'AGENT_MSG'];
const EVENT_TYPE_OPTIONS = EVENT_TYPES_LIST.map(type => ({
  value: type,
  label: `${EVENT_TYPE_CN[type] || type} (${type})`,
}));

const NegotiationVisualizer: React.FC<NegotiationVisualizerProps> = ({
  events: propEvents,
  map,
  showFullPanel = true,
}) => {
  const dispatch = useDispatch<AppDispatch>();
  const negotiationState = useSelector((state: RootState) => state.negotiation);

  const [overlayVisible, setOverlayVisible] = useState(true);
  const [filterEventTypes, setFilterEventTypes] = useState<NegotiationEventType[]>([]);
  const replayTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // 追踪当前已处理的 sessionId，避免竞态
  const currentSessionRef = useRef<string | null>(null);
  // 追踪事件长度的基准，用于增量更新判断
  const prevEventLengthRef = useRef<number>(0);

  // 初始化：将 propEvents 同步到 Redux（无竞态）
  useEffect(() => {
    if (!propEvents || propEvents.length === 0) return;

    const newSessionId = propEvents[0]?.sessionId;
    const currentSessionId = currentSessionRef.current;
    const prevLength = prevEventLengthRef.current;

    // 检测是否为全新的协商会话
    const isNewSession =
      newSessionId &&
      currentSessionId &&
      newSessionId !== currentSessionId;

    if (isNewSession) {
      // 全新会话：先记录 sessionId，再使用原子操作重置并设置
      currentSessionRef.current = newSessionId;
      prevEventLengthRef.current = propEvents.length;
      dispatch(resetNegotiation());
      // 使用 queueMicrotask 替代 setTimeout(0)，更可靠
      queueMicrotask(() => dispatch(setEvents(propEvents)));
    } else if (prevLength === 0) {
      // 首次加载
      currentSessionRef.current = newSessionId || null;
      prevEventLengthRef.current = propEvents.length;
      dispatch(setEvents(propEvents));
    } else if (propEvents.length > prevLength) {
      // 轮询更新：有新的数据追加
      prevEventLengthRef.current = propEvents.length;
      dispatch(setEvents(propEvents));
    }
  }, [propEvents, dispatch]);

  // 回放定时器
  useEffect(() => {
    if (negotiationState.isReplaying) {
      const delay = 1500 / negotiationState.replaySpeed; // 基础间隔 1.5s
      replayTimerRef.current = setInterval(() => {
        dispatch(nextReplayEvent() as any);
      }, delay);
    } else {
      if (replayTimerRef.current) {
        clearInterval(replayTimerRef.current);
        replayTimerRef.current = null;
      }
    }

    return () => {
      if (replayTimerRef.current) {
        clearInterval(replayTimerRef.current);
      }
    };
  }, [negotiationState.isReplaying, negotiationState.replaySpeed, dispatch]);

  // 当前可见事件（用于地图和时间轴）
  const visibleEvents = useMemo(() => {
    if (negotiationState.replayIndex >= 0) {
      return negotiationState.events.slice(0, negotiationState.replayIndex + 1);
    }
    return negotiationState.events;
  }, [negotiationState.events, negotiationState.replayIndex]);

  // 传统模式（无事件时降级）
  const isLegacy = negotiationState.events.length === 0;

  // 按事件类型筛选（P1 新增）
  const filteredEvents = useMemo(() => {
    if (filterEventTypes.length === 0) return negotiationState.events;
    return negotiationState.events.filter(e => filterEventTypes.includes(e.eventType));
  }, [negotiationState.events, filterEventTypes]);

  // 筛选后在原始 events 中的索引
  const replayIndexInFilter = useMemo(() => {
    if (negotiationState.replayIndex < 0 || filterEventTypes.length === 0) {
      return negotiationState.replayIndex;
    }
    // 计算在筛选后列表中的位置
    const targetEvent = negotiationState.events[negotiationState.replayIndex];
    if (!targetEvent) return -1;
    const idx = filteredEvents.findIndex(e => e.eventId === targetEvent.eventId);
    return idx;
  }, [negotiationState.replayIndex, filterEventTypes, filteredEvents, negotiationState.events]);

  // 回放控制回调
  const handleStartReplay = useCallback(() => {
    dispatch(startReplay());
  }, [dispatch]);

  const handleStopReplay = useCallback(() => {
    dispatch(stopReplay());
  }, [dispatch]);

  const handleNextStep = useCallback(() => {
    if (negotiationState.isReplaying) {
      dispatch(stopReplay());
    }
    dispatch(nextReplayEvent());
  }, [dispatch, negotiationState.isReplaying]);

  const handleReset = useCallback(() => {
    if (replayTimerRef.current) {
      clearInterval(replayTimerRef.current);
    }
    dispatch(stopReplay());
    dispatch(seekReplay(-1));
  }, [dispatch]);

  const handleSpeedChange = useCallback(
    (value: number) => {
      dispatch(setReplaySpeed(value));
    },
    [dispatch]
  );

  const handleTimelineEventClick = useCallback(
    (_event: NegotiationEvent, index: number) => {
      if (negotiationState.isReplaying) {
        dispatch(stopReplay());
      }
      dispatch(seekReplay(index));
    },
    [dispatch, negotiationState.isReplaying]
  );

  // ===== 协商摘要数据计算 =====
  const summaryData = useMemo(() => {
    const events = negotiationState.events;
    if (!events || events.length === 0) return null;

    const totalAdjustments = events.reduce(
      (sum, e) => sum + (e.adjustments?.length || 0), 0
    );

    // 计算迭代轮数：按 FINALIZED / COUNTER 事件推断
    const counterCount = events.filter(e => e.eventType === 'COUNTER').length;
    const iterations = Math.max(counterCount, 1);

    // 获取首尾效用值，判断变化趋势
    const firstUtility = events.find(e => e.utility?.dispatcher !== undefined)?.utility;
    const lastUtility = [...events].reverse().find(e => e.utility?.dispatcher !== undefined)?.utility;

    let dispatchTrend: 'up' | 'down' | 'flat' = 'flat';
    let vehicleTrend: 'up' | 'down' | 'flat' = 'flat';
    if (firstUtility && lastUtility) {
      if (lastUtility.dispatcher! > firstUtility.dispatcher! + 0.01) dispatchTrend = 'up';
      else if (lastUtility.dispatcher! < firstUtility.dispatcher! - 0.01) dispatchTrend = 'down';
      if (lastUtility.vehicle! > firstUtility.vehicle! + 0.01) vehicleTrend = 'up';
      else if (lastUtility.vehicle! < firstUtility.vehicle! - 0.01) vehicleTrend = 'down';
    }

    // 事件类型计数
    const typeCounts: Record<string, number> = {};
    events.forEach(e => {
      typeCounts[e.eventType] = (typeCounts[e.eventType] || 0) + 1;
    });

    // 总耗时（P2 新增）
    let totalDuration: string | null = null;
    if (events.length >= 2) {
      const firstTs = events[0].timestamp;
      const lastTs = events[events.length - 1].timestamp;
      const diffMs = lastTs - firstTs;
      if (diffMs > 0) {
        const seconds = Math.floor(diffMs / 1000);
        if (seconds < 60) {
          totalDuration = `${seconds}秒`;
        } else if (seconds < 3600) {
          totalDuration = `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
        } else {
          totalDuration = `${Math.floor(seconds / 3600)}时${Math.floor((seconds % 3600) / 60)}分`;
        }
      }
    }

    // 成功/失败状态
    const hasFinalized = events.some(e => e.eventType === 'FINALIZED');
    const hasReject = events.some(e => e.eventType === 'REJECT');
    const status = hasFinalized ? 'success' : hasReject ? 'fail' : 'in_progress';

    return {
      totalEvents: events.length,
      totalAdjustments,
      iterations,
      firstDispatcher: firstUtility?.dispatcher,
      lastDispatcher: lastUtility?.dispatcher,
      firstVehicle: firstUtility?.vehicle,
      lastVehicle: lastUtility?.vehicle,
      dispatchTrend,
      vehicleTrend,
      typeCounts,
      totalDuration,
      status,
    };
  }, [negotiationState.events]);

  return (
    <Card
      size="small"
      title={
        <Space>
          <ClockCircleOutlined />
          <Text strong>协商过程可视化</Text>
          {!isLegacy && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              ({negotiationState.events.length} 个事件)
            </Text>
          )}
          <Popover
            title="使用说明"
            content={
              <div style={{ fontSize: 12, lineHeight: 1.8, maxWidth: 260 }}>
                <div>▶ <strong>播放/暂停</strong>：自动回放协商全过程</div>
                <div>⏭ <strong>步进</strong>：手动逐条查看事件</div>
                <div>🔄 <strong>重置</strong>：回到起点</div>
                <div>🕐 <strong>点击事件</strong>：跳转到对应时间点</div>
                <div>🔍 <strong>筛选器</strong>：按事件类型过滤</div>
              </div>
            }
            trigger="click"
            placement="bottom"
          >
            <QuestionCircleOutlined style={{ fontSize: 14, color: 'var(--ink-light, #8a7a70)', cursor: 'pointer' }} />
          </Popover>
        </Space>
      }
      style={{ marginBottom: 16 }}
    >
      {/* ===== 1. 进度条 ===== */}
      <NegotiationProgressBar
        percent={negotiationState.progress.overallPercent}
        phase={negotiationState.progress.currentPhase}
        activeAgents={negotiationState.progress.activeAgents}
        summary={negotiationState.progress.latestSummary}
        status={
          negotiationState.progress.currentPhase === 'FINALIZED'
            ? 'success'
            : 'active'
        }
        legacy={isLegacy}
        showDetail={!isLegacy}
      />

      {/* ===== 2. 完整面板内容 ===== */}
      {!isLegacy && showFullPanel && (
        <>
          {/* 回放控制栏 */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '8px 0',
              borderTop: '1px solid var(--border-faded, #e0d8ce)',
              borderBottom: '1px solid var(--border-faded, #e0d8ce)',
              marginBottom: 12,
              flexWrap: 'wrap',
            }}
          >
            <Space size="small">
              <Button
                size="small"
                icon={
                  negotiationState.isReplaying ? (
                    <PauseCircleOutlined />
                  ) : (
                    <PlayCircleOutlined />
                  )
                }
                onClick={
                  negotiationState.isReplaying ? handleStopReplay : handleStartReplay
                }
                disabled={negotiationState.events.length === 0}
              >
                {negotiationState.isReplaying ? '暂停' : '播放'}
              </Button>

              <Button
                size="small"
                icon={<StepForwardOutlined />}
                onClick={handleNextStep}
                disabled={negotiationState.events.length === 0}
              >
                步进
              </Button>

              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={handleReset}
                disabled={negotiationState.replayIndex < 0 && !negotiationState.isReplaying}
              >
                重置
              </Button>
            </Space>

            <Space size="small">
              <Text style={{ fontSize: 12 }}>速度:</Text>
              <Slider
                min={0.5}
                max={4}
                step={0.5}
                value={negotiationState.replaySpeed}
                onChange={handleSpeedChange}
                style={{ width: 80 }}
                tooltip={{ formatter: (v) => `${v}x` }}
              />
              <Text style={{ fontSize: 12, minWidth: 30 }}>
                {negotiationState.replaySpeed}x
              </Text>
            </Space>

            {map && (
              <Space size="small">
                <Text style={{ fontSize: 12 }}>路线图层:</Text>
                <Switch
                  checkedChildren={<EyeOutlined />}
                  unCheckedChildren={<EyeInvisibleOutlined />}
                  checked={overlayVisible}
                  onChange={setOverlayVisible}
                  size="small"
                />
              </Space>
            )}

            <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>
              {negotiationState.replayIndex >= 0
                ? `${negotiationState.replayIndex + 1} / ${negotiationState.events.length}`
                : `${negotiationState.events.length} 个事件`}
            </Text>
          </div>

          {/* ===== 协商摘要卡片（P1 新增） ===== */}
          {summaryData && (
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 8,
                padding: '8px 12px',
                marginBottom: 10,
                background: 'var(--paper-warm, #f0e8da)',
                border: '1px solid var(--border-faded, #e0d8ce)',
              }}
            >
              {/* 事件总数 */}
              <Tooltip title="协商过程中产生的总事件数">
                <Text style={{ fontSize: 12 }}>
                  <ClockCircleOutlined style={{ marginRight: 4, color: 'var(--stamp-blue, #4a7a8c)' }} />
                  事件: <Text strong>{summaryData.totalEvents}</Text>
                </Text>
              </Tooltip>

              {/* 调整项数 */}
              {summaryData.totalAdjustments > 0 && (
                <Tooltip title="字段级调整总数（before → after）">
                  <Text style={{ fontSize: 12 }}>
                    <SwapOutlined style={{ marginRight: 4, color: 'var(--stamp-red, #c45a4a)' }} />
                    调整: <Text strong>{summaryData.totalAdjustments}</Text>
                  </Text>
                </Tooltip>
              )}

              {/* 迭代轮数 */}
              <Tooltip title="协商迭代轮数（基于反提案次数估算）">
                <Text style={{ fontSize: 12 }}>
                  <ReloadOutlined style={{ marginRight: 4, color: 'var(--ink-light, #8a7a70)' }} />
                  迭代: <Text strong>{summaryData.iterations}</Text> 轮
                </Text>
              </Tooltip>

              {/* 调度效用变化趋势 */}
              {summaryData.firstDispatcher !== undefined && summaryData.lastDispatcher !== undefined && (
                <Tooltip title={`调度效用: ${summaryData.firstDispatcher.toFixed(2)} → ${summaryData.lastDispatcher.toFixed(2)}`}>
                  <Text style={{ fontSize: 12 }}>
                    {summaryData.dispatchTrend === 'up' ? (
                      <RiseOutlined style={{ color: 'var(--stamp-green, #6a8f6a)', marginRight: 2 }} />
                    ) : summaryData.dispatchTrend === 'down' ? (
                      <FallOutlined style={{ color: 'var(--stamp-red, #c45a4a)', marginRight: 2 }} />
                    ) : (
                      <MinusOutlined style={{ color: 'var(--ink-light, #8a7a70)', marginRight: 2 }} />
                    )}
                    调度: {summaryData.lastDispatcher.toFixed(2)}
                  </Text>
                </Tooltip>
              )}

              {/* 车辆效用变化趋势 */}
              {summaryData.firstVehicle !== undefined && summaryData.lastVehicle !== undefined && (
                <Tooltip title={`车辆效用: ${summaryData.firstVehicle.toFixed(2)} → ${summaryData.lastVehicle.toFixed(2)}`}>
                  <Text style={{ fontSize: 12 }}>
                    {summaryData.vehicleTrend === 'up' ? (
                      <RiseOutlined style={{ color: 'var(--stamp-green, #6a8f6a)', marginRight: 2 }} />
                    ) : summaryData.vehicleTrend === 'down' ? (
                      <FallOutlined style={{ color: 'var(--stamp-red, #c45a4a)', marginRight: 2 }} />
                    ) : (
                      <MinusOutlined style={{ color: 'var(--ink-light, #8a7a70)', marginRight: 2 }} />
                    )}
                    车辆: {summaryData.lastVehicle.toFixed(2)}
                  </Text>
                </Tooltip>
              )}

              {/* 总耗时（P2 新增） */}
              {summaryData.totalDuration && (
                <Tooltip title="协商过程总耗时">
                  <Text style={{ fontSize: 12 }}>
                    <ClockCircleOutlined style={{ marginRight: 4, color: 'var(--ink-light, #8a7a70)' }} />
                    耗时: <Text strong>{summaryData.totalDuration}</Text>
                  </Text>
                </Tooltip>
              )}

              {/* 协商状态 */}
              <Tooltip title="协商最终结果">
                <Text style={{ fontSize: 12 }}>
                  {summaryData.status === 'success' ? (
                    <Tag color="green" style={{ fontSize: 10, margin: 0 }}>协商成功</Tag>
                  ) : summaryData.status === 'fail' ? (
                    <Tag color="red" style={{ fontSize: 10, margin: 0 }}>协商失败</Tag>
                  ) : (
                    <Tag color="processing" style={{ fontSize: 10, margin: 0 }}>进行中</Tag>
                  )}
                </Text>
              </Tooltip>
            </div>
          )}

          {/* ===== 事件类型筛选器（P1 新增） ===== */}
          <div style={{ marginBottom: 8 }}>
            <Select
              mode="multiple"
              allowClear
              placeholder="筛选事件类型（默认全部）"
              value={filterEventTypes}
              onChange={setFilterEventTypes}
              size="small"
              style={{ minWidth: 200 }}
              options={EVENT_TYPE_OPTIONS}
            />
          </div>

          {/* 折叠面板：默认只展开时间轴，其他收起以减少信息过载 */}
          <Collapse
            defaultActiveKey={['timeline']}
            size="small"
            ghost
            style={{ margin: 0 }}
          >
            {/* 时间轴 */}
            <Panel
              header={
                <Space>
                  <ClockCircleOutlined />
                  <Text>事件时间轴</Text>
                  {filterEventTypes.length > 0 && (
                    <Tag color="geekblue" style={{ fontSize: 10 }}>
                      已筛选 {filteredEvents.length} 个
                    </Tag>
                  )}
                </Space>
              }
              key="timeline"
            >
              <ScrollableRouteTimeline
                events={filteredEvents}
                replayIndex={replayIndexInFilter}
                onEventClick={(event, _idxInFilter) => {
                  // 将筛选后的索引映射到原始索引
                  const originalIdx = negotiationState.events.findIndex(
                    (e) => e.eventId === event.eventId
                  );
                  if (originalIdx >= 0) {
                    handleTimelineEventClick(event, originalIdx);
                  }
                }}
              />
            </Panel>

            {/* 调整详情汇总 */}
            <Panel
              header={
                <Space>
                  <SwapOutlined />
                  <Text>调整详情汇总</Text>
                  {summaryData && summaryData.totalAdjustments > 0 && (
                    <Tag color="geekblue" style={{ fontSize: 11 }}>
                      {summaryData.totalAdjustments} 项变更
                    </Tag>
                  )}
                </Space>
              }
              key="adjustments"
            >
              <NegotiationAdjustmentSummary
                events={negotiationState.events}
                onEventClick={handleTimelineEventClick}
              />
            </Panel>

            {/* 效用轨迹图 */}
            <Panel
              header={
                <Space>
                  <BarChartOutlined />
                  <Text>效用轨迹图</Text>
                </Space>
              }
              key="utility"
            >
              <UtilityTrajectoryChart
                events={visibleEvents}
                title="协商效用轨迹"
              />
            </Panel>
          </Collapse>
        </>
      )}

      {/* ===== 3. 地图路线图层（叠加） ===== */}
      {map && !isLegacy && (
        <NegotiationMapOverlay
          map={map}
          events={negotiationState.events}
          visible={overlayVisible}
          replayIndex={negotiationState.replayIndex}
        />
      )}

      {/* 空状态 */}
      {isLegacy && !negotiationState.events.length && (
        <Empty
          description="暂无协商事件数据"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ marginTop: 8 }}
        />
      )}
    </Card>
  );
};

export default NegotiationVisualizer;
