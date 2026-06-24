import React, { useEffect, useState } from 'react';
import { Card, Space, Typography, Tag, Spin } from 'antd';
import { CloudOutlined, LoadingOutlined } from '@ant-design/icons';
import { qweatherApi, QDailyForecast } from '../services/weather';

const { Text } = Typography;

/** 通用工具函数：从对象中安全读取字段，兼容下划线/无下划线两种命名 */
function f(obj: any, ...keys: string[]): string | undefined {
  if (!obj || typeof obj !== 'object') return undefined;
  for (const key of keys) {
    const v = obj[key];
    if (v !== undefined && v !== null && v !== '') return String(v);
  }
  return undefined;
}

interface WeatherInfoProps {
  weather?: {
    date?: string;
    dayweather?: string;
    nightweather?: string;
    daytemp?: string;
    nighttemp?: string;
    daywind?: string;
    nightwind?: string;
    /** 后端新格式：下划线命名 */
    day_weather?: string;
    night_weather?: string;
    day_temp?: string;
    night_temp?: string;
    temperature?: string;
    day_wind?: string;
    night_wind?: string;
    /** 季节推算 */
    season?: string;
    source?: string;
  };
  /** 城市名（可选）：传入后自动从和风天气 API 获取真实数据 */
  cityName?: string;
  /** 目标日期（可选）：YYYY-MM-DD 格式，与 cityName 配合获取真实预报 */
  date?: string;
}

/**
 * 和风天气 Emoji 映射
 */
const weatherEmojiMap: Record<string, string> = {
  '晴': '☀️', '多云': '⛅', '少云': '⛅', '晴间多云': '🌤️', '阴': '☁️',
  '阵雨': '🌦️', '强阵雨': '🌧️', '雷阵雨': '⛈️', '小雨': '🌦️', '中雨': '🌦️',
  '大雨': '🌧️', '暴雨': '🌧️', '冻雨': '🌨️', '雨': '🌧️',
  '小雪': '🌨️', '中雪': '🌨️', '大雪': '❄️', '暴雪': '❄️', '雪': '❄️',
  '雾': '🌫️', '霾': '🌫️', '薄雾': '🌫️', '浓雾': '🌫️',
  '扬沙': '🌪️', '浮尘': '🌪️', '沙尘暴': '🌪️',
};

function getWeatherEmoji(text: string): string {
  for (const [key, emoji] of Object.entries(weatherEmojiMap)) {
    if (text.includes(key)) return emoji;
  }
  return '☀️';
}

/** 天气颜色 */
function getWeatherColor(w: string) {
  if (!w) return 'default';
  if (w.includes('雨') || w.includes('雪')) return 'blue';
  if (w.includes('晴')) return 'gold';
  if (w.includes('多云') || w.includes('阴')) return 'default';
  return 'default';
}

/**
 * WeatherInfo 组件
 *
 * 改进：支持传入 cityName + date，自动从和风天气 API 获取真实预报数据。
 * 兼容旧用法：直接传入 weather 对象（模拟数据/后端数据）。
 */
