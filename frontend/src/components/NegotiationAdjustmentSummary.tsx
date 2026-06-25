/**
 * 调整详情汇总组件
 * 按策略分组展示所有字段级变化（before → after）
 */
import React, { useMemo } from 'react';
import { Typography, Tag, Empty, Tooltip, Button, Space, message } from 'antd';
import { ArrowRightOutlined, RiseOutlined, FallOutlined, MinusOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
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
    // 将 LLM 格式的 adjustment 转为标准格式（field/item_name/before/after）
  const normalizeAdjustment = (adj: any): any => {
    // 已经是标准格式
    if (adj.field || adj.item_name) return adj;
    // LLM 格式 {target, action, from, to, reason}
    const field = adj.action || (adj.reason ? '调整' : '未知');
    const itemName = adj.target || adj.item_name || '';
    const beforeVal = adj.from || adj.before || '';
    const afterVal = adj.to || adj.after || '';
    return { field, item_name: itemName, before: beforeVal, after: afterVal, reason: adj.reason || '' };
  };

  // 按事件筛选出有调整详情的事件，同时保留其在原始 events 中的索引
  const adjustmentEvents = useMemo(() => {
    const result: { event: NegotiationEvent; originalIndex: number }[] = [];
    events.forEach((e, i) => {
      const rawAdjustments = e.adjustments || [];
      if (rawAdjustments.length > 0) {
        const normalizedAdjustments = rawAdjustments.map(normalizeAdjustment);
        result.push({
          event: { ...e, adjustments: normalizedAdjustments } as NegotiationEvent,
          originalIndex: i,
        });
      }
    });
    return result;
  }, [events]);

  if (adjustmentEvents.length === 0) {
    return <Empty description="暂无调整详情数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div style={{ maxHeight: 400, overflowY: 'auto', padding: '4px 0' }}>
      {adjustmentEvents.map(({ event, originalIndex }, eventIdx) => {
        const timestamp = new Date(event.timestamp);
        const timeStr = `${timestamp.getHours().toString().padStart(2, '0')}:${timestamp.getMinutes().toString().padStart(2, '0')}:${timestamp.getSeconds().toString().padStart(2, '0')}`;

        return (
          <div
            key={event.eventId || `adj-event-${eventIdx}`}
            style={{
                            marginBottom: 16,
              padding: 12,
              background: eventIdx % 2 === 0 ? 'var(--paper-warm, #f0e8da)' : 'var(--paper-light, #faf7f2)',
              borderRadius: 6,
              border: '1px solid var(--border-faded, #e0d8ce)',
              cursor: onEventClick ? 'pointer' : 'default',
            }}
            onClick={() => onEventClick?.(event, originalIndex)}
          >
            {/* 事件头部：策略名 + 时间 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Tag color="purple" style={{ fontSize: 11, margin: 0 }}>
                {event.proposal?.action || event.eventType}
              </Tag>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {timeStr}
              </Text>
                            <Text style={{ fontSize: 11, color: 'var(--ink-light, #8a7a70)' }}>
                {event.fromAgent} → {event.toAgent}
              </Text>
            </div>

                        {/* 用户反馈按钮（P2 预置框架，外部回调时启用） */}
            <Space size="small" style={{ marginTop: 6, marginBottom: 4 }}>
              <Button
                size="small"
                type="text"
                icon={<CheckOutlined />}
                style={{ fontSize: 11, color: 'var(--stamp-green, #6a8f6a)' }}
                onClick={(e) => {
                  e.stopPropagation();
                  message.info('接受功能待后端对接');
                }}
              >
                接受
              </Button>
              <Button
                size="small"
                type="text"
                icon={<CloseOutlined />}
                style={{ fontSize: 11, color: 'var(--stamp-red, #c45a4a)' }}
                onClick={(e) => {
                  e.stopPropagation();
                  message.info('拒绝功能待后端对接');
                }}
              >
                拒绝
              </Button>
            </Space>

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
                  background: 'var(--paper-light, #faf7f2)',
                  borderRadius: 4,
                  border: '1px dashed var(--border-faded, #e0d8ce)',
                  flexWrap: 'wrap',
                }}
              >
                {/* 字段标签 */}
                <Tag color="geekblue" style={{ fontSize: 10, margin: 0, flexShrink: 0 }}>
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
                <ArrowRightOutlined style={{ color: 'var(--stamp-red, #c45a4a)', fontSize: 12 }} />

                {/* after（绿色） */}
                <Tooltip title={`调整后: ${adj.after}`}>
                  <Text
                    style={{ fontSize: 12, color: 'var(--stamp-green, #6a8f6a)', fontWeight: 600, maxWidth: 120 }}
                    ellipsis={{ tooltip: adj.after }}
                  >
                    {adj.after}
                  </Text>
                </Tooltip>

                {/* 变化量指示（P2 新增） */}
                {(() => {
                  const bv = parseFloat(adj.before);
                  const av = parseFloat(adj.after);
                  if (!isNaN(bv) && !isNaN(av) && bv !== 0) {
                    const diff = av - bv;
                    const pct = ((diff / Math.abs(bv)) * 100).toFixed(1);
                    return (
                      <Tooltip title={`变化: ${diff > 0 ? '+' : ''}${diff.toFixed(1)} (${pct}%)`}>
                        <Text style={{ fontSize: 11, color: diff > 0 ? 'var(--stamp-green, #6a8f6a)' : diff < 0 ? 'var(--stamp-red, #c45a4a)' : 'var(--ink-light, #8a7a70)' }}>
                          {diff > 0 ? <><RiseOutlined /> +{pct}%</> : diff < 0 ? <><FallOutlined /> {pct}%</> : <><MinusOutlined /> 0%</>}
                        </Text>
                      </Tooltip>
                    );
                  }
                  return null;
                })()}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

export default NegotiationAdjustmentSummary;