/**
 * 安全地将任意类型的地点数据转为可显示的字符串
 * - 字符串：直接返回
 * - 对象含 name：返回 name
 * - 对象含 lat/lng：返回 "lat, lng" 格式
 * - 其他：返回空字符串
 */
export function formatLocation(location: any): string {
  if (!location) return '';
  if (typeof location === 'string') return location;
  if (typeof location === 'object') {
    // 优先使用 name 字段
    if (location.name) return location.name;
    // 否则组合经纬度
    if (location.lat !== undefined && location.lng !== undefined) {
      return `${location.lat.toFixed(4)}, ${location.lng.toFixed(4)}`;
    }
    // 如果有 address 字段
    if (location.address) return location.address;
  }
  return '';
}

/**
 * 安全获取坐标数组 [lng, lat]，用于高德地图 API
 * 如果输入是 {lat, lng} 对象则转换，否则返回 null
 */
export function extractCoords(location: any): [number, number] | null {
  if (!location) return null;
  if (typeof location === 'object' && location.lat !== undefined && location.lng !== undefined) {
    return [location.lng, location.lat];
  }
  // 如果 location 是 "lng,lat" 字符串格式
  if (typeof location === 'string' && location.includes(',')) {
    const parts = location.split(',').map(Number);
    if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
      return [parts[0], parts[1]];
    }
  }
  return null;
}

export function extractLatLng(location: any): { lat: number; lng: number } | null {
  if (!location) return null;

  if (typeof location === 'object') {
    // 标准格式 {lat, lng}
    if (location.lat !== undefined && location.lng !== undefined) {
      return { lat: location.lat, lng: location.lng };
    }
    // 嵌套格式 {latLng: {lat, lng}}
    if (location.latLng && location.latLng.lat !== undefined) {
      return { lat: location.latLng.lat, lng: location.latLng.lng };
    }
  }

  // 🆕 支持字符串格式 "lng,lat" 或 "lat,lng"
  if (typeof location === 'string' && location.includes(',')) {
    const parts = location.split(',').map(Number);
    if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
      // 判断哪个是 lat/lng：lat 范围 -90~90，lng 范围 -180~180
      const a = parts[0], b = parts[1];
      if (a >= -90 && a <= 90 && b >= -180 && b <= 180) {
        return { lat: a, lng: b };   // "lat,lng"
      } else if (b >= -90 && b <= 90 && a >= -180 && a <= 180) {
        return { lat: b, lng: a };   // "lng,lat"
      }
    }
  }

  return null;
}