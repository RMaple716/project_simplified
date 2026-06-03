import React from 'react';
import { Typography, Button, Space } from 'antd';
import { useNavigate } from 'react-router-dom';

const { Title, Paragraph } = Typography;

const ItineraryList: React.FC = () => {
  const navigate = useNavigate();

  console.log('ItineraryList 组件已加载'); // 调试日志

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Title level={3}>我的行程</Title>
      <Paragraph>这是行程列表页面（简化版）</Paragraph>
      
      <Space>
        <Button type="primary" onClick={() => navigate('/requirement')}>
          新建行程
        </Button>
        <Button onClick={() => navigate('/')}>
          返回首页
        </Button>
      </Space>
    </div>
  );
};

export default ItineraryList;
