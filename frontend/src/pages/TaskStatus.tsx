import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { Typography, Button, Progress, Card, Alert, message, Tag, Space } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { taskApi } from '../services';
import { workflowLogger } from '../utils/workflowlogger';
import NegotiationVisualizer from '../components/NegotiationVisualizer';
import { getDefaultWS } from '../services/negotiationApi';
import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined, ClockCircleOutlined, AimOutlined, RobotOutlined } from '@ant-design/icons';

const { Title, Paragraph, Text } = Typography;

interface TaskInfo {
  task_id: string;
  status: string;
  progress: number;
  completed: number;
  total: number;
  failed: number;
  message: string;
  itinerary_id?: string;
  negotiation_events?: any[];
}

/** 单个 Agent 的执行状态 */
interface AgentStatus {
  type: string;               // attraction/accommodation/food/transport
  label: string;              // 中文名称
  status: 'pending' | 'running' | 'success' | 'failed';
  itemCount: number;          // 找到的结果数
  error?: string;
  startTime?: number;         // 开始时间戳
  endTime?: number;           // 结束时间戳
}

/** Agent 类型中文映射 */
const AGENT_LABEL_MAP: Record<string, string> = {
  attraction: '景点推荐',
  accommodation: '住宿推荐',
  food: '美食推荐',
  transport: '交通规划',
};

const AGENT_ICON_MAP: Record<string, string> = {
  attraction: '🏛️',
  accommodation: '🏨',
  food: '🍽️',
  transport: '🚗',
};

