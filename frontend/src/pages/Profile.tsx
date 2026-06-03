import React, { useEffect, useState } from 'react';
import { Card, Descriptions, Button, message, Spin, List, Tag, Empty } from 'antd';
import { UserOutlined, CalendarOutlined, EditOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { authApi } from '../services/authApi';
import { itineraryApi } from '../services/itineraryApi';

interface ItineraryItem {
  itinerary_id: string;
  title: string;
  total_budget: number;
  status: string;
  created_at: string;
}

const Profile: React.FC = () => {
  const navigate = useNavigate();
  const { isLoggedIn, user } = useSelector((state: RootState) => state.auth);
  const [loading, setLoading] = useState(false);
  const [userInfo, setUserInfo] = useState<any>(null);
  const [itineraries, setItineraries] = useState<ItineraryItem[]>([]);
  const [itinerariesLoading, setItinerariesLoading] = useState(false);

  useEffect(() => {
    if (!isLoggedIn) {
      message.warning('请先登录');
      navigate('/login');
      return;
    }
    fetchUserInfo();
    fetchItineraries();
  }, [isLoggedIn]);

    const fetchUserInfo = async () => {
    setLoading(true);
    try {
      const response = await authApi.getCurrentUser();
      const res = response as any;
      if (res.code === 200) {
        setUserInfo(res.data);
      }
    } catch (error) {
      console.error('获取用户信息失败:', error);
    } finally {
      setLoading(false);
    }
  };
  const fetchItineraries = async () => {
    if (!user?.user_id) return;
    setItinerariesLoading(true);
    try {
      const response = await itineraryApi.getByUser(user.user_id);
      const res = response as any;
      if (res.code === 200) {
        setItineraries(res.data?.itineraries || []);
      }
    } catch (error) {
      console.error('获取行程列表失败:', error);
    } finally {
      setItinerariesLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 100 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1000px', margin: '0 auto' }}>
      {/* 返回按钮 */}
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/')}
        style={{ marginBottom: 16 }}
      >
        返回首页
      </Button>

      {/* 用户信息卡片 */}
      <Card
        title={
          <span>
            <UserOutlined style={{ marginRight: 8 }} />
            个人中心
          </span>
        }
        style={{ marginBottom: 24 }}
      >
        <Descriptions column={2}>
          <Descriptions.Item label="用户名">
            {userInfo?.username || user?.username || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="邮箱">
            {userInfo?.email || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="用户ID">
            {userInfo?.user_id || user?.user_id || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="注册时间">
            {userInfo?.created_at || '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 我的行程列表 */}
      <Card
        title={
          <span>
            <CalendarOutlined style={{ marginRight: 8 }} />
            我的行程
          </span>
        }
        extra={
          <Button type="primary" onClick={() => navigate('/requirement')}>
            <EditOutlined /> 新建行程
          </Button>
        }
      >
        {itinerariesLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : itineraries.length === 0 ? (
          <Empty description="暂无行程，快去创建第一个行程吧！">
            <Button type="primary" onClick={() => navigate('/requirement')}>
              新建行程
            </Button>
          </Empty>
        ) : (
          <List
            dataSource={itineraries}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button
                    type="link"
                    onClick={() => navigate(`/itinerary/${item.itinerary_id}`)}
                  >
                    查看详情
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {item.title}
                      <Tag
                        color={
                          item.status === 'published' ? 'green' :
                          item.status === 'saved' ? 'blue' : 'default'
                        }
                        style={{ marginLeft: 8 }}
                      >
                        {item.status === 'published' ? '已发布' :
                         item.status === 'saved' ? '已保存' : '草稿'}
                      </Tag>
                    </span>
                  }
                  description={
                    <span>
                      <CalendarOutlined style={{ marginRight: 4 }} />
                      {item.created_at ? new Date(item.created_at).toLocaleDateString('zh-CN') : '-'}
                      <span style={{ marginLeft: 16 }}>
                        预算: ¥{item.total_budget || 0}
                      </span>
                    </span>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>
    </div>
  );
};

export default Profile;