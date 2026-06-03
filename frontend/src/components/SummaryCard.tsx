import React from 'react';
import { Card, Statistic, Row, Col } from 'antd';
import { 
  CalendarOutlined, 
  DollarOutlined, 
  TeamOutlined,
  EnvironmentOutlined 
} from '@ant-design/icons';

interface SummaryCardProps {
  city: string;
  days: number;
  budget: number;
  travelers: number;
}

const SummaryCard: React.FC<SummaryCardProps> = ({ city, days, budget, travelers }) => {
  return (
    <Card>
      <Row gutter={16}>
        <Col span={6}>
          <Statistic
            title="目的地"
            value={city}
            prefix={<EnvironmentOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="天数"
            value={days}
            suffix="天"
            prefix={<CalendarOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="预算"
            value={budget}
            precision={0}
            prefix={<DollarOutlined />}
            suffix="元"
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="人数"
            value={travelers}
            suffix="人"
            prefix={<TeamOutlined />}
          />
        </Col>
      </Row>
    </Card>
  );
};

export default SummaryCard;
