/**
 * API服务统一导出
 * 方便在组件中按需导入
 */

// 基础API客户端
export { default as apiClient } from './api';

// 各功能模块API
export { requirementApi } from './requirementApi';
export type { 
  UserRequirement, 
  RequirementSubmitRequest, 
  Requirement,
  StructuredRequirement 
} from './requirementApi';

export { taskApi } from './taskApi';
export type { Task, SubTask } from './taskApi';

export { itineraryApi } from './itineraryApi';
export type { Itinerary, DayPlan } from './itineraryApi';

export { validationApi } from './validationApi';
export type { 
  TimeConflictCheck, 
  ScheduleItem, 
  ValidationResult,
  ConflictItem,
  WarningItem
} from './validationApi';

export { staticDataApi } from './staticDataApi';
export type { Attraction } from './staticDataApi';

export { agentApi } from './agentApi';
export type {
  AttractionsRequest,
  AttractionsResponse,
  TransportRequest,
  TransportResponse,
  HotelRequest,
  HotelResponse,
  FoodRequest,
  FoodResponse
} from './agentApi';

// 新增：行程整合API
export { integrationApi } from './integrationApi';
export type {
  AgentResults,
  CombineRequest,
  CombineResponse,
  OptimizeRouteRequest,
  OptimizeRouteResponse
} from './integrationApi';

// 新增：健康检查API
export { healthApi } from './healthApi';
export type { HealthStatus } from './healthApi';

// 新增：自然语言处理API
export { nlpApi } from './nlp';
export type { NLPRequest, NLPResponse } from './nlp';

// 新增：天气API
export { weatherApi, amapWeatherApi, qweatherApi } from './weather';
export type { CurrentWeather, ForecastDay, WeatherForecast } from './weather';

// 新增：导航路线API
export { navigationApi } from './navigationApi';
export type {
  DirectionRequest,
  DirectionResponse,
  DirectionStep,
  GeocodeRequest,
  GeocodeResponse
} from './navigationApi';

// 新增：协商可视化API
export { negotiationApi, extractEventsFromItinerary } from './negotiationApi';
export type { NegotiationLogEntry, NegotiationResult } from './negotiationApi';

