import apiClient from './api';

// 景点推荐接口
export interface AttractionsRequest {
  city_name: string;
  travel_days: number;
  preferences?: string[];
  dislikes?: string[];
  ticket_budget?: number;
  traveler_count?: number;
}

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

export interface AttractionsResponse {
  attractions: Attraction[];
}

// 交通推荐接口
export interface TransportRequest {
  from_location: {
    name: string;
    lat?: number;
    lng?: number;
    coords?: string;
  };
  to_location: {
    name: string;
    lat?: number;
    lng?: number;
    coords?: string;
  };
  mode_preference?: string;  // walking/transit/driving
}

export interface TransportOption {
  transport_id: string;
  type: 'flight' | 'train' | 'bus' | 'subway' | 'taxi';
  from: string;
  to: string;
  departure_time?: string;
  arrival_time?: string;
  duration?: string;
  price?: number;
}

export interface TransportResponse {
  transport_options: TransportOption[];
}

// 住宿推荐接口
export interface HotelRequest {
  city_name: string;
  check_in_date: string;
  check_out_date: string;
  nights: number;
  budget_per_night?: number;
  location_preference?: string;
  traveler_count?: number;
}

export interface Hotel {
  hotel_id: string;
  name: string;
  city_name: string;
  location?: string;
  price_per_night?: number;
  rating?: number;
  amenities?: string[];
}

export interface HotelResponse {
  hotels: Hotel[];
}

// 美食推荐接口
export interface FoodRequest {
  city_name: string;
  travel_days: number;
  budget_per_person?: number;
  cuisine_preference?: string;
  preferences?: string[];
  dislikes?: string[];
}

export interface Restaurant {
  restaurant_id: string;
  name: string;
  city_name: string;
  location?: string;
  cuisine_type?: string;
  avg_price?: number;
  rating?: number;
  specialties?: string[];
}

export interface FoodResponse {
  restaurants: Restaurant[];
}

export const agentApi = {
  // 景点推荐
  getAttractions: (data: AttractionsRequest) => 
    apiClient.post('/agent/attractions', data),
  
  // 交通推荐
  getTransport: (data: TransportRequest) => 
    apiClient.post('/agent/transport', data),
  
  // 住宿推荐
  getHotels: (data: HotelRequest) => 
    apiClient.post('/agent/hotel', data),
  
  // 美食推荐
  getFood: (data: FoodRequest) => 
    apiClient.post('/agent/food', data),
};
