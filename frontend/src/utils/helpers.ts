import dayjs from 'dayjs';

/**
 * 格式化日期
 */
export const formatDate = (date: string | Date, format = 'YYYY-MM-DD') => {
  return dayjs(date).format(format);
};

/**
 * 格式化时间
 */
export const formatTime = (time: string, format = 'HH:mm') => {
  return dayjs(time, 'HH:mm').format(format);
};

/**
 * 格式化金额
 */
export const formatMoney = (amount: number) => {
  return `¥${amount.toFixed(2)}`;
};

/**
 * 计算两个日期之间的天数
 */
export const daysBetween = (startDate: string | Date, endDate: string | Date) => {
  const start = dayjs(startDate);
  const end = dayjs(endDate);
  return end.diff(start, 'day');
};

/**
 * 生成唯一ID
 */
export const generateId = () => {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};

/**
 * 防抖函数
 */
export const debounce = <T extends (...args: any[]) => any>(
  func: T,
  wait: number
): ((...args: Parameters<T>) => void) => {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
};

/**
 * 节流函数
 */
export const throttle = <T extends (...args: any[]) => any>(
  func: T,
  limit: number
): ((...args: Parameters<T>) => void) => {
  let inThrottle = false;
  
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
};

/**
 * 深拷贝对象
 */
export const deepClone = <T>(obj: T): T => {
  return JSON.parse(JSON.stringify(obj));
};

/**
 * 从localStorage获取数据
 */
export const getFromStorage = <T>(key: string, defaultValue?: T): T | undefined => {
  try {
    const item = localStorage.getItem(key);
    return item ? JSON.parse(item) : defaultValue;
  } catch (error) {
    console.error('Error reading from localStorage:', error);
    return defaultValue;
  }
};

/**
 * 保存数据到localStorage
 */
export const saveToStorage = <T>(key: string, value: T): void => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.error('Error saving to localStorage:', error);
  }
};

/**
 * 从localStorage删除数据
 */
export const removeFromStorage = (key: string): void => {
  try {
    localStorage.removeItem(key);
  } catch (error) {
    console.error('Error removing from localStorage:', error);
  }
};

/**
 * 解析自然语言日期为具体日期
 * 支持格式：明天、后天、大后天、下周一、下周五、周末、X月X日等
 */
export const parseNaturalDate = (dateStr: string): dayjs.Dayjs | null => {
  if (!dateStr || typeof dateStr !== 'string') {
    return null;
  }

  const today = dayjs();

  // 处理绝对日期格式：YYYY-MM-DD
  if (/^\d{4}-\d{1,2}-\d{1,2}$/.test(dateStr)) {
    const date = dayjs(dateStr);
    return date.isValid() ? date : null;
  }

  // 处理 X月X日 格式
  const monthDayMatch = dateStr.match(/(\d{1,2})月(\d{1,2})[日号]?/);
  if (monthDayMatch) {
    const month = parseInt(monthDayMatch[1]);
    const day = parseInt(monthDayMatch[2]);
    const year = today.year();
    const date = dayjs(`${year}-${month}-${day}`);
    // 如果日期已过，假设是明年
    return date.isBefore(today, 'day') ? date.add(1, 'year') : date;
  }

  // 处理相对日期（按长度降序排列，优先匹配更长的关键词）
  const relativeDates = [
    { keyword: '大后天', days: 3 },  // ✅ 优先匹配最长的
    { keyword: '明天', days: 1 },
    { keyword: '后天', days: 2 },
  ];

  for (const { keyword, days } of relativeDates) {
    if (dateStr.includes(keyword)) {
      return today.add(days, 'day');
    }
  }

  // 处理"下周X"格式
  const nextWeekMatch = dateStr.match(/下周([一二三四五六日天])/);
  if (nextWeekMatch) {
    const weekMap: Record<string, number> = {
      '一': 1, '二': 2, '三': 3, '四': 4, 
      '五': 5, '六': 6, '日': 0, '天': 0
    };
    const targetWeekday = weekMap[nextWeekMatch[1]];
    if (targetWeekday !== undefined) {
      const currentWeekday = today.day();
      let daysToAdd = targetWeekday - currentWeekday + 7;
      if (daysToAdd <= 0) daysToAdd += 7;
      return today.add(daysToAdd, 'day');
    }
  }

  // 处理"周末"
  if (dateStr.includes('周末')) {
    const currentWeekday = today.day();
    const daysToSaturday = currentWeekday === 0 ? 6 : (6 - currentWeekday);
    return today.add(daysToSaturday, 'day');
  }

  // 处理"下个月"
  if (dateStr.includes('下个月')) {
    return today.add(1, 'month').date(1);
  }

  // 处理"下个星期"或"下星期"
  if (dateStr.includes('下星期') || dateStr.includes('下个星期')) {
    return today.add(7, 'day');
  }

  // 尝试直接用 dayjs 解析（兜底）
  const fallback = dayjs(dateStr);
  return fallback.isValid() ? fallback : null;
};
