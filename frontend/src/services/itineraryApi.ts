import apiClient from './api';

export interface DayPlan {
  day: number;
  date: string;
  attractions?: any[];
  transport?: any;
  hotel?: any;
  meals?: any[];
  notes?: string;
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

export interface Itinerary {
  itinerary_id?: string;
  user_id: string;
  requirement_id: string;
  title?: string;
  city_name: string;
  travel_days: number;
  total_budget?: number;
  day_plans?: DayPlan[];
  status?: string; // draft/saved/published
  created_at?: string;
  updated_at?: string;
}

export const itineraryApi = {
  // 创建行程
  create: (data: Partial<Itinerary>) => 
    apiClient.post('/itinerary/create', data),
  
  // 获取行程详情
  getById: (id: string) => 
    apiClient.get(`/itinerary/${id}`),
  
  // 更新行程
  update: (id: string, data: Partial<Itinerary>) => 
    apiClient.put(`/itinerary/${id}`, data),
  
  // 删除行程
  delete: (id: string) => 
    apiClient.delete(`/itinerary/${id}`),
  
  // 获取用户所有行程
  getByUser: (userId: string) => 
    apiClient.get(`/itinerary/user/${userId}`),
};
