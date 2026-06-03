import React from 'react';
import { Card, Space, Typography, Tag } from 'antd';
import { CloudOutlined, ThunderboltOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface WeatherInfoProps {
  weather?: {
    date?: string;
    dayweather?: string;
    nightweather?: string;
    daytemp?: string;
    nighttemp?: string;
    daywind?: string;
    nightwind?: string;
  };
}

const WeatherInfo: React.FC<WeatherInfoProps> = ({ weather }) => {
  if (!weather) {
    return null;
  }

  // 根据天气状况选择图标和颜色
  const getWeatherIcon = (weather: string) => {
    if (!weather) return <CloudOutlined />;

    if (weather.includes('雨') || weather.includes('雪')) {
      return <ThunderboltOutlined style={{ color: '#1890ff' }} />;
    }
    if (weather.includes('晴')) {
      return <CloudOutlined style={{ color: '#faad14' }} />;
    }
    if (weather.includes('多云') || weather.includes('阴')) {
      return <CloudOutlined style={{ color: '#8c8c8c' }} />;
    }
    return <CloudOutlined />;
  };

  const getWeatherColor = (weather: string) => {
    if (!weather) return 'default';

    if (weather.includes('雨') || weather.includes('雪')) {
      return 'blue';
    }
    if (weather.includes('晴')) {
      return 'gold';
    }
    if (weather.includes('多云') || weather.includes('阴')) {
      return 'default';
    }
    return 'default';
  };

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, backgroundColor: '#e6f7ff' }}
      bodyStyle={{ padding: '12px' }}
    >
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong>
            {getWeatherIcon(weather.dayweather || '')}
            {' '}天气信息
          </Text>
          {weather.dayweather && (
            <Tag color={getWeatherColor(weather.dayweather)}>
              {weather.dayweather}
            </Tag>
          )}
        </div>

        {weather.daytemp && weather.nighttemp && (
          <Text type="secondary">
            温度：{weather.daytemp}°C / {weather.nighttemp}°C
          </Text>
        )}

        {weather.nightweather && (
          <Text type="secondary">
            夜间：{weather.nightweather}
          </Text>
        )}

        {weather.daywind && (
          <Text type="secondary">
            白天风向：{weather.daywind}
          </Text>
        )}

        {weather.nightwind && (
          <Text type="secondary">
            夜间风向：{weather.nightwind}
          </Text>
        )}
      </Space>
    </Card>
  );
};

export default WeatherInfo;
