import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Typography, Space } from 'antd';
import { 
  PlusOutlined, 
  CalendarOutlined, 
  CompassOutlined
} from '@ant-design/icons';

const { Title, Paragraph } = Typography;

const Home: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Title level={2} style={{ textAlign: 'center', marginBottom: 8 }}>
        <CompassOutlined style={{ color: '#1890ff', marginRight: 8 }} />
        欢迎使用旅游行程规划系统
      </Title>
      <Paragraph style={{ textAlign: 'center', fontSize: 16, color: '#666' }}>
        智能规划您的旅行，让每一次出行都充满惊喜！
      </Paragraph>

      <Row gutter={[24, 24]} style={{ marginTop: '48px' }}>
        <Col xs={24} sm={12}>
          <Card
            hoverable
            onClick={() => navigate('/requirement')}
            style={{ 
              height: '240px', 
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center'
            }}
            styles={{ body: { padding: '32px' } }}
          >
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <PlusOutlined style={{ fontSize: '64px', color: '#1890ff' }} />
              <div>
                <Title level={3} style={{ margin: '0 0 8px 0' }}>新建行程</Title>
                <Paragraph type="secondary" style={{ margin: 0, fontSize: 14 }}>
                  填写旅行需求，AI将为您智能规划完美行程
                </Paragraph>
              </div>
            </Space>
          </Card>
        </Col>

        <Col xs={24} sm={12}>
          <Card
            hoverable
            onClick={() => navigate('/itineraries')}
            style={{ 
              height: '240px', 
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center'
            }}
            styles={{ body: { padding: '32px' } }}
          >
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <CalendarOutlined style={{ fontSize: '64px', color: '#52c41a' }} />
              <div>
                <Title level={3} style={{ margin: '0 0 8px 0' }}>我的行程</Title>
                <Paragraph type="secondary" style={{ margin: 0, fontSize: 14 }}>
                  查看和管理您已保存的所有行程方案
                </Paragraph>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      <div style={{ marginTop: '48px', textAlign: 'center' }}>
        <Paragraph type="secondary" style={{ fontSize: 14 }}>
          💡 提示：点击上方的卡片开始您的旅行规划之旅
        </Paragraph>
      </div>
    </div>
  );
};

export default Home;
