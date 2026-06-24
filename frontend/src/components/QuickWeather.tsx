/**
 * 首页快捷天气小部件
 *
 * 在首页底部显示当前已规划行程目的地的天气信息摘要。
 * 不再提供独立搜索功能，天气信息在行程详情页展示。
 */
import React from 'react';
import { Typography } from 'antd';
import { CloudOutlined } from '@ant-design/icons';

const { Text } = Typography;

const QuickWeather: React.FC = () => {
  return (
    <div
      style={{
        border: '1px solid #e0d8ce',
        background: '#faf7f2',
        padding: '24px 28px',
        marginTop: 48,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <CloudOutlined style={{ fontSize: 24, color: '#4a7a8c' }} />
        <div>
          <Text
            style={{
              fontFamily: "'Cormorant Garamond', Georgia, serif",
              fontSize: 18,
              fontWeight: 600,
              color: '#2c2420',
              display: 'block',
              marginBottom: 2,
            }}
          >
            沿途看天
          </Text>
          <Text style={{ fontSize: 12, color: '#8a7a70' }}>
            行程详情页会自动展示目的地的天气信息
          </Text>
        </div>
      </div>
    </div>
  );
};

export default QuickWeather;
