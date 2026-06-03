/**
 * 数据转换工具
 * 用于处理后端智能体返回的数据,转换为前端期望的格式
 */

// 景点数据转换
export const transformAttraction = (attraction: any) => ({
  attraction_id: attraction.attraction_id || attraction.id || '',
  name: attraction.name || '',
  city_name: attraction.city_name || '',
  location: attraction.location || '',
  description: attraction.description || '',
  recommended_duration: attraction.recommended_duration || attraction.suggested_duration || '',
  visit_time_slot: attraction.visit_time_slot || '',
  visit_time: attraction.visit_time || '',
  visit_duration: attraction.visit_duration || attraction.recommended_duration || '',
  start_time: attraction.start_time || '',
  end_time: attraction.end_time || '',
  ticket_price: attraction.ticket_price || 0,
  rating: attraction.rating || 0,
  opening_hours: attraction.opening_hours || '',
  tags: attraction.tags || [],
});

// 酒店数据转换
export const transformHotel = (hotel: any) => ({
  hotel_id: hotel.hotel_id || hotel.id || '',
  name: hotel.name || '',
  city_name: hotel.city_name || '',
  location: hotel.location || hotel.address || '',
  price_per_night: hotel.price_per_night || 0,
  rating: hotel.rating || 0,
  amenities: hotel.amenities || [],
});

// 餐厅数据转换
export const transformRestaurant = (restaurant: any) => ({
  restaurant_id: restaurant.restaurant_id || restaurant.id || '',
  name: restaurant.name || restaurant.restaurant_name || '',
  city_name: restaurant.city_name || '',
  location: restaurant.location || restaurant.address || '',
  cuisine_type: restaurant.cuisine_type || restaurant.cuisine || '',
  avg_price: restaurant.avg_price || restaurant.avg_price_per_person || 0,
  rating: restaurant.rating || 0,
  specialties: restaurant.specialties || restaurant.recommended_dishes || [],
  meal_type: restaurant.meal_type || '',
  meal_time: restaurant.meal_time || '',
  time: restaurant.time || '',
  start_time: restaurant.start_time || '',
  end_time: restaurant.end_time || '',
  duration: restaurant.duration || '',
});

// 交通数据转换
export const transformTransport = (transport: any) => ({
  transport_id: transport.transport_id || transport.id || '',
  type: transport.type || transport.mode || '',
  from: transport.from || transport.from_location || '',
  to: transport.to || transport.to_location || '',
  departure_time: transport.departure_time || '',
  arrival_time: transport.arrival_time || '',
  duration: transport.duration || '',
  duration_text: transport.duration_text || '',
  distance: transport.distance || 0,
  distance_text: transport.distance_text || '',
  price: transport.price || transport.cost || 0,
  polyline: transport.polyline || '',
  steps: transport.steps || [],
});

// 批量转换景点数据
export const transformAttractions = (attractions: any[]) => 
  attractions.map(transformAttraction);

// 批量转换酒店数据
export const transformHotels = (hotels: any[]) => 
  hotels.map(transformHotel);

// 批量转换餐厅数据
export const transformRestaurants = (restaurants: any[]) => 
  restaurants.map(transformRestaurant);

// 批量转换交通数据
export const transformTransports = (transports: any[]) => 
  transports.map(transformTransport);

// 转换每日行程数据
export const transformDayPlan = (dayPlan: any) => ({
  day: dayPlan.day || 1,
  date: dayPlan.date || '',
  attractions: dayPlan.attractions ? transformAttractions(dayPlan.attractions) : [],
  meals: dayPlan.meals ? transformRestaurants(dayPlan.meals) : [],
  transport: dayPlan.transport ? transformTransport(dayPlan.transport) : null,
  hotel: dayPlan.hotel ? transformHotel(dayPlan.hotel) : null,
  daily_cost: dayPlan.daily_cost || 0,
  notes: dayPlan.notes || '',
});

// 批量转换每日行程数据
export const transformDayPlans = (dayPlans: any[]) => 
  dayPlans.map(transformDayPlan);
