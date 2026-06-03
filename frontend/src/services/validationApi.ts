import apiClient from './api';

export interface TimeConflictCheck {
  schedule: ScheduleItem[];
}

export interface ScheduleItem {
  name: string;
  start_time?: string;
  end_time?: string;
  duration?: string;
  activity_type: string;
  location?: string; // 活动地点（可选）
}

export interface ValidationResult {
  has_conflict: boolean;
  conflicts: ConflictItem[];
  warnings: WarningItem[];
  suggestions: string[];
}

export interface ConflictItem {
  type: string;
  severity: 'error' | 'warning';
  message: string;
  items: string[];
}

export interface WarningItem {
  type: string;
  message: string;
}

export const validationApi = {
  // 时间冲突检测
  checkTimeConflict: (data: TimeConflictCheck) => 
    apiClient.post('/validation/time-conflict', data),
  
  // 完整行程校验
  validateItinerary: (data: any) => 
    apiClient.post('/validation/itinerary', data),
};
