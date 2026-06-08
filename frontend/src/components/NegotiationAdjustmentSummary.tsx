/**
 * 调整详情汇总组件
 * 按策略分组展示所有字段级变化（before → after）
 */
import React, { useMemo } from 'react';
import {  Typography, Tag, Empty, Tooltip } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import type { NegotiationEvent } from '../types/negotiation';

const { Text } = Typography;

interface NegotiationAdjustmentSummaryProps {
  events: NegotiationEvent[];
  onEventClick?: (event: NegotiationEvent, index: number) => void;
}

const NegotiationAdjustmentSummary: React.FC<NegotiationAdjustmentSummaryProps> = ({
  events,
  onEventClick,
}) => {
  // 按事件筛选出有调整详情的事件
  const adjustmentEvents = useMemo(() => {
    return events.filter(e => e.adjustments && e.adjustments.length > 0);
  }, [events]);

  if (adjustmentEvents.length === 0) {
    return <Empty description="暂无调整详情数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div style={{ maxHeight: 400, overflowY: 'auto', padding: '4px 0' }}>
      {adjustmentEvents.map((event, eventIdx) => {
        const timestamp = new Date(event.timestamp);
        const timeStr = `${timestamp.getHours().toString().padStart(2, '0')}:${timestamp.getMinutes().toString().padStart(2, '0')}:${timestamp.getSeconds().toString().padStart(2, '0')}`;

        return (
          <div
            key={event.eventId || `adj-event-${eventIdx}`}
            style={{
              marginBottom: 16,
              padding: 12,
              background: eventIdx % 2 === 0 ? '#fafafa' : '#fff',
              borderRadius: 6,
              border: '1px solid #f0f0f0',
              cursor: onEventClick ? 'pointer' : 'default',
            }}
            onClick={() => onEventClick?.(event, eventIdx)}
          >
            {/* 事件头部：策略名 + 时间 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Tag color="purple" style={{ fontSize: 11, margin: 0 }}>
                {event.proposal?.action || event.eventType}
              </Tag>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {timeStr}
              </Text>
              <Text style={{ fontSize: 11, color: '#666' }}>
                {event.fromAgent} → {event.toAgent}
              </Text>
            </div>

            {/* 调整详情列表 */}
            {event.adjustments?.map((adj, adjIdx) => (
              <div
                key={adjIdx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 8px',
                  marginBottom: 4,
                  background: '#fff',
                  borderRadius: 4,
                  border: '1px dashed #e8e8e8',
                  flexWrap: 'wrap',
                }}
              >
                {/* 字段标签 */}
                <Tag color="blue" style={{ fontSize: 10, margin: 0, flexShrink: 0 }}>
                  {adj.field}
                </Tag>

                {/* 项目名 */}
                <Text
                  style={{ fontSize: 12, fontWeight: 500, minWidth: 60, flexShrink: 0 }}
                  ellipsis={{ tooltip: adj.item_name }}
                >
                  {adj.item_name}
                </Text>

                {/* before（红色） */}
                <Tooltip title={`调整前: ${adj.before}`}>
                  <Text
                    delete
                    type="danger"
                    style={{ fontSize: 12, maxWidth: 120 }}
                    ellipsis={{ tooltip: adj.before }}
                  >
                    {adj.before}
                  </Text>
                </Tooltip>

                {/* 箭头 */}
                <ArrowRightOutlined style={{ color: '#faad14', fontSize: 12 }} />

                {/* after（绿色） */}
                <Tooltip title={`调整后: ${adj.after}`}>
                  <Text
                    style={{ fontSize: 12, color: '#52c41a', fontWeight: 600, maxWidth: 120 }}
                    ellipsis={{ tooltip: adj.after }}
                  >
                    {adj.after}
                  </Text>
                </Tooltip>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

export default NegotiationAdjustmentSummary;