const TaskStatus: React.FC = () => {
  const navigate = useNavigate();
  const { taskId } = useParams();
  const [taskInfo, setTaskInfo] = useState<TaskInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ===== WebSocket 实时推送状态 =====
  const [agents, setAgents] = useState<AgentStatus[]>([
    { type: 'attraction', label: '景点推荐', status: 'pending', itemCount: 0 },
    { type: 'accommodation', label: '住宿推荐', status: 'pending', itemCount: 0 },
    { type: 'food', label: '美食推荐', status: 'pending', itemCount: 0 },
    { type: 'transport', label: '交通规划', status: 'pending', itemCount: 0 },
  ]);
  const [currentPhase, setCurrentPhase] = useState<'pending' | 'executing' | 'negotiating' | 'finalized' | 'failed'>('pending');
  const [liveNegotiationEvents, setLiveNegotiationEvents] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [progressMessage, setProgressMessage] = useState('正在初始化...');
  const wsRef = useRef<ReturnType<typeof getDefaultWS> | null>(null);
  const navigatingRef = useRef(false);

  // 更新单个 agent 状态
  const updateAgentStatus = useCallback((agentType: string, updates: Partial<AgentStatus>) => {
    setAgents(prev => prev.map(a => a.type === agentType ? { ...a, ...updates } : a));
  }, []);

  // ===== WebSocket 连接 =====
  useEffect(() => {
    if (!taskId) return;
    if (navigatingRef.current) return;

    // 只要不是 finalizing 阶段，就连接 WebSocket
    const ws = getDefaultWS();
    wsRef.current = ws;

    const unsubStatus = ws.onStatusChange((status) => {
      setWsConnected(status === 'connected');
    });

    const unsubEvent = ws.onEvent((event) => {
      // 根据事件类型处理
      switch (event.eventType) {
        case 'TASK_STARTED':
          setCurrentPhase('executing');
          setProgressMessage(event.message || `开始行程规划：共 ${event.subtaskCount || 4} 个子任务`);
          break;

        case 'SUB_TASK_STARTED': {
          const agentType = event.agentType;
          updateAgentStatus(agentType, { status: 'running', startTime: event.timestamp });
          setProgressMessage(event.message || `${AGENT_LABEL_MAP[agentType] || agentType}智能体正在执行...`);
          break;
        }

        case 'SUB_TASK_COMPLETED': {
          const agentType = event.agentType;
          updateAgentStatus(agentType, {
            status: 'success',
            itemCount: event.itemCount || 0,
            endTime: event.timestamp
          });
          setProgressMessage(event.message || `${AGENT_LABEL_MAP[agentType] || agentType}智能体完成`);
          break;
        }

        case 'SUB_TASK_FAILED': {
          const agentType = event.agentType;
          updateAgentStatus(agentType, {
            status: 'failed',
            error: event.error,
            endTime: event.timestamp
          });
          setProgressMessage(event.message || `${AGENT_LABEL_MAP[agentType] || agentType}智能体执行失败`);
          break;
        }

        case 'NEGOTIATION_STARTED':
          setCurrentPhase('negotiating');
          setProgressMessage('🔄 所有子任务完成，正在协商优化行程...');
          break;

        case 'ITINERARY_CREATED': {
          setCurrentPhase('finalized');
          setProgressMessage(`🎉 行程生成成功！`);
          const itineraryId = event.itineraryId;
          if (itineraryId && !navigatingRef.current) {
            navigatingRef.current = true;
            // 更新 taskInfo 让页面显示行程已创建
            setTaskInfo(prev => prev ? { ...prev, itinerary_id: itineraryId, status: 'success' } : prev);
            // 延迟后跳转
            setTimeout(() => {
              message.success('行程已生成，正在跳转...');
              navigate(`/itinerary/${itineraryId}`);
            }, 1500);
          }
          break;
        }

        default:
          // 其他事件类型（如协商事件）统一收集
          if (['CFP', 'PROPOSE', 'COUNTER', 'ACCEPT', 'REJECT', 'FINALIZED', 'AGENT_MSG'].includes(event.eventType)) {
            setLiveNegotiationEvents(prev => {
              // 避免重复
              if (prev.some(e => e.eventId === event.eventId)) return prev;
              return [...prev, event];
            });
          }
          break;
      }
    });

    ws.connect(taskId);

    return () => {
      unsubEvent();
      unsubStatus();
      ws.disconnect();
    };
  }, [taskId, navigate, updateAgentStatus]);

  // ===== HTTP 轮询（作为 WebSocket 的补充/降级） =====
  useEffect(() => {
    if (!taskId) return;
    if (navigatingRef.current) return;

    workflowLogger.startWorkflow('task_polling', { taskId });

    const pollTaskStatus = async () => {
      try {
        const response = await taskApi.getById(taskId);
        if (response.code === 200) {
          const data = response.data;

          // 如果 WebSocket 已经拿到 itinerary_id 跳转了，就不再更新
          if (navigatingRef.current) return;

          const taskInfoData: TaskInfo = {
            task_id: data.task_id || taskId,
            status: data.status || 'pending',
            progress: typeof data.progress === 'number' ? data.progress : 0,
            completed: typeof data.completed === 'number' ? data.completed : 0,
            total: typeof data.total === 'number' ? data.total : 0,
            failed: typeof data.failed === 'number' ? data.failed : 0,
            message: data.message || '正在处理中...',
            itinerary_id: data.itinerary_id,
            negotiation_events: data.negotiation_events || []
          };

                    // 合并 WebSocket 已收集的协商事件
          const pollEvents: any[] = data.negotiation_events || [];
          if (pollEvents.length > 0) {
            setLiveNegotiationEvents(prev => {
              const existingIds = new Set(prev.map(e => e.eventId));
              const newEvents = pollEvents.filter((e: any) => !existingIds.has(e.eventId));
              return [...prev, ...newEvents];
            });
          }

          // 只有当 WebSocket 还没有提供 itinerary_id 时才用轮询的
          if (!navigatingRef.current) {
            setTaskInfo(taskInfoData);
          }

          // 如果轮询发现行程ID，但 WebSocket 尚未触发跳转
          if (data.itinerary_id && !navigatingRef.current) {
            const itineraryId = data.itinerary_id;
            navigatingRef.current = true;
            setCurrentPhase('finalized');
            setTimeout(() => {
              navigate(`/itinerary/${itineraryId}`);
            }, 1500);
          }
        }
      } catch (err) {
        if (!navigatingRef.current) {
          setError('获取任务状态失败');
        }
      }
    };

    pollTaskStatus();
    const interval = setInterval(pollTaskStatus, 3000);
    return () => clearInterval(interval);
  }, [taskId, navigate]);

  // ===== 计算总体进度 =====
  const overallProgress = useMemo(() => {
    if (currentPhase === 'finalized') return 100;
    if (currentPhase === 'failed') return 100;
    if (currentPhase === 'negotiating') {
      // 协商阶段：占 80%-98%
      const base = 80;
      const events = liveNegotiationEvents.length;
      const extra = Math.min(events * 3, 18); // 每多一个事件加3%，最多18%
      return base + extra;
    }
    if (currentPhase === 'executing') {
      const completedCount = agents.filter(a => a.status === 'success' || a.status === 'failed').length;
      const runningCount = agents.filter(a => a.status === 'running').length;
      // 每个 agent 占 20%
      return (completedCount * 20) + (runningCount > 0 ? 10 : 0);
    }
    return 0;
  }, [currentPhase, agents, liveNegotiationEvents]);

  // ===== 合并 WebSocket 事件和轮询事件 =====
  const mergedEvents = useMemo(() => {
    if (liveNegotiationEvents.length > 0) return liveNegotiationEvents;
    return taskInfo?.negotiation_events || [];
  }, [liveNegotiationEvents, taskInfo]);

    // ===== 渲染 =====

  if (error) {
    return (
      <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
        <Alert
          message="错误"
          description={error}
          type="error"
          showIcon
          action={
            <Button size="small" onClick={() => navigate('/')}>
              返回首页
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Card>
        <Title level={3}>
          <Space>
            <RobotOutlined style={{ color: 'var(--stamp-blue, #4a7a8c)' }} />
            <span>智能规划进度</span>
            {wsConnected && (
              <Tag color="green" style={{ fontSize: 11, marginLeft: 8 }}>
                <ClockCircleOutlined spin /> 实时
              </Tag>
            )}
            {!wsConnected && currentPhase === 'executing' && (
              <Tag color="orange" style={{ fontSize: 11, marginLeft: 8 }}>
                轮询模式
              </Tag>
            )}
          </Space>
        </Title>

        {/* 任务ID */}
        <Paragraph style={{ marginBottom: 8 }}>
          <Text strong>任务ID:</Text> {taskId}
        </Paragraph>

        {/* 总体进度条 */}
        <div style={{ margin: '16px 0' }}>
          <Progress
            percent={overallProgress}
            status={currentPhase === 'failed' ? 'exception' : 'active'}
            strokeColor={{
              '0%': '#108ee9',
              '100%': '#87d068',
            }}
            format={(percent) => {
              if (currentPhase === 'finalized') return '100%';
              if (currentPhase === 'executing') return `${percent}%`;
              if (currentPhase === 'negotiating') return `${percent}%`;
              return `${percent}%`;
            }}
          />
          <Paragraph style={{ marginTop: 8, marginBottom: 4 }}>
            <Text type="secondary">
              {/* 阶段标签 */}
              {currentPhase === 'pending' && <Tag color="default">等待中</Tag>}
              {currentPhase === 'executing' && <Tag color="processing">子任务执行中</Tag>}
              {currentPhase === 'negotiating' && <Tag color="warning">协商优化中</Tag>}
              {currentPhase === 'finalized' && <Tag color="success">已完成</Tag>}
              {currentPhase === 'failed' && <Tag color="error">失败</Tag>}
              {' '}{progressMessage}
            </Text>
          </Paragraph>
        </div>

        {/* ===== Agent 实时执行状态面板 ===== */}
        {currentPhase !== 'pending' && (
          <div style={{
            marginBottom: 16,
            padding: 12,
            background: 'var(--paper-warm, #f0e8da)',
            border: '1px solid var(--border-faded, #e0d8ce)',
            borderRadius: 4,
          }}>
            <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 14 }}>
              <AimOutlined style={{ marginRight: 6 }} />
              智能体执行进度
            </Text>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {agents.map(agent => (
                <div
                  key={agent.type}
                  style={{
                    flex: '1 1 180px',
                    padding: '8px 12px',
                    background: '#fff',
                    border: `1px solid ${
                      agent.status === 'success' ? '#52c41a' :
                      agent.status === 'failed' ? '#ff4d4f' :
                      agent.status === 'running' ? '#1890ff' :
                      '#d9d9d9'
                    }`,
                    borderRadius: 4,
                    minWidth: 140,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <span>{AGENT_ICON_MAP[agent.type] || '🤖'}</span>
                    <Text strong style={{ fontSize: 13 }}>{agent.label}</Text>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    {agent.status === 'pending' && (
                      <>
                        <ClockCircleOutlined style={{ color: '#d9d9d9' }} />
                        <Text type="secondary">等待中</Text>
                      </>
                    )}
                    {agent.status === 'running' && (
                      <>
                        <LoadingOutlined style={{ color: '#1890ff' }} />
                        <Text style={{ color: '#1890ff' }}>执行中...</Text>
                      </>
                    )}
                    {agent.status === 'success' && (
                      <>
                        <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        <Text style={{ color: '#52c41a' }}>完成 ({agent.itemCount} 项)</Text>
                      </>
                    )}
                    {agent.status === 'failed' && (
                      <>
                        <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                        <Text style={{ color: '#ff4d4f', fontSize: 11 }}>失败</Text>
                      </>
                    )}
                  </div>
                  {agent.error && (
                    <div style={{ fontSize: 10, color: '#ff4d4f', marginTop: 2 }}>
                      {agent.error.substring(0, 40)}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* 完成情况统计 */}
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <Text type="secondary">
                已完成: {agents.filter(a => a.status === 'success').length} /
                失败: {agents.filter(a => a.status === 'failed').length} /
                执行中: {agents.filter(a => a.status === 'running').length} /
                等待: {agents.filter(a => a.status === 'pending').length}
              </Text>
            </div>
          </div>
        )}

        {/* ===== 协商过程可视化 ===== */}
        {(currentPhase === 'negotiating' || currentPhase === 'finalized' || (taskInfo?.negotiation_events && taskInfo.negotiation_events.length > 0)) && (
          <div style={{ marginTop: 16, borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
            <NegotiationVisualizer
              events={mergedEvents}
              showFullPanel={true}
            />
          </div>
        )}

        {/* ===== 完成/失败提示 ===== */}
        {currentPhase === 'finalized' && (
          <Alert
            message="规划完成"
            description="正在跳转到行程详情页..."
            type="success"
            showIcon
            style={{ marginTop: '16px' }}
          />
        )}

        {currentPhase === 'failed' && (
          <Alert
            message="规划失败"
            description="部分智能体执行失败，请检查网络连接后重试"
            type="error"
            showIcon
            style={{ marginTop: '16px' }}
            action={
              <Button onClick={() => navigate('/requirement')}>
                重新规划
              </Button>
            }
          />
        )}
      </Card>
    </div>
  );
};

export default TaskStatus;
