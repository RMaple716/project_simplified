/**
 * 可滚动路线时间轴组件
 *
 * 功能：
 * 1. 实时时间轴显示协商阶段
 * 2. 时间轴可滚动
 * 3. 当前回放位置高亮
 * 4. 时间轴自动滚动到最新位置
 */
import React, { useEffect, useRef } from 'react';
import { Timeline, Typography, Tag, Tooltip } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  SwapOutlined,
  SendOutlined,
  FlagOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import type { NegotiationEvent } from '../types/negotiation';
import { EVENT_TYPE_CN, PHASE_MAP_CN } from '../types/negotiation';

const { Text } = Typography;

interface ScrollableRouteTimelineProps {
  /** 协商事件列表 */
  events: NegotiationEvent[];
  /** 当前回放索引（-1 表示非回放模式） */
  replayIndex: number;
  /** 点击事件的回调 */
  onEventClick?: (event: NegotiationEvent, index: number) => void;
  /** 最大显示条数 */
  maxItems?: number;
}

/** 事件类型对应的颜色 */
const EVENT_COLORS: Record<string, string> = {
  CFP: 'blue',
  PROPOSE: 'orange',
  COUNTER: 'purple',
  ACCEPT: 'green',
  REJECT: 'red',
  FINALIZED: 'cyan',
};

/** 事件类型对应的图标 */
const EVENT_ICONS: Record<string, React.ReactNode> = {
  CFP: <SendOutlined />,
  PROPOSE: <FileSearchOutlined />,
  COUNTER: <SwapOutlined />,
  ACCEPT: <CheckCircleOutlined />,
  REJECT: <CloseCircleOutlined />,
  FINALIZED: <FlagOutlined />,
};

/** 格式化时间戳 */
function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

const ScrollableRouteTimeline: React.FC<ScrollableRouteTimelineProps> = ({
  events,
  replayIndex,
  onEventClick,
  maxItems = 50,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 截取显示的 events
  const displayEvents = events.slice(-maxItems);
  const offset = Math.max(0, events.length - maxItems);

  // 自动滚动到底部
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [displayEvents.length]);

  // 构建时间轴项目
  const timelineItems = displayEvents.map((event, idx) => {
    const actualIdx = offset + idx;
    const isActive =
      replayIndex >= 0 ? actualIdx <= replayIndex : true;
    const isCurrent =
      actualIdx === replayIndex;

    // 从 proposal 提取核心信息
    const proposalInfo =
      event.proposal?.action || event.proposal?.conflict_type || '';

    return {
      key: event.eventId || `event-${actualIdx}`,
      color: isCurrent ? EVENT_COLORS[event.eventType] || 'gray' : 'gray',
      dot: isCurrent ? (
        <Tooltip title={EVENT_TYPE_CN[event.eventType] || event.eventType}>
          <span style={{ color: EVENT_COLORS[event.eventType] || '#333', fontSize: 16 }}>
            {EVENT_ICONS[event.eventType] || <SyncOutlined />}
          </span>
        </Tooltip>
      ) : undefined,
      children: (
        <div
          onClick={() => onEventClick?.(event, actualIdx)}
          style={{
            cursor: onEventClick ? 'pointer' : 'default',
            padding: '4px 0',
            opacity: isActive ? 1 : 0.4,
            background: isCurrent ? '#e6f7ff' : 'transparent',
            borderRadius: 4,
            paddingLeft: isCurrent ? 8 : 0,
            transition: 'all 0.3s',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {/* 事件类型标签 */}
            <Tag
              color={EVENT_COLORS[event.eventType] || 'default'}
              style={{ marginRight: 0, fontSize: 11, lineHeight: '18px' }}
            >
              {EVENT_TYPE_CN[event.eventType] || event.eventType}
            </Tag>

            {/* 时间 */}
            <Text type="secondary" style={{ fontSize: 11 }}>
              {formatTimestamp(event.timestamp)}
            </Text>

            {/* 参与方 */}
            <Text style={{ fontSize: 12 }}>
              {event.fromAgent} → {event.toAgent}
            </Text>

            {/* 阶段 */}
            {event.phase && (
              <Tag style={{ fontSize: 10, lineHeight: '16px', margin: 0 }}>
                {PHASE_MAP_CN[event.phase] || event.phase}
              </Tag>
            )}
          </div>

          {/* 提案信息 */}
          {proposalInfo && (
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 2 }}>
              {proposalInfo}
            </Text>
          )}
     {/* ===== 调整详情（字段级变化） ===== */}
     {event.adjustments && event.adjustments.length > 0 && (
       <div style={{ marginTop: 4, paddingLeft: 0 }}>
         {event.adjustments.map((adj, adjIdx) => (
           <div
             key={adjIdx}
             style={{
               display: 'flex',
               alignItems: 'center',
               gap: 6,
               padding: '2px 0',
               fontSize: 12,
             }}
           >
             {/* 字段名 */}
             <Tag
               color="processing"
               style={{ fontSize: 10, lineHeight: '16px', margin: 0, flexShrink: 0 }}
             >
               {adj.field}
             </Tag>
     
             {/* 项目名 */}
             <Text type="secondary" style={{ fontSize: 11, maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0 }}>
               {adj.item_name}：
             </Text>
     
             {/* before 值（红色删除线） */}
             <Text
               delete
               type="danger"
               style={{ fontSize: 11, maxWidth: 100 }}
               ellipsis={{ tooltip: adj.before }}
             >
               {adj.before}
             </Text>
     
             {/* 箭头 */}
             <Text type="warning" style={{ fontSize: 11 }}>→</Text>
     
             {/* after 值（绿色） */}
             <Text
               style={{ fontSize: 11, color: '#52c41a', fontWeight: 500, maxWidth: 100 }}
               ellipsis={{ tooltip: adj.after }}
             >
               {adj.after}
             </Text>
           </div>
         ))}
       </div>
     )}



          {/* 效用值 */}
          {event.utility && (event.utility.dispatcher !== undefined || event.utility.vehicle !== undefined) && (
            <div style={{ marginTop: 2 }}>
              {event.utility.dispatcher !== undefined && (
                <Text style={{ fontSize: 11, color: '#1890ff' }}>
                  调度:{event.utility.dispatcher.toFixed(2)}
                </Text>
              )}
              {event.utility.vehicle !== undefined && (
                <Text style={{ fontSize: 11, color: '#52c41a', marginLeft: 8 }}>
                  车辆:{event.utility.vehicle.toFixed(2)}
                </Text>
              )}
            </div>
          )}

          {/* 价格信息 */}
          {event.proposal?.price !== undefined && (
            <Tag color="gold" style={{ fontSize: 11, marginTop: 2 }}>
              ¥{event.proposal.price}
            </Tag>
          )}
        </div>
      ),
    };
  });

  return (
    <div
      ref={containerRef}
      style={{
        maxHeight: 360,
        overflowY: 'auto',
        padding: '8px 0',
        scrollBehavior: 'smooth',
      }}
    >
      {/* 索引偏移提示 */}
      {offset > 0 && (
        <Text type="secondary" style={{ display: 'block', textAlign: 'center', fontSize: 11, padding: '4px 0' }}>
          前面还有 {offset} 个事件...
        </Text>
      )}

      <Timeline items={timelineItems} />

      <div ref={bottomRef} />
    </div>
  );
};

export default ScrollableRouteTimeline;
