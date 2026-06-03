/**
 * 天气API服务
 */
import apiClient from './api';

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

export const weatherApi = {
  /**
   * 获取实时天气
   */
  getCurrent: async (city: string): Promise<CurrentWeather> => {
    const response = await apiClient.get<{ data: CurrentWeather }>('/weather/current', {
      params: { city }
    });
    return response.data.data;
  },

  /**
   * 获取天气预报
   */
  getForecast: async (city: string): Promise<WeatherForecast> => {
    const response = await apiClient.get<{ data: WeatherForecast }>('/weather/forecast', {
      params: { city }
    });
    return response.data.data;
  }
};
