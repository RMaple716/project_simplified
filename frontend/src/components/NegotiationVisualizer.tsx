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
import { Card, Collapse, Space, Typography, Empty, Button, Slider, Switch, Tag } from 'antd';
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
import type { NegotiationEvent } from '../types/negotiation';
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

const NegotiationVisualizer: React.FC<NegotiationVisualizerProps> = ({
  events: propEvents,
  map,
  showFullPanel = true,
}) => {
  const dispatch = useDispatch<AppDispatch>();
  const negotiationState = useSelector((state: RootState) => state.negotiation);

  const [overlayVisible, setOverlayVisible] = useState(true);
  const replayTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 初始化：将 propEvents 同步到 Redux（轮询时只追加新事件）
  useEffect(() => {
    if (propEvents && propEvents.length > 0) {
      // 检测是否为全新的协商会话：通过判断事件 sessionId 是否改变
      const isNewSession =
        negotiationState.events.length > 0 &&
        propEvents[0]?.sessionId &&
        propEvents[0].sessionId !== negotiationState.events[0]?.sessionId;

      if (isNewSession) {
        // 全新会话：先重置再设置新数据
        dispatch(resetNegotiation());
        setTimeout(() => dispatch(setEvents(propEvents)), 0);
      } else if (negotiationState.events.length === 0) {
        // 首次加载：全部设置
        dispatch(setEvents(propEvents));
      } else if (propEvents.length > negotiationState.events.length) {
        // 轮询更新：只 dispatch 新的事件（用最后一个事件的阶段推断进度）
        // 利用 setEvents 基于最后一个事件计算 correct 进度
        dispatch(setEvents(propEvents));
      }
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
              borderTop: '1px solid #f0f0f0',
              borderBottom: '1px solid #f0f0f0',
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

          {/* 折叠面板：时间轴 + 效用图 */}
          <Collapse
            defaultActiveKey={['timeline', 'utility']}
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
                </Space>
              }
              key="timeline"
            >
              <ScrollableRouteTimeline
                events={negotiationState.events}
                replayIndex={negotiationState.replayIndex}
                onEventClick={handleTimelineEventClick}
              />
            </Panel>


            {/* 调整详情汇总 */}
            <Panel
              header={
                <Space>
                  <SwapOutlined />
                  <Text>调整详情汇总</Text>
                  {negotiationState.events.reduce(
                    (sum, e) => sum + (e.adjustments?.length || 0), 0
                  ) > 0 && (
                    <Tag color="blue" style={{ fontSize: 11 }}>
                      {negotiationState.events.reduce(
                        (sum, e) => sum + (e.adjustments?.length || 0), 0
                      )} 项变更
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