const WeatherInfo: React.FC<WeatherInfoProps> = ({ weather, cityName, date }) => {
  // ===== 真实数据状态（从和风天气API获取） =====
  const [realForecast, setRealForecast] = useState<QDailyForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

    // 如果提供了 cityName，从和风天气获取真实预报
  useEffect(() => {
    if (!cityName) return;

    let cancelled = false;
    setLoading(true);
    setFetchError(null);

    const fetchRealWeather = async () => {
      try {
        // 1. 搜索城市获取 Location ID
        const cities = await qweatherApi.searchCities(cityName);
        if (cancelled) return;
        if (cities.length === 0) {
          console.warn(`[WeatherInfo] 和风天气未找到城市: ${cityName}`);
          setFetchError(`未找到城市「${cityName}」的天气数据`);
          return;
        }

        // 2. 选择最佳匹配城市（优先选市级 city 类型，rank 数字越小越精确）
        //    和风天气 rank: 1=一线城市, 2=二线城市, ..., 通常城市数据中 type='city' 的才是可查天气的
        const sorted = [...cities].sort((a, b) => {
          // 优先 type 为 'city' 的
          const aIsCity = a.type === 'city' ? 0 : 1;
          const bIsCity = b.type === 'city' ? 0 : 1;
          if (aIsCity !== bIsCity) return aIsCity - bIsCity;
          // rank 数字越小越精确
          return (parseInt(a.rank) || 999) - (parseInt(b.rank) || 999);
        });
        const bestCity = sorted[0];
        console.log(`[WeatherInfo] 选择城市: ${bestCity.name} (${bestCity.adm1}), id=${bestCity.id}, type=${bestCity.type}, rank=${bestCity.rank}`);

        // 3. 获取预报数据
        const forecastList = await qweatherApi.getForecast(bestCity.id, '7d');
        if (cancelled) return;

        if (date && forecastList.length > 0) {
          // 如果有日期，找对应日期的预报
          const matched = forecastList.find(d => d.fxDate === date);
          if (matched) {
            setRealForecast(matched);
          } else {
            // 没找到对应日期，取第一天
            setRealForecast(forecastList[0]);
          }
        } else if (forecastList.length > 0) {
          // 没有日期，取今天（第一条）
          setRealForecast(forecastList[0]);
        } else {
          console.warn(`[WeatherInfo] 和风天气未返回预报数据, locationId=${bestCity.id}`);
          setFetchError('暂无天气预报数据');
        }
      } catch (err) {
        console.error(`[WeatherInfo] 获取和风天气数据失败:`, err);
        setFetchError('天气服务暂不可用');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchRealWeather();
    return () => { cancelled = true; };
  }, [cityName, date]);

  // ===== 决定显示的数据：优先用 API 真实数据，其次用传入的 weather =====
  const displayData = realForecast ?? weather;

  // ===== 加载中状态 =====
  if (loading) {
    return (
      <Card size="small" style={{ marginBottom: 8, backgroundColor: '#e6f7ff' }}
        styles={{ body: { padding: '12px' } }}>
        <Space direction="vertical" size="small" style={{ width: '100%', textAlign: 'center' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 18, color: '#4a7a8c' }} />} />
          <Text type="secondary" style={{ fontSize: 12 }}>获取天气...</Text>
        </Space>
      </Card>
    );
  }

    // ===== 无数据状态（显示回退信息） =====
  if (!displayData || Object.keys(displayData).length === 0) {
    return (
      <Card size="small" style={{ marginBottom: 8, backgroundColor: '#e6f7ff' }}
        styles={{ body: { padding: '12px' } }}>
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text strong><CloudOutlined /> 天气信息</Text>
            <Tag color="default">暂无预报</Tag>
          </div>
          {fetchError ? (
            <Text type="secondary" style={{ fontSize: 12 }}>{fetchError}</Text>
          ) : (
            <Text type="secondary">天气数据暂不可用</Text>
          )}
        </Space>
      </Card>
    );
  }

  // ===== 提取展示字段 =====
  let dayWeatherStr: string;
  let nightWeatherStr: string;
  let dayTempStr: string | undefined;
  let nightTempStr: string | undefined;
  let temperatureStr: string | undefined;
  let sourceStr: string | undefined;

  if (realForecast) {
    // 来自 API 真实数据
    dayWeatherStr = realForecast.textDay || '';
    nightWeatherStr = realForecast.textNight || '';
    dayTempStr = realForecast.tempMax;
    nightTempStr = realForecast.tempMin;
    temperatureStr = `${realForecast.tempMin}°C ~ ${realForecast.tempMax}°C`;
  } else {
    // 兼容旧数据格式
    dayWeatherStr = f(weather, 'dayweather', 'day_weather') || '';
    nightWeatherStr = f(weather, 'nightweather', 'night_weather') || '';
    dayTempStr = f(weather, 'daytemp', 'day_temp');
    nightTempStr = f(weather, 'nighttemp', 'night_temp');
    temperatureStr = f(weather, 'temperature');
    sourceStr = f(weather, 'source');
  }

  return (
    <Card size="small" style={{ marginBottom: 8, backgroundColor: '#e6f7ff' }}
      styles={{ body: { padding: '12px' } }}>
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong>
            <span style={{ marginRight: 4 }}>{getWeatherEmoji(dayWeatherStr)}</span>
            {' '}天气信息
          </Text>
          <Space size="small">
            {dayWeatherStr && (
              <Tag color={getWeatherColor(dayWeatherStr)}>
                {getWeatherEmoji(dayWeatherStr)} {dayWeatherStr}
              </Tag>
            )}
            {realForecast ? (
              <Tag color="cyan" style={{ fontSize: 10 }}>和风天气</Tag>
            ) : sourceStr === 'seasonal' ? (
              <Tag color="cyan" style={{ fontSize: 10 }}>估算</Tag>
            ) : null}
          </Space>
        </div>

        {/* 温度 */}
        {temperatureStr ? (
          <Text type="secondary">温度：{temperatureStr}</Text>
        ) : dayTempStr && nightTempStr ? (
          <Text type="secondary">温度：{dayTempStr}°C / {nightTempStr}°C</Text>
        ) : dayTempStr ? (
          <Text type="secondary">温度：{dayTempStr}°C</Text>
        ) : null}

        {/* 夜间天气 */}
        {nightWeatherStr && (
          <Text type="secondary">夜间：{getWeatherEmoji(nightWeatherStr)} {nightWeatherStr}</Text>
        )}
      </Space>
    </Card>
  );
};

export default WeatherInfo;
