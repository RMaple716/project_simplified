import React, { useEffect, useState, useCallback } from 'react';
import {
  Typography, Button, Card, Row, Col, Spin, Empty, Tag, Space,
  message, Popconfirm, Tooltip, Alert, Modal, List, Divider, Descriptions
} from 'antd';
import {
  PlusOutlined,
  CalendarOutlined,
  EnvironmentOutlined,
  DollarOutlined,
  ClockCircleOutlined,
  EyeOutlined,
  DeleteOutlined,
  StarOutlined,
  StarFilled,
  RightOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { itineraryApi } from '../services/itineraryApi';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

// 状态对应的颜色和中文
const statusConfig: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  saved: { color: 'blue', label: '已保存' },
  completed: { color: 'green', label: '已完成' },
  published: { color: 'purple', label: '已发布' },
};

const ItineraryList: React.FC = () => {
  const navigate = useNavigate();
  const { user, isLoggedIn } = useSelector((state: RootState) => state.auth);

  const [loading, setLoading] = useState(false);
  const [itineraries, setItineraries] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [previewItinerary, setPreviewItinerary] = useState<any | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);

  // 加载行程列表
  const fetchItineraries = useCallback(async () => {
    if (!isLoggedIn || !user?.user_id) {
      setItineraries([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await itineraryApi.getByUser(user.user_id);
      if ((res as any).code === 200) {
        const data = (res as any).data;
        setItineraries(data.itineraries || []);
      } else {
        setError((res as any).msg || '获取行程列表失败');
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '网络请求失败');
    } finally {
      setLoading(false);
    }
  }, [isLoggedIn, user?.user_id]);

  useEffect(() => {
    fetchItineraries();
  }, [fetchItineraries]);

  // 删除行程
  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      const res = await itineraryApi.delete(id);
      if ((res as any).code === 200) {
        message.success('行程已删除');
        setItineraries(prev => prev.filter(item => item.itinerary_id !== id));
      } else {
        message.error((res as any).msg || '删除失败');
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除失败');
    } finally {
      setDeletingId(null);
    }
  };

  // 切换收藏
  const handleToggleFavorite = async (id: string, currentFav: boolean) => {
    try {
      const res = await itineraryApi.toggleFavorite(id);
      if ((res as any).code === 200) {
        message.success(currentFav ? '已取消收藏' : '已收藏');
        setItineraries(prev => prev.map(item =>
          item.itinerary_id === id ? { ...item, is_favorite: !currentFav } : item
        ));
      }
    } catch (err: any) {
      message.error('操作失败');
    }
  };

  // 预览行程
  const handlePreview = async (id: string) => {
    try {
      const res = await itineraryApi.getById(id);
      if ((res as any).code === 200) {
        setPreviewItinerary((res as any).data);
        setPreviewVisible(true);
      }
    } catch {
      message.error('获取行程详情失败');
    }
  };

  // 格式化时间
  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '未知';
    return dayjs(dateStr).format('YYYY-MM-DD HH:mm');
  };

  // 未登录状态
  if (!isLoggedIn) {
    return (
      <div style={{ padding: '48px', maxWidth: '1200px', margin: '0 auto', textAlign: 'center' }}>
        <Empty description="请先登录后查看行程">
          <Button type="primary" onClick={() => navigate('/login')}>
            前往登录
          </Button>
        </Empty>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      {/* 标题栏 */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={3} style={{ margin: 0 }}>
            <CalendarOutlined style={{ marginRight: 8 }} />
            我的行程
          </Title>
          <Text type="secondary">共 {itineraries.length} 个行程</Text>
        </Col>
        <Col>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/requirement')} size="large">
              新建行程
            </Button>
            <Button onClick={() => navigate('/')}>返回首页</Button>
          </Space>
        </Col>
      </Row>

      {/* 加载状态 */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <Spin size="large" tip="加载行程列表..." />
        </div>
      )}

      {/* 错误状态 */}
      {error && !loading && (
        <Alert
          message="加载失败"
          description={error}
          type="error"
          showIcon
          closable
          style={{ marginBottom: 16 }}
          action={<Button size="small" onClick={fetchItineraries}>重试</Button>}
        />
      )}

      {/* 空状态 */}
      {!loading && !error && itineraries.length === 0 && (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <Empty
            description={
              <span>
                暂无行程数据<br />
                <Text type="secondary">点击"新建行程"开始规划你的旅行吧！</Text>
              </span>
            }
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/requirement')}>
              新建行程
            </Button>
          </Empty>
        </div>
      )}

      {/* 行程卡片列表 */}
      {!loading && itineraries.length > 0 && (
        <Row gutter={[16, 16]}>
          {itineraries.map((item) => (
            <Col xs={24} sm={12} lg={8} key={item.itinerary_id}>
              <Card
                hoverable
                actions={[
                  <Tooltip title="查看详情" key="view">
                    <EyeOutlined onClick={() => navigate(`/itinerary/${item.itinerary_id}`)} />
                  </Tooltip>,
                  <Tooltip title="快速预览" key="preview">
                    <ClockCircleOutlined onClick={() => handlePreview(item.itinerary_id)} />
                  </Tooltip>,
                  <Tooltip title={item.is_favorite ? '取消收藏' : '收藏'} key="fav">
                    {item.is_favorite ? (
                      <StarFilled style={{ color: '#faad14' }} onClick={() => handleToggleFavorite(item.itinerary_id, true)} />
                    ) : (
                      <StarOutlined onClick={() => handleToggleFavorite(item.itinerary_id, false)} />
                    )}
                  </Tooltip>,
                  <Popconfirm
                    title="确定删除此行程？"
                    description="删除后无法恢复"
                    onConfirm={() => handleDelete(item.itinerary_id)}
                    okText="确定"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    key="delete"
                  >
                    <DeleteOutlined style={{ color: deletingId === item.itinerary_id ? '#999' : '#ff4d4f' }} />
                  </Popconfirm>,
                ]}
                style={{ borderRadius: 8 }}
              >
                <Card.Meta
                  title={
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <Text strong ellipsis style={{ fontSize: 16 }}>
                        {item.title || (item.city_name ? `${item.city_name} ${item.travel_days || ''}日游` : '未命名行程')}
                      </Text>
                      <Space>
                        {item.city_name && <Tag icon={<EnvironmentOutlined />} color="blue">{item.city_name}</Tag>}
                        {item.travel_days && <Tag icon={<CalendarOutlined />}>{item.travel_days}天</Tag>}
                        <Tag color={statusConfig[item.status]?.color || 'default'}>
                          {statusConfig[item.status]?.label || item.status}
                        </Tag>
                        {item.is_favorite && <Tag color="gold" icon={<StarFilled />}>收藏</Tag>}
                      </Space>
                    </Space>
                  }
                  description={
                    <div>
                      <Divider style={{ margin: '8px 0' }} />
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        {item.total_budget != null && (
                          <Text type="secondary">
                            <DollarOutlined style={{ marginRight: 4 }} />
                            预算: ¥{Number(item.total_budget).toLocaleString()}
                          </Text>
                        )}
                        {item.actual_cost != null && (
                          <Text type="secondary">
                            <DollarOutlined style={{ marginRight: 4 }} />
                            实际花费: ¥{Number(item.actual_cost).toLocaleString()}
                          </Text>
                        )}
                        <Text type="secondary" style={{ fontSize: 12 }}>创建于 {formatDate(item.created_at)}</Text>
                        {item.updated_at && <Text type="secondary" style={{ fontSize: 12 }}>更新于 {formatDate(item.updated_at)}</Text>}
                      </Space>
                      <Divider style={{ margin: '8px 0' }} />
                      <Button type="link" icon={<RightOutlined />} onClick={(e) => { e.stopPropagation(); navigate(`/itinerary/${item.itinerary_id}`); }} style={{ padding: 0 }}>
                        查看完整详情
                      </Button>
                    </div>
                  }
                />
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 预览弹窗 */}
      <Modal
        title={
          <Space>
            <EyeOutlined />
            <span>行程预览: {previewItinerary?.title || (previewItinerary?.city_name ? `${previewItinerary.city_name} ${previewItinerary.travel_days || ''}日游` : '未命名行程')}</span>
          </Space>
        }
        open={previewVisible}
        onCancel={() => { setPreviewVisible(false); setPreviewItinerary(null); }}
        footer={
          <Space>
            <Button onClick={() => setPreviewVisible(false)}>关闭</Button>
            <Button type="primary" onClick={() => { setPreviewVisible(false); if (previewItinerary?.itinerary_id) navigate(`/itinerary/${previewItinerary.itinerary_id}`); }}>
              查看完整详情
            </Button>
          </Space>
        }
        width={700}
      >
        {previewItinerary && (
          <div>
            <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label={<><EnvironmentOutlined /> 目的地</>}>{previewItinerary.city_name || '未知'}</Descriptions.Item>
              <Descriptions.Item label={<><CalendarOutlined /> 天数</>}>{previewItinerary.travel_days || '-'} 天</Descriptions.Item>
              <Descriptions.Item label={<><DollarOutlined /> 总预算</>}>¥{(previewItinerary.total_budget ?? 0).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusConfig[previewItinerary.status]?.color || 'default'}>
                  {statusConfig[previewItinerary.status]?.label || previewItinerary.status}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
            <Divider>每日行程摘要</Divider>
            {previewItinerary.day_plans && previewItinerary.day_plans.length > 0 ? (
              <List
                size="small"
                dataSource={previewItinerary.day_plans}
                renderItem={(dayPlan: any, idx: number) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={<Tag color="blue" style={{ minWidth: 60, textAlign: 'center' }}>第{dayPlan.day || idx + 1}天</Tag>}
                      title={
                        <Space>
                          {dayPlan.date && <Text type="secondary" style={{ fontSize: 12 }}>{dayPlan.date}</Text>}
                          {dayPlan.weather?.dayweather && (
                            <Tag color="cyan" style={{ fontSize: 11 }}>{dayPlan.weather.dayweather}{dayPlan.weather.daytemp ? ` ${dayPlan.weather.daytemp}°C` : ''}</Tag>
                          )}
                        </Space>
                      }
                      description={
                        <div>
                          {dayPlan.attractions?.length > 0 && (
                            <div style={{ marginBottom: 4 }}>
                              <Text type="secondary" style={{ fontSize: 12 }}>景点: {dayPlan.attractions.map((a: any) => a.name).join(' → ')}</Text>
                            </div>
                          )}
                          {dayPlan.meals?.length > 0 && (
                            <div style={{ marginBottom: 4 }}>
                              <Text type="secondary" style={{ fontSize: 12 }}>餐饮: {dayPlan.meals.map((m: any) => m.name || m.restaurant_name).join('、')}</Text>
                            </div>
                          )}
                          {dayPlan.hotel && (
                            <div><Text type="secondary" style={{ fontSize: 12 }}>住宿: {dayPlan.hotel.name}</Text></div>
                          )}
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无每日行程数据" />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ItineraryList;
