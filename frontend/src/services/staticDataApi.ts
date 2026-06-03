import apiClient from './api';

export interface Attraction {
  attraction_id: string;
  name: string;
  city_name: string;
  location?: string;
  description?: string;
  recommended_duration?: string;
  ticket_price?: number;
  rating?: number;
}

export const staticDataApi = {
  // 获取所有景点
  getAttractions: () => 
    apiClient.get('/static/attractions'),
  
  // 获取城市景点
  getAttractionsByCity: (cityName: string) => 
    apiClient.get(`/static/attractions/${cityName}`),
  
  // 获取城市列表
  getCities: () => 
    apiClient.get('/static/cities'),
  
  // 获取地点库 - 后端暂未实现此接口
  // getLocations: (cityName: string) => 
  //   apiClient.get(`/static/locations/${cityName}`),
};
