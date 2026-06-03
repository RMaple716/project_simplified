/**
 * 导航路线API服务
 * 封装对后端导航API的调用
 */
import apiClient from './api';

export interface DirectionRequest {
  origin: string;           // 起点坐标或地址
  destination: string;      // 终点坐标或地址
  mode?: string;            // walking/driving/transit/bicycling
  origin_name?: string;     // 起点显示名称
  destination_name?: string; // 终点显示名称
}

export interface DirectionStep {
  instruction: string;
  distance: number;
  duration: number;
  polyline?: string;
  type?: string;
  departure?: string;
  arrival?: string;
  via_num?: number;
}

export interface DirectionResponse {
  mode: string;
  from: string;
  to: string;
  distance: number;
  distance_text: string;
  duration: number;
  duration_text: string;
  steps: DirectionStep[];
  polyline: string;
}

export interface GeocodeRequest {
  address: string;
}

export interface GeocodeResponse {
  address: string;
  location: string;
}

export const navigationApi = {
  /**
   * 查询两点之间的导航路线
   */
  getDirection: (data: DirectionRequest) =>
    apiClient.post('/navigation/direction', data),

  /**
   * 地理编码：将地址转换为经纬度坐标
   */
  geocode: (data: GeocodeRequest) =>
    apiClient.post('/navigation/geocode', data),
};

export default navigationApi;
