import React, { useEffect, useState } from 'react';
import { Typography, Button, Progress, Card, Alert, message } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { taskApi } from '../services';
import { workflowLogger } from '../utils/workflowlogger';
import NegotiationVisualizer from '../components/NegotiationVisualizer';

const { Title, Paragraph, Text } = Typography;

interface TaskInfo {
  task_id: string;
  status: string;
  progress: number;
  completed: number;
  total: number;
  failed: number;
  message: string;
  itinerary_id?: string;  // 添加行程ID字段
  negotiation_events?: any[];  // 协商事件
}

const TaskStatus: React.FC = () => {
  const navigate = useNavigate();
  const { taskId } = useParams();
  const [taskInfo, setTaskInfo] = useState<TaskInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;

    // 开始工作流程
    workflowLogger.startWorkflow('task_polling', { taskId });

    const pollTaskStatus = async () => {
      try {
        workflowLogger.logApiCall('GET', `/task/${taskId}`);
        const response = await taskApi.getById(taskId);
        workflowLogger.logApiResponse('GET', `/task/${taskId}`, response);

        if (response.code === 200) {
          const data = response.data;
          console.log('任务状态数据:', data); // 添加调试日志

          // 构建任务信息对象
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

          setTaskInfo(taskInfoData);

          workflowLogger.logKeyData('task_status', taskInfoData.status);
          workflowLogger.logKeyData('task_progress', taskInfoData.progress);
          workflowLogger.logKeyData('itinerary_id', taskInfoData.itinerary_id);

                    // 如果任务完成,停止轮询（但 success 且 itinerary_id 为空时继续等待）
                    if (taskInfoData.status === 'failed') {
            workflowLogger.endWorkflow('failed', `任务失败: ${taskInfoData.status}`);
            return;
          }

          if (taskInfoData.status === 'success') {
            // 行程ID可能延迟写入，为空时继续轮询等待
            if (!taskInfoData.itinerary_id) {
              workflowLogger.logKeyData('itinerary_id_pending', 'itinerary_id 尚为空，继续轮询等待...');
              return; // 不停止轮询，等待下一次
            }

            setTimeout(() => {
              // 使用行程ID进行跳转
              const itineraryId = taskInfoData.itinerary_id;
              workflowLogger.logKeyData('navigation_itinerary_id', itineraryId);

              if (itineraryId) {
                workflowLogger.logRoute(`/task/${taskId}`, `/itinerary/${itineraryId}`, { taskId, itineraryId });
                navigate(`/itinerary/${itineraryId}`);
                workflowLogger.endWorkflow('success', '成功跳转到行程详情页');
              } else {
                workflowLogger.logError('navigation', '未找到行程ID');
                message.error('行程生成失败，请重试');
                workflowLogger.endWorkflow('failed', '未找到行程ID');
              }
            }, 1500);
          }
        }
      } catch (err) {
        workflowLogger.logError('task_polling', err);
        console.error('获取任务状态失败:', err);
                setError('获取任务状态失败');
        workflowLogger.endWorkflow('failed', '获取任务状态失败');
      }
    };

    // 立即执行一次
    pollTaskStatus();

    // 设置轮询
    const interval = setInterval(pollTaskStatus, 2000);

    return () => clearInterval(interval);
  }, [taskId, navigate]);

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
          <Title level={3}>智能规划进度</Title>

          {taskInfo ? (
            <>
              <Paragraph>
                <Text strong>任务ID:</Text> {taskInfo.task_id}
              </Paragraph>

              <div style={{ margin: '24px 0' }}>
                <Progress
                  percent={taskInfo.progress}
                  status={taskInfo.status === 'failed' ? 'exception' : 'active'}
                  strokeColor={{
                    '0%': '#108ee9',
                    '100%': '#87d068',
                  }}
                />
                <Paragraph style={{ marginTop: '8px' }}>
                  <Text strong>进度:</Text> {taskInfo.completed}/{taskInfo.total} 个子任务已完成
                </Paragraph>
                <Paragraph style={{ marginTop: '8px' }}>
                  {taskInfo.message}
                </Paragraph>
                {taskInfo.failed > 0 && (
                  <Paragraph style={{ color: '#ff4d4f' }}>
                    失败的子任务: {taskInfo.failed} 个
                  </Paragraph>
                )}
              </div>

                 {/* 协商过程可视化（运行中或已完成时显示） */}
                          {(taskInfo.status === 'running' || taskInfo.status === 'success') && (
                            <div style={{ marginTop: 24, borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
                              <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 8 }}>
                                协商修复过程
                              </Text>
                          <NegotiationVisualizer
                                events={taskInfo.negotiation_events || []}
                                showFullPanel={taskInfo.status === 'running' || taskInfo.status === 'success'}
                              />
                            </div>
                          )}

              {taskInfo.status === 'success' && (
                <Alert
                  message="规划完成"
                  description="正在跳转到行程详情页..."
                  type="success"
                  showIcon
                  style={{ marginTop: '24px' }}
                />
              )}

              {taskInfo.status === 'failed' && (
                <Alert
                  message="规划失败"
                  description="请检查网络连接后重试"
                  type="error"
                  showIcon
                  style={{ marginTop: '24px' }}
                  action={
                    <Button onClick={() => navigate('/requirement')}>
                      重新规划
                    </Button>
                  }
                />
              )}
            </>
          ) : (
            <Paragraph style={{ marginTop: 24 }}>
              <Text type="secondary">正在获取任务状态...</Text>
            </Paragraph>
          )}
        </Card>
    </div>
  );
};

export default TaskStatus;
