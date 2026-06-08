/**
 * 协商进度条组件 - 语义化升级版
 *
 * 功能：
 * 1. 保留原有百分比进度条
 * 2. 增加当前阶段中文描述和参与方信息
 * 3. 兼容旧版纯百分比进度条（后端未发新事件时降级）
 */
import React from 'react';
import { Progress, Typography, Tag, Space } from 'antd';
import {
  LoadingOutlined,
  CheckCircleOutlined,
  SwapOutlined,
  CarOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { NegotiationPhase } from '../types/negotiation';
import { PHASE_MAP_CN } from '../types/negotiation';

const { Text } = Typography;

export interface NegotiationProgressBarProps {
  /** 整体进度百分比 0-100 */
  percent: number;
  /** 当前协商阶段 */
  phase: NegotiationPhase;
  /** 活跃参与方列表 */
  activeAgents?: string[];
  /** 当前摘要文字 */
  summary?: string;
  /** 是否展示详细信息 */
  showDetail?: boolean;
  /** 进度条状态 */
  status?: 'active' | 'exception' | 'success' | 'normal';
  /** 传统模式（无协商事件时降级） */
  legacy?: boolean;
}

/** 阶段对应的颜色 */
const PHASE_COLORS: Record<NegotiationPhase, string> = {
  INIT: '#d9d9d9',
  CFP: '#1890ff',
  BIDDING: '#722ed1',
  NEGOTIATE: '#fa8c16',
  FINALIZING: '#52c41a',
  FINALIZED: '#13c2c2',
};

/** 阶段对应的图标 */
const PhaseIcon: React.FC<{ phase: NegotiationPhase }> = ({ phase }) => {
  switch (phase) {
    case 'CFP':
    case 'BIDDING':
      return <TeamOutlined />;
    case 'NEGOTIATE':
      return <SwapOutlined />;
    case 'FINALIZING':
    case 'FINALIZED':
      return <CheckCircleOutlined />;
    default:
      return <LoadingOutlined />;
  }
};

const NegotiationProgressBar: React.FC<NegotiationProgressBarProps> = ({
  percent,
  phase,
  activeAgents = [],
  summary = '',
  showDetail = true,
  status = 'active',
  legacy = false,
}) => {
  // 传统模式：仅显示百分比进度条
  if (legacy) {
    return (
      <div style={{ margin: '16px 0' }}>
        <Progress
          percent={percent}
          status={status}
          strokeColor={{
            '0%': '#108ee9',
            '100%': '#87d068',
          }}
        />
        {summary && (
          <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
            {summary}
          </Text>
        )}
      </div>
    );
  }

  return (
    <div style={{ margin: '16px 0' }}>
      {/* 进度条 */}
      <Progress
        percent={percent}
        status={status}
        strokeColor={{
          '0%': '#108ee9',
          '100%': '#87d068',
        }}
      />

      {/* 阶段状态文字 */}
      {showDetail && (
        <Space
          direction="vertical"
          size="small"
          style={{ width: '100%', marginTop: 8 }}
        >
          {/* 当前阶段 */}
          <Space size="small">
            <PhaseIcon phase={phase} />
            <Text strong style={{ color: PHASE_COLORS[phase] || '#333' }}>
              {PHASE_MAP_CN[phase] || phase}
            </Text>
          </Space>

          {/* 摘要文字 */}
          {summary && (
            <Text type="secondary" style={{ fontSize: 13 }}>
              {summary}
            </Text>
          )}

          {/* 活跃参与方 */}
          {activeAgents.length > 0 && (
            <Space size={4} wrap>
              <Text type="secondary" style={{ fontSize: 12 }}>
                参与方：
              </Text>
              {activeAgents.map((agent) => (
                <Tag
                  key={agent}
                  color="blue"
                  style={{ fontSize: 11, marginRight: 4 }}
                  icon={agent === 'dispatcher' ? <TeamOutlined /> : <CarOutlined />}
                >
                  {agent === 'dispatcher'
                    ? '调度中心'
                    : agent === 'all_vehicles'
                    ? '全部车辆'
                    : agent}
                </Tag>
              ))}
            </Space>
          )}
        </Space>
      )}
    </div>
  );
};

export default NegotiationProgressBar;
