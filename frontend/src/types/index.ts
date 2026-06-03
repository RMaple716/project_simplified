// 通用API响应类型
export interface ApiResponse<T = any> {
  code: number;
  msg: string;
  data: T;
}

// 分页参数
export interface PaginationParams {
  page?: number;
  page_size?: number;
  total?: number;
}

// 用户信息
export interface User {
  user_id: string;
  username: string;
  email?: string;
  phone?: string;
}

// 景点信息
export interface Attraction {
  attraction_id: string;
  name: string;
  city_name: string;
  location?: string;
  description?: string;
  recommended_duration?: string;
  visit_time_slot?: 'morning' | 'afternoon' | 'evening';
  ticket_price?: number;
  rating?: number;
  opening_hours?: string;
  tags?: string[];
}

// 酒店信息
export interface Hotel {
  hotel_id: string;
  name: string;
  city_name: string;
  location?: string;
  price_per_night?: number;
  rating?: number;
  amenities?: string[];
}

// 餐厅信息
export interface Restaurant {
  restaurant_id: string;
  name: string;
  city_name: string;
  location?: string;
  cuisine_type?: string;
  avg_price?: number;
  rating?: number;
  specialties?: string[];
  meal_type?: 'breakfast' | 'lunch' | 'dinner';
  meal_time?: string;
  time?: string;
  start_time?: string;
  end_time?: string;
  duration?: string;
}

// 交通信息
export interface Transport {
  transport_id: string;
  type: 'flight' | 'train' | 'bus' | 'subway' | 'taxi' | 'transit';
  from: string;
  to: string;
  departure_time?: string;
  arrival_time?: string;
  duration?: string;
  price?: number;
}
