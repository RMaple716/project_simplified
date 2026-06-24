/**
 * 天气API服务
 *
 * 1. 高德地图天气 - amapWeatherApi（旧）
 * 2. 和风天气     - qweatherApi（新，精简版）
 *
 * 和风天气的 API Key 和 Host 已硬编码在后端，前端只通过代理接口调用。
 * 后端路由前缀：/api/v1/qweather
 */
import apiClient from './api';

// ============================================================
// 1. 高德地图天气类型（现有）
// ============================================================

export interface CurrentWeather {
  province: string;
  city: string;
  adcode: string;
  weather: string;
  temperature: string;
  winddirection: string;
  windpower: string;
  humidity: string;
  reporttime: string;
}

export interface ForecastDay {
  date: string;
  week: string;
  dayweather: string;
  nightweather: string;
  daytemp: string;
  nighttemp: string;
  daywind: string;
  nightwind: string;
  daypower: string;
  nightpower: string;
}

export interface WeatherForecast {
  city: string;
  adcode: string;
  province: string;
  reporttime: string;
  casts: ForecastDay[];
}

export const amapWeatherApi = {
  getCurrent: async (city: string): Promise<CurrentWeather> => {
    const response = await apiClient.get<{ data: CurrentWeather }>('/weather/current', {
      params: { city }
    });
    return response.data.data;
  },

  getForecast: async (city: string): Promise<WeatherForecast> => {
    const response = await apiClient.get<{ data: WeatherForecast }>('/weather/forecast', {
      params: { city }
    });
    return response.data.data;
  }
};

// ============================================================
// 2. 和风天气类型（精简版 — 匹配和风天气原始数据字段）
// ============================================================

/** 和风天气 - 城市信息 */
export interface QCity {
  name: string;
  id: string;
  lat: string;
  lon: string;
  adm1: string;
  adm2: string;
  country: string;
  tz: string;
  utcOffset: string;
  type: string;
  rank: string;
}

/** 和风天气 - 实时天气（原始 API 字段名） */
export interface QCurrentWeather {
  obsTime: string;
  temp: string;
  feelsLike: string;
  icon: string;
  text: string;
  windDir: string;
  windScale: string;
  windSpeed: string;
  humidity: string;
  precip: string;
  pressure: string;
  vis: string;
  cloud: string;
  dew: string;
}

/** 和风天气 - 每日预报 */
export interface QDailyForecast {
  fxDate: string;
  sunrise: string;
  sunset: string;
  tempMax: string;
  tempMin: string;
  iconDay: string;
  textDay: string;
  iconNight: string;
  textNight: string;
  windDirDay: string;
  windScaleDay: string;
  windDirNight: string;
  windScaleNight: string;
  humidity: string;
  precip: string;
  pressure: string;
  vis: string;
  uvIndex: string;
}

/** 和风天气 - 逐小时预报 */
export interface QHourlyForecast {
  fxTime: string;
  temp: string;
  icon: string;
  text: string;
  windDir: string;
  windScale: string;
  windSpeed: string;
  humidity: string;
  precip: string;
  pop: string;
  pressure: string;
  cloud: string;
  dew: string;
}

/**
 * 和风天气 API 精简版
 *
 * 后端代理地址：/api/v1/qweather/*
 * API Key 和 Host 硬编码在后端，前端无需关心。
 */
export const qweatherApi = {
  /** 搜索城市 */
  searchCities: async (location: string): Promise<QCity[]> => {
    const response = await apiClient.get<any>(
      '/qweather/city/lookup',
      { params: { location } }
    );
    // axios拦截器已返回 {code, msg, data}，所以 response.data 就是实际数据（城市数组）
    return response.data || [];
  },

  /** 获取实时天气 */
  getCurrent: async (location: string): Promise<QCurrentWeather | null> => {
    const response = await apiClient.get<any>(
      '/qweather/weather/now',
      { params: { location } }
    );
    return response.data || null;
  },

  /** 获取天气预报 */
  getForecast: async (location: string, days: string = '7d'): Promise<QDailyForecast[]> => {
    const response = await apiClient.get<any>(
      '/qweather/weather/forecast',
      { params: { location, days } }
    );
    return response.data || [];
  },

  /** 获取逐小时预报 */
  getHourly: async (location: string, hours: string = '24h'): Promise<QHourlyForecast[]> => {
    const response = await apiClient.get<any>(
      '/qweather/weather/hourly',
      { params: { location, hours } }
    );
    return response.data || [];
  }
};

/** 兼容旧版引用 */
export const weatherApi = amapWeatherApi;
