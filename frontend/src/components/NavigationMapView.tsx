import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Card, Button, Tag, Space, Typography, Spin, Empty, Alert } from 'antd';
import { CarOutlined, EnvironmentOutlined, ArrowRightOutlined, AimOutlined } from '@ant-design/icons';

const { Text } = Typography;

// 高德地图配置
const AMAP_JS_API_KEY = import.meta.env.VITE_AMAP_JS_API_KEY || '44d5a1d0ff67c65b57f1d9bb7291850d';
const AMAP_SECURITY_JS_CODE = import.meta.env.VITE_AMAP_SECURITY_JS_CODE || '15dc86f3be21a7853129ca4a5b76e58c';

// ==================== 类型定义 ====================

interface NavigationData {
  from: string;
  to: string;
  type: string;
  fromLocation?: { lat: number; lng: number } | null;
  toLocation?: { lat: number; lng: number } | null;
}

/** 出行方式类型 */
type TransportMode = 'driving' | 'walking' | 'bicycling' | 'transit';

interface RouteSegment {
  from: string;
  to: string;
  type: string;
  /** 当前选中的出行方式 */
  currentMode?: TransportMode;
  /** 支持的出行方式列表 */
  availableModes?: TransportMode[];
  fromLocation?: { lat: number; lng: number } | null;
  toLocation?: { lat: number; lng: number } | null;
  cityName?: string; // 新增城市名称字段，供公交换乘使用
}

interface LocationPoint {
  name: string;
  lat: number;
  lng: number;
  type: 'attraction' | 'hotel' | 'restaurant' | 'start' | 'end';
  day?: number;
}

interface NavigationMapViewProps {
  navigationData: NavigationData | null;
  allLocations?: LocationPoint[];
  cityName?: string;
}

/** 多路段地图组件的 Props */
interface MultiRouteMapProps {
  segments: RouteSegment[];
  allLocations?: LocationPoint[];
  visible: boolean;
  onClose?: () => void;
  cityName?: string;
}

// ==================== 工具函数 ====================

const getTransportTypeName = (type: string) => {
  switch (type) {
    case 'walking': return '步行';
    case 'driving': return '驾车';
    case 'transit': return '公交/地铁';
    case 'bicycling':
    case 'riding': return '骑行';
    default: return type;
  }
};

const getTransportTagColor = (type: string) => {
  switch (type) {
    case 'walking': return 'blue';
    case 'driving': return 'orange';
    case 'transit': return 'green';
    case 'bicycling':
    case 'riding': return 'purple';
    default: return 'default';
  }
};

const getTransportIcon = (type: string) => {
  switch (type) {
    case 'walking': return '🚶';
    case 'driving': return '🚗';
    case 'transit': return '🚇';
    case 'bicycling':
    case 'riding': return '🚴';
    default: return '🚗';
  }
};

const formatTime = (seconds: number): string => {
  if (!seconds || seconds <= 0) return '';
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}小时${mins}分钟`;
  return `${mins}分钟`;
};

const formatDistance = (meters: number): string => {
  if (!meters || meters <= 0) return '';
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)}公里`;
  return `${meters}米`;
};

// ==================== 高德地图 SDK 加载（单例） ====================
let amapLoadPromise: Promise<void> | null = null;

function loadAMapSDK(): Promise<void> {
  if (amapLoadPromise) return amapLoadPromise;
  amapLoadPromise = new Promise((resolve, reject) => {
    if ((window as any).AMap && (window as any).AMap.Map) { resolve(); return; }
    // 设置安全密钥（必须在脚本加载之前）
    (window as any)._AMapSecurityConfig = {
      securityJsCode: AMAP_SECURITY_JS_CODE
    };
    // 注册全局回调
    (window as any).onAMapLoad = () => {
      resolve();
    };
    const script = document.createElement('script');
    script.type = 'text/javascript';
    // 注意：不在 URL 中声明任何 plugin，全部按需加载
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_JS_API_KEY}&callback=onAMapLoad`;
    script.onerror = () => { amapLoadPromise = null; reject(new Error('高德地图API加载失败')); };
    document.head.appendChild(script);
  });
  return amapLoadPromise;
}

/** 清除地图上的路线覆盖物（兼容 Transfer 等特殊类型） */
function clearRouteOverlays(navigator: any): void {
  if (!navigator) return;
  try {
    navigator.clear();
  } catch (e) {
    console.warn('清除路线覆盖物失败:', e);
  }
  // Transfer 的 clear() 无法清除地图上已绘制的 Polyline/Marker
  // 遍历移除所有非 Marker 残留覆盖物
  try {
    if (navigator._map) {
      const overlays = navigator._map.getAllOverlays?.();
      if (overlays && overlays.length > 0) {
        const routeOverlays = overlays.filter((o: any) =>
          !(o instanceof (window as any).AMap.Marker)
        );
        if (routeOverlays.length > 0) {
          navigator._map.remove(routeOverlays);
        }
      }
    }
  } catch (e) {
    // ignore
  }
}

// ==================== QPS 限流器（确保 ≤ 3 QPS） ====================
/**
 * 创建一个请求队列，确保每秒最多发送 maxQPS 个请求。
 * 高德地图路线规划 API 的 QPS 限制为 3。
 */
function createRateLimiter(maxQPS: number = 3) {
  const queue: Array<() => Promise<void>> = [];
  let running = 0;
  let lastRequestTime = 0;

  async function processQueue() {
    if (queue.length === 0 || running >= 1) return; // 一次只处理一个，控制速率
    const now = Date.now();
    const timeSinceLast = now - lastRequestTime;
    const minInterval = 1000 / maxQPS; // 333ms

    if (timeSinceLast < minInterval) {
      // 还没到时间，延迟后再试
      setTimeout(processQueue, minInterval - timeSinceLast + 10);
      return;
    }

    running++;
    const task = queue.shift()!;
    try {
      lastRequestTime = Date.now();
      await task();
    } finally {
      running--;
      // 等待 minInterval 再处理下一个
      setTimeout(processQueue, minInterval);
    }
  }

  return {
    enqueue: (task: () => Promise<void>) => {
      queue.push(task);
      processQueue();
    },
    getQueueLength: () => queue.length,
  };
}

/** 全局 QPS 限流器实例 */
const routeSearchLimiter = createRateLimiter(3);

function createNavigator(mode: string, map: any, panelEl?: HTMLElement | string | null, city?: string): Promise<any> {
  // 统一 riding → bicycling
  const normalizedMode = mode === 'riding' ? 'bicycling' : mode;
  const baseOptions: any = { map, hideMarkers: false };

  // 如果传入了 panel 元素，将其 ID 或元素传给规划器，高德会自动填充分步指引
  if (panelEl) {
    baseOptions.panel = panelEl;
  }

  return new Promise((resolve) => {
    switch (normalizedMode) {
      case 'walking':
        (window as any).AMap.plugin('AMap.Walking', () => {
          resolve(new (window as any).AMap.Walking(baseOptions));
        });
        break;
      case 'bicycling':
        (window as any).AMap.plugin('AMap.Riding', () => {
          resolve(new (window as any).AMap.Riding(baseOptions));
        });
        break;
      case 'transit':
        (window as any).AMap.plugin('AMap.Transfer', () => {
          baseOptions.city = city || '北京';
          baseOptions.policy = (window as any).AMap.TransferPolicy?.LEAST_TIME || 0;
          const transitOptions = { ...baseOptions };
          delete transitOptions.hideMarkers;
          resolve(new (window as any).AMap.Transfer(transitOptions));
        });
        break;
      case 'driving':
      default:
        (window as any).AMap.plugin('AMap.Driving', () => {
          baseOptions.policy = (window as any).AMap.DrivingPolicy?.LEAST_TIME || 0;
          baseOptions.showTraffic = true;
          resolve(new (window as any).AMap.Driving(baseOptions));
        });
        break;
    }
  });
}
/**
 * 受 QPS 限制的路线搜索
 * 将 navigator.search() 包装为 Promise，通过全局限流器控制并发
 */
function searchRoute(
  navigator: any,
  origin: any,
  destination: any,
  options?: { cancelledRef?: React.MutableRefObject<boolean> }
): Promise<{ status: string; result: any }> {
  return new Promise((resolve) => {
    routeSearchLimiter.enqueue(async () => {
      if (options?.cancelledRef?.current) {
        resolve({ status: 'cancelled', result: null });
        return;
      }
      try {
        navigator.search(origin, destination, (status: string, result: any) => {
          resolve({ status, result });
        });
      } catch (error) {
        console.error('路线搜索异常:', error);
        resolve({ status: 'error', result: { info: (error as Error).message } });
      }
    });
  });
}

/** 检查坐标对象是否有效 */
function isValidCoord(location: { lat: number; lng: number } | null | undefined): boolean {
  return !!(location && typeof location.lat === 'number' && typeof location.lng === 'number'
    && isFinite(location.lat) && isFinite(location.lng));
}

// 获取起点终点（带坐标有效性校验，无效时降级为文本地址）
function getOriginDest(segment: RouteSegment) {
  let origin: any = segment.from;
  let destination: any = segment.to;

  if (isValidCoord(segment.fromLocation)) {
    const lng = segment.fromLocation!.lng;
    const lat = segment.fromLocation!.lat;
    if (!isNaN(lng) && !isNaN(lat) && isFinite(lng) && isFinite(lat)) {
      origin = [lng, lat];
    }
  }

  if (isValidCoord(segment.toLocation)) {
    const lng = segment.toLocation!.lng;
    const lat = segment.toLocation!.lat;
    if (!isNaN(lng) && !isNaN(lat) && isFinite(lng) && isFinite(lat)) {
      destination = [lng, lat];
    }
  }

  return { origin, destination };
}

// 添加标记点
function addMarkers(map: any, allLocations: LocationPoint[]): any[] {
  const markers: any[] = [];
  const colorMap: Record<string, string> = {
    attraction: '#1890ff', hotel: '#722ed1', restaurant: '#fa8c16', start: '#52c41a', end: '#ff4d4f',
  };
  const labelMap: Record<string, string> = {
    attraction: '🏛️', hotel: '🏨', restaurant: '🍽️', start: '🚩', end: '🏁',
  };
  allLocations.forEach((loc) => {
    const marker = new (window as any).AMap.Marker({
      position: [loc.lng, loc.lat], map: map,
      label: {
        content: `<div style="background:${colorMap[loc.type] || '#666'};color:white;padding:2px 6px;border-radius:4px;font-size:12px;white-space:nowrap">${labelMap[loc.type] || '📍'} ${loc.name}</div>`,
        direction: 'top',
      },
    });
    markers.push(marker);
  });
  return markers;
}

// ==================== 多路段地图组件（带时间轴+出行方式切换+详细面板） ====================
const TRANSPORT_MODES: TransportMode[] = ['driving', 'walking', 'bicycling', 'transit'];
const TRANSPORT_MODE_LABELS: Record<TransportMode, string> = {
  driving: '驾车', walking: '步行', bicycling: '骑行', transit: '公交',
};

const MultiRouteMapModal: React.FC<MultiRouteMapProps> = ({
  visible,
  segments,
  allLocations,
  cityName
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const currentRouteRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const cancelledRef = useRef(false);

  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [routeSummary, setRouteSummary] = useState<{ distance: string; duration: string; mode: string } | null>(null);
  // 跟踪每个路段当前选的出行方式
  const [segmentModes, setSegmentModes] = useState<TransportMode[]>(() =>
    segments.map(s => (s.currentMode || s.type || 'driving') as TransportMode)
  );

  // 当 segments 变化时重置出行方式
  useEffect(() => {
    setSegmentModes(segments.map(s => (s.currentMode || s.type || 'driving') as TransportMode));
  }, [segments]);

  const getEffectiveSegment = useCallback((index: number): RouteSegment => {
    return { ...segments[index], type: segmentModes[index] };
  }, [segments, segmentModes]);

    const planRoute = useCallback(async (map: any, segmentIndex: number, panelEl?: HTMLElement | null, overrideMode?: TransportMode) => {
    // 如果传入了 overrideMode，使用它创建临时 segment
    const effectiveSegment = overrideMode
      ? { ...segments[segmentIndex], type: overrideMode }
      : getEffectiveSegment(segmentIndex);

        // 1) 清除旧路线（兼容 Transfer/Driving 等不同类型）
    if (currentRouteRef.current) {
      clearRouteOverlays(currentRouteRef.current);
      currentRouteRef.current = null;
    }

    // 2) 清空 panel（高德会重新填充）
    if (panelEl) {
      panelEl.innerHTML = '';
    }

        // 3) 创建新规划器（createNavigator 现在是 async，需要 await）
    const { origin, destination } = getOriginDest(effectiveSegment);
    const segCity = effectiveSegment.cityName || cityName;
    const navigator = await createNavigator(effectiveSegment.type, map,panelEl, segCity);
    currentRouteRef.current = navigator;

    setRouteSummary(null);
    setLoadError(null);

        // 4) 搜索路线（通过 QPS 限流器）
    const { status, result } = await searchRoute(navigator, origin, destination, { cancelledRef });

    if (cancelledRef.current) return;

    if (status === 'complete') {
      map.setFitView();
      // 公交换乘（Transfer）的返回结果是 plans，而非 routes
      const isTransit = effectiveSegment.type === 'transit';
      if (isTransit && result.plans && result.plans[0]) {
        const plan = result.plans[0];
        setRouteSummary({
          distance: formatDistance(plan.distance),
          duration: formatTime(plan.time),
          mode: getTransportTypeName(effectiveSegment.type),
        });
      } else if (!isTransit && result.routes && result.routes[0]) {
        const route = result.routes[0];
        setRouteSummary({
          distance: formatDistance(route.distance),
          duration: formatTime(route.time),
          mode: getTransportTypeName(effectiveSegment.type),
        });
      }
    } else {
      const errMsg = result?.info || '路线规划失败，请检查地址';
      setLoadError(errMsg);
      if (panelEl) {
        panelEl.innerHTML = `<div style="padding:12px 16px;color:#ff4d4f;text-align:center;">❌ ${errMsg}</div>`;
      }
    }
  }, [segments, getEffectiveSegment]);


  /** 切换出行方式 */
  const handleModeChange = useCallback(async (newMode: TransportMode) => {
      if (!mapInstanceRef.current) return;

      // 先取消正在进行的旧搜索
      cancelledRef.current = true;
      await new Promise(resolve => setTimeout(resolve, 100));
      cancelledRef.current = false;

      // 通过地图直接清除所有非 Marker 残留覆盖物
      const map = mapInstanceRef.current;
      if (currentRouteRef.current) {
        clearRouteOverlays(currentRouteRef.current);
        currentRouteRef.current = null;
      }
      try {
        const overlays = map.getAllOverlays?.() || [];
        const toRemove = overlays.filter((o: any) =>
          !(o instanceof (window as any).AMap.Marker)
        );
        if (toRemove.length > 0) map.remove(toRemove);
      } catch (e) { /* ignore */ }

      setLoading(true);
      setSegmentModes(prev => {
        const updated = [...prev];
        updated[activeIndex] = newMode;
        return updated;
      });
      const panelEl = panelRef.current;
      await planRoute(map, activeIndex, panelEl, newMode);
      setLoading(false);
    }, [activeIndex, planRoute]);

  // 初始化/重建地图
  useEffect(() => {
    if (!visible || !mapRef.current || segments.length === 0) return;

    let localCancelled = false;
    cancelledRef.current = false;
    setLoading(true);
    setLoadError(null);
    setActiveIndex(0);

    const initMap = async () => {
      try {
        await loadAMapSDK();
        if (localCancelled) return;

                // 销毁旧实例 + 清除旧路线
        if (currentRouteRef.current) {
          clearRouteOverlays(currentRouteRef.current);
          currentRouteRef.current = null;
        }
        if (mapInstanceRef.current) {
          mapInstanceRef.current.destroy();
          mapInstanceRef.current = null;
        }
        markersRef.current = [];

        const map = new (window as any).AMap.Map(mapRef.current, {
          viewMode: '2D', zoom: 12, center: [116.397428, 39.90923],
        });
        mapInstanceRef.current = map;

         (window as any).AMap.plugin(['AMap.ToolBar', 'AMap.Scale'], () => {
         try {
              map.addControl(new (window as any).AMap.ToolBar({ position: 'RT' }));
              map.addControl(new (window as any).AMap.Scale({ position: 'LB' }));
            } catch (e) { /* ignore */ }
          });

        if (allLocations && allLocations.length > 0) {
          markersRef.current = addMarkers(map, allLocations);
        }

        // 规划第一个路段
        const panelEl = panelRef.current;
        await planRoute(map, 0, panelEl);

       // 绘制其他路段的背景线（带错误保护，失败也不影响主流程）
      if (segments.length > 1) {
        for (let i = 1; i < segments.length; i++) {
          if (localCancelled) break;
          try {
            const effSeg = getEffectiveSegment(i);
            const { origin, destination } = getOriginDest(effSeg);
            const bgNavigator = await createNavigator(effSeg.type, map, effSeg.cityName || cityName);
            await searchRoute(bgNavigator, origin, destination, { cancelledRef });
          } catch (e) {
            console.warn(`背景线 ${i} 规划失败，跳过:`, e);
          }
        }
      }

        if (!localCancelled) setLoading(false);
      } catch (error) {
        if (!localCancelled) {
          setLoading(false);
          setLoadError(`地图加载失败: ${(error as Error).message}`);
        }
      }
    };

    initMap();

        return () => {
      localCancelled = true;
      cancelledRef.current = true;
      if (currentRouteRef.current) {
        clearRouteOverlays(currentRouteRef.current);
        currentRouteRef.current = null;
      }
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy();
        mapInstanceRef.current = null;
      }
    };
  }, [visible, segments, allLocations]);

  // 切换路段时重新规划
  useEffect(() => {
    if (!mapInstanceRef.current || !visible || segments.length === 0) return;
    const map = mapInstanceRef.current;
    const panelEl = panelRef.current;
    const doPlan = async () => {
      setLoading(true);
      await planRoute(map, activeIndex, panelEl);
      setLoading(false);
    };
    doPlan();
  }, [activeIndex, visible, planRoute, segments.length]);

  if (segments.length === 0) {
    return <Empty description="暂无路线数据" />;
  }

  return (
    <div>
      {/* 路段选择时间轴 */}
      {segments.length > 1 && (
        <div style={{
          marginBottom: 12, padding: '8px 12px', background: '#fafafa',
          borderRadius: 8, border: '1px solid #f0f0f0',
        }}>
          <Text strong style={{ fontSize: 13, marginBottom: 8, display: 'block' }}>
            📍 选择路段查看详细导航
          </Text>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {segments.map((seg, idx) => (
              <div
                key={idx}
                onClick={() => setActiveIndex(idx)}
                style={{
                  cursor: 'pointer', padding: '6px 12px', borderRadius: 6,
                  background: idx === activeIndex ? '#e6f7ff' : '#fff',
                  border: idx === activeIndex ? '1.5px solid #1890ff' : '1px solid #d9d9d9',
                  display: 'flex', alignItems: 'center', gap: 6, fontSize: 12,
                  transition: 'all 0.2s', flex: '1 1 auto', minWidth: 120,
                }}
              >
                <Tag color={getTransportTagColor(segmentModes[idx])} style={{ margin: 0, fontSize: 11 }}>
                  {getTransportIcon(segmentModes[idx])} {getTransportTypeName(segmentModes[idx])}
                </Tag>
                <Text style={{ fontSize: 12 }}>{seg.from} → {seg.to}</Text>
                {idx === activeIndex && (
                  <Tag color="blue" style={{ margin: 0, fontSize: 10 }}>当前</Tag>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 当前路段的出行方式切换按钮组 */}
      <div style={{ marginBottom: 8, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>出行方式：</Text>
        {TRANSPORT_MODES.map(mode => (
          <Tag
            key={mode}
            color={segmentModes[activeIndex] === mode ? getTransportTagColor(mode) : 'default'}
            style={{
              cursor: 'pointer', fontSize: 12, padding: '2px 8px',
              opacity: segmentModes[activeIndex] === mode ? 1 : 0.6,
            }}
            onClick={() => {
              if (segmentModes[activeIndex] !== mode && !loading) {
                handleModeChange(mode);
              }
            }}
          >
            {getTransportIcon(mode)} {TRANSPORT_MODE_LABELS[mode]}
          </Tag>
        ))}
        {loading && <Spin size="small" style={{ marginLeft: 8 }} />}
      </div>

      {/* 当前路段的摘要信息 */}
      {routeSummary && !loading && (
        <div style={{
          background: '#f0f5ff', borderRadius: 8, padding: '8px 16px',
          marginBottom: 8, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <Text><EnvironmentOutlined style={{ color: '#52c41a' }} /> {segments[activeIndex].from}</Text>
          <ArrowRightOutlined style={{ color: '#1890ff', fontSize: 12 }} />
          <Text><EnvironmentOutlined style={{ color: '#ff4d4f' }} /> {segments[activeIndex].to}</Text>
          <Tag color={getTransportTagColor(segmentModes[activeIndex])}>
            {getTransportIcon(segmentModes[activeIndex])} {routeSummary.mode}
          </Tag>
          {routeSummary.distance && <Tag color="green">📏 {routeSummary.distance}</Tag>}
          {routeSummary.duration && <Tag color="blue">⏱ {routeSummary.duration}</Tag>}
        </div>
      )}

      {/* 加载错误提示 */}
      {loadError && !loading && !loadError.includes('地图加载失败') && (
        <Alert message="路线规划提示" description={loadError} type="warning" showIcon
          style={{ marginBottom: 8 }} closable onClose={() => setLoadError(null)} />
      )}
      {/* 地图区域 */}
      <div style={{ position: 'relative', minHeight: '200px' }}>
        {loading && (
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#f5f5f5', borderRadius: '8px', zIndex: 1,
          }}>
            <Spin tip={loadError ? '加载中...' : '正在规划路线...'} />
          </div>
        )}
        <div ref={mapRef} style={{
          width: '100%', height: '400px', borderRadius: '8px',
          visibility: loading ? 'hidden' : 'visible',
          position: 'relative', zIndex: 0,
        }} />
      </div>

      {/* 高德自动填充的详细导航面板 — 没有初始占位文字 */}
      <div
        ref={panelRef}
        id="route-panel-content"
        style={{
          marginTop: 12, maxHeight: '300px', overflowY: 'auto',
          background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0', fontSize: 13,
        }}
      />
    </div>
  );
};

// ==================== 单路段地图组件（兼容原有 NavigationData） ====================
const SingleRouteMapModal: React.FC<{
  visible: boolean;
  navigationData: NavigationData;
  allLocations?: LocationPoint[];
  cityName?: string;
  onClose?: () => void;
}> = ({ visible, navigationData, allLocations, cityName}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const currentRouteRef = useRef<any>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [routeSummary, setRouteSummary] = useState<{ distance: string; duration: string; mode: string } | null>(null);

  useEffect(() => {
    if (!visible || !mapRef.current) return;

    let cancelled = false;
    setLoading(true);
    setLoadError(null);

    const initMap = async () => {
      try {
        await loadAMapSDK();
        if (cancelled) return;

        if (mapInstanceRef.current) {
          mapInstanceRef.current.destroy();
          mapInstanceRef.current = null;
        }

        const map = new (window as any).AMap.Map(mapRef.current, {
          viewMode: '2D', zoom: 12, center: [116.397428, 39.90923],
        });
        mapInstanceRef.current = map;

      (window as any).AMap.plugin(['AMap.ToolBar', 'AMap.Scale'], () => {
        try {
          map.addControl(new (window as any).AMap.ToolBar({ position: 'RT' }));
          map.addControl(new (window as any).AMap.Scale({ position: 'LB' }));
        } catch (e) { /* ignore */ }
      });
        

        if (allLocations && allLocations.length > 0) {
          addMarkers(map, allLocations);
        }

        // 规划路线
        const { origin, destination } = {
          origin: navigationData.fromLocation
            ? [navigationData.fromLocation.lng, navigationData.fromLocation.lat]
            : navigationData.from,
          destination: navigationData.toLocation
            ? [navigationData.toLocation.lng, navigationData.toLocation.lat]
            : navigationData.to,
        };

        const navigator = await createNavigator(navigationData.type, map, panelRef.current, cityName);
        currentRouteRef.current = navigator;

        setRouteSummary(null);

                // 先在 panel 中清空旧内容
        if (panelRef.current) {
          panelRef.current.innerHTML = '';
        }

        const { status, result } = await searchRoute(navigator, origin, destination);

        if (cancelled) return;
        setLoading(false);

        if (status === 'complete') {
          map.setFitView();
          // 公交换乘（Transfer）的返回结果是 plans，而非 routes
          const isTransit = navigationData.type === 'transit';
          if (isTransit && result.plans && result.plans[0]) {
            const plan = result.plans[0];
            setRouteSummary({
              distance: formatDistance(plan.distance),
              duration: formatTime(plan.time),
              mode: getTransportTypeName(navigationData.type),
            });
          } else if (!isTransit && result.routes && result.routes[0]) {
            const route = result.routes[0];
            setRouteSummary({
              distance: formatDistance(route.distance),
              duration: formatTime(route.time),
              mode: getTransportTypeName(navigationData.type),
            });
          }
          // 规划成功后，高德会自动填充 panel，无需手动操作
        } else {
          if (allLocations && allLocations.length > 0) {
            setTimeout(() => map.setFitView(), 500);
            setLoadError('路线规划失败，但已显示景点位置');
          } else {
            setLoadError(result?.info || '路线规划失败');
          }
          // 规划失败时在 panel 显示错误
          if (panelRef.current) {
            panelRef.current.innerHTML = `<div style="padding: 12px 16px; color: #ff4d4f; text-align: center;">
              ❌ 路线规划失败：${result?.info || '请检查起点和终点地址是否准确'}
            </div>`;
          }
        }

        if (!cancelled) setTimeout(() => setLoading(false), 1000);

      } catch (error) {
        if (!cancelled) {
          setLoading(false);
          setLoadError(`地图加载失败: ${(error as Error).message}`);
        }
      }
    };

    initMap();

        return () => {
      cancelled = true;
      if (currentRouteRef.current) {
        clearRouteOverlays(currentRouteRef.current);
        currentRouteRef.current = null;
      }
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy();
        mapInstanceRef.current = null;
      }
    };
  }, [visible, navigationData, allLocations]);

  return (
    <div>
      {/* 摘要信息 */}
      {routeSummary && (
        <div style={{
          background: '#f0f5ff', borderRadius: 8, padding: '8px 16px',
          marginBottom: 8, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <Text><EnvironmentOutlined style={{ color: '#52c41a' }} /> {navigationData.from}</Text>
          <ArrowRightOutlined style={{ color: '#1890ff', fontSize: 12 }} />
          <Text><EnvironmentOutlined style={{ color: '#ff4d4f' }} /> {navigationData.to}</Text>
          <Tag color={getTransportTagColor(navigationData.type)}>
            {getTransportIcon(navigationData.type)} {routeSummary.mode}
          </Tag>
          {routeSummary.distance && <Tag color="green">📏 {routeSummary.distance}</Tag>}
          {routeSummary.duration && <Tag color="blue">⏱ {routeSummary.duration}</Tag>}
        </div>
      )}

      {/* 地图 */}
      <div style={{ position: 'relative', minHeight: '200px' }}>
        {loading && (
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#f5f5f5', borderRadius: '8px', zIndex: 1,
          }}>
            <Spin tip="加载地图中..." />
          </div>
        )}
        {loadError && !loading && !loadError.includes('地图加载失败') && (
          <Alert message="地图加载提示" description={loadError} type="warning" showIcon
            style={{ marginBottom: 8, position: 'relative', zIndex: 1 }}
            closable onClose={() => setLoadError(null)} />
        )}
        <div ref={mapRef} style={{
          width: '100%', height: '400px', borderRadius: '8px',
          visibility: loading ? 'hidden' : 'visible', position: 'relative', zIndex: 0,
        }} />
      </div>

      {/* 详细导航面板 */}
      <div
        ref={panelRef}
        style={{
          marginTop: 12, maxHeight: '300px', overflowY: 'auto',
          background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0', fontSize: 13,
        }}
      >
        {/*高德会自动填充路线详情到此面板*/}
      </div>
    </div>
  );
};

// ==================== 主组件（判断使用单路段还是多路段） ====================
const NavigationMapView: React.FC<NavigationMapViewProps> = ({
  navigationData,
  allLocations,
  cityName,
}) => {
  const [showMap, setShowMap] = useState(false);

  if (!navigationData) {
    return (
      <Card size="small" style={{ marginBottom: 8 }}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无导航路线数据" />
      </Card>
    );
  }

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, border: '1px solid #d6e4ff' }}
      styles={{ header: { backgroundColor: '#f0f5ff', padding: '8px 12px' } }}
      title={
        <Space>
          <CarOutlined style={{ color: '#1890ff' }} />
          <Text strong>导航路线</Text>
        </Space>
      }
      extra={
        <Button type="primary" size="small" icon={<AimOutlined />}
          onClick={() => setShowMap(!showMap)}>
          {showMap ? '隐藏地图' : '显示地图'}
        </Button>
      }
    >
      {/* 路线概要（用格式化保护） */}
      <div style={{ background: '#f0f5ff', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <Tag icon={<CarOutlined />} color={getTransportTagColor(navigationData.type)}>
            {getTransportTypeName(navigationData.type)}
          </Tag>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Text><EnvironmentOutlined style={{ color: '#52c41a' }} /> {String(navigationData.from)}</Text>
          <ArrowRightOutlined style={{ color: '#1890ff' }} />
          <Text><EnvironmentOutlined style={{ color: '#ff4d4f' }} /> {String(navigationData.to)}</Text>
        </div>
      </div>

      {/* 地图 */}
      {showMap && (
        <div style={{ marginTop: 12 }}>
          <SingleRouteMapModal
            visible={showMap}
            navigationData={navigationData}
            allLocations={allLocations}
            cityName={cityName}
            onClose={() => setShowMap(false)}
          />
        </div>
      )}
    </Card>
  );
};


// ==================== 按需加载的多路段地图组件（带"显示路线"按钮控制） ====================
interface DayMultiRouteMapProps {
  segments: RouteSegment[];
  allLocations?: LocationPoint[];
  cityName?: string;
}

const DayMultiRouteMap: React.FC<DayMultiRouteMapProps> = ({
  segments,
  allLocations,
  cityName,
}) => {
  const [showMap, setShowMap] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  const mapRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const currentRouteRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const cancelledRef = useRef(false);

  const [activeIndex, setActiveIndex] = useState(0);
  const [routeSummary, setRouteSummary] = useState<{ distance: string; duration: string; mode: string } | null>(null);
  // 跟踪每个路段当前选的出行方式
  const [segmentModes, setSegmentModes] = useState<string[]>(() =>
    segments.map(s => (s.currentMode || s.type || 'driving') as TransportMode)
  );

  // 当 segments 变化时重置出行方式
  useEffect(() => {
    setSegmentModes(segments.map(s => (s.currentMode || s.type || 'driving') as TransportMode));
  }, [segments]);

  /** 获取当前有效 segment（合并当前选中的出行方式） */
  const getEffectiveSegment = useCallback((index: number): RouteSegment => {
    return { ...segments[index], type: segmentModes[index] };
  }, [segments, segmentModes]);

  /** 规划指定路段路线（返回 Promise，确保规划完成） */
    const planRoute = useCallback(async (map: any, segmentIndex: number, panelEl?: HTMLElement | null, overrideMode?: string) => {
    // 如果传入了 overrideMode，直接用它创建 segment，不依赖 state
    const effectiveSegment = overrideMode
      ? { ...segments[segmentIndex], type: overrideMode }
      : getEffectiveSegment(segmentIndex);

        // 1) 清除旧路线（兼容 Transfer/Driving 等不同类型）
    if (currentRouteRef.current) {
      clearRouteOverlays(currentRouteRef.current);
      currentRouteRef.current = null;
    }

    // 2) 清空 panel（高德会重新填充）
    if (panelEl) {
      panelEl.innerHTML = '';
    }

        // 3) 创建新规划器（createNavigator 现在是 async，需要 await）
    const { origin, destination } = getOriginDest(effectiveSegment);
    const segCity = effectiveSegment.cityName || cityName;
    const navigator = await createNavigator(effectiveSegment.type, map, panelEl, segCity);
    currentRouteRef.current = navigator;

    setRouteSummary(null);
    setLoadError(null);

        // 4) 搜索路线（通过 QPS 限流器）
    const { status, result } = await searchRoute(navigator, origin, destination, { cancelledRef });

    if (cancelledRef.current) return;

    if (status === 'complete') {
      map.setFitView();
      // 公交换乘（Transfer）的返回结果是 plans，而非 routes
      const isTransit = effectiveSegment.type === 'transit';
      if (isTransit && result.plans && result.plans[0]) {
        const plan = result.plans[0];
        setRouteSummary({
          distance: formatDistance(plan.distance),
          duration: formatTime(plan.time),
          mode: getTransportTypeName(effectiveSegment.type),
        });
      } else if (!isTransit && result.routes && result.routes[0]) {
        const route = result.routes[0];
        setRouteSummary({
          distance: formatDistance(route.distance),
          duration: formatTime(route.time),
          mode: getTransportTypeName(effectiveSegment.type),
        });
      }
    } else {
      const errMsg = result?.info || '路线规划失败，请检查地址';
      setLoadError(errMsg);
      if (panelEl) {
        panelEl.innerHTML = `<div style="padding:12px 16px;color:#ff4d4f;text-align:center;">❌ ${errMsg}</div>`;
      }
    }
  }, [segments, getEffectiveSegment]);
  /** 切换出行方式 */
  const handleModeChange = useCallback(async (newMode: string) => {
      if (!mapInstanceRef.current) return;

      cancelledRef.current = true;
      await new Promise(resolve => setTimeout(resolve, 50));
      cancelledRef.current = false;


      setLoading(true);
      setSegmentModes(prev => {
        const updated = [...prev];
        updated[activeIndex] = newMode as TransportMode;
        return updated;
      });
      const map = mapInstanceRef.current;
      const panelEl = panelRef.current;
      await planRoute(map, activeIndex, panelEl, newMode);
      setLoading(false);
    }, [activeIndex, planRoute]);


  const segmentModesRef = useRef(segmentModes);
  useEffect(() => { segmentModesRef.current = segmentModes; }, [segmentModes]);

  /** 初始化地图 + 只规划当前选中路段 */
  const initMap = useCallback(async () => {
    if (!mapRef.current || segments.length === 0) return;
    let localCancelled = false;
    cancelledRef.current = false;
    setLoading(true);
    setLoadError(null);
    setActiveIndex(0);

    try {
      await loadAMapSDK();
      if (localCancelled) return;

      // 清理旧实例
      if (currentRouteRef.current) {
        clearRouteOverlays(currentRouteRef.current);
        currentRouteRef.current = null;
      }
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy();
        mapInstanceRef.current = null;
      }
      markersRef.current = [];

      const map = new (window as any).AMap.Map(mapRef.current, {
        viewMode: '2D', zoom: 12, center: [116.397428, 39.90923],
      });
      mapInstanceRef.current = map;

    (window as any).AMap.plugin(['AMap.ToolBar', 'AMap.Scale'], () => {
      try {
        map.addControl(new (window as any).AMap.ToolBar({ position: 'RT' }));
        map.addControl(new (window as any).AMap.Scale({ position: 'LB' }));
      } catch (e) { /* ignore */ }
    });

      if (allLocations && allLocations.length > 0) {
        markersRef.current = addMarkers(map, allLocations);
      }

      // 规划第一个路段
      const latestModes = segmentModesRef.current;
      const firstSegment = { ...segments[0], type: latestModes[0] || segments[0].type };
      const { origin: firstOrigin, destination: firstDest } = getOriginDest(firstSegment);
      const firstCity = latestModes[0] === 'transit' ? (cityName || segments[0].cityName) : undefined;
      const firstNavigator = await createNavigator(firstSegment.type, map, panelRef.current, firstCity);
      currentRouteRef.current = firstNavigator;
      await searchRoute(firstNavigator, firstOrigin, firstDest, { cancelledRef });
      map.setFitView();

      if (!localCancelled) {
        setLoading(false);
        setMapLoaded(true);
      }
    } catch (error) {
      if (!localCancelled) {
        setLoading(false);
        setLoadError(`地图加载失败: ${(error as Error).message}`);
      }
    }
  }, [segments, allLocations]);

  // 切换路段时重新规划
  useEffect(() => {
    if (!mapInstanceRef.current || !showMap || segments.length === 0) return;
    const map = mapInstanceRef.current;
    const panelEl = panelRef.current;
    const doPlan = async () => {
      setLoading(true);
      await planRoute(map, activeIndex, panelEl);
      setLoading(false);
    };
    doPlan();
    // 注意：不能把 planRoute 作为依赖，否则循环
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, showMap, segments.length]);

  // 点击按钮处理
  const handleToggleMap = () => {
    if (showMap) {
      // 隐藏地图：销毁实例
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy();
        mapInstanceRef.current = null;
      }
      markersRef.current = [];
      currentRouteRef.current = null;
      setMapLoaded(false);
      setRouteSummary(null);
      setShowMap(false);
    } else {
      setShowMap(true);
    }
  };

  // showMap 变为 true 时初始化地图
  useEffect(() => {
    if (!showMap || !mapRef.current || segments.length === 0 || mapLoaded) return;
    const timer = setTimeout(() => {
      initMap();
    }, 100);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMap, mapRef.current, initMap, mapLoaded, segments.length]);

    // 组件卸载时清理
  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      if (currentRouteRef.current) {
        clearRouteOverlays(currentRouteRef.current);
        currentRouteRef.current = null;
      }
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  if (segments.length === 0) {
    return null;
  }

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, border: '1px solid #d6e4ff' }}
      styles={{ header: { backgroundColor: '#f0f5ff', padding: '8px 12px' } }}
      title={
        <Space>
          <CarOutlined style={{ color: '#1890ff' }} />
          <Text strong>导航路线</Text>
        </Space>
      }
      extra={
        <Button
          type="primary"
          size="small"
          icon={!showMap && !loading ? <AimOutlined /> : undefined}
          loading={loading}
          disabled={loading}
          onClick={handleToggleMap}
        >
          {loading ? '⏳ 正在加载路线...' : showMap ? '🗺️ 隐藏路线' : '🗺️ 显示路线'}
        </Button>
      }
    >
      {/* 地图未显示时展示文字提示 */}
      {!showMap && !loading && (
        <div style={{
          padding: '16px', textAlign: 'center', color: '#999',
          background: '#fafafa', borderRadius: 6,
        }}>
          <EnvironmentOutlined style={{ fontSize: 24, marginBottom: 8, display: 'block' }} />
          <Text type="secondary">点击上方"显示路线"按钮查看本日导航路线</Text>
        </div>
      )}

      {/* 以下内容只有 showMap 为 true 时才渲染 */}
      {showMap && (
        <>
          {/* 路段选择时间轴 */}
          {segments.length > 1 && (
            <div style={{
              marginBottom: 12, padding: '8px 12px', background: '#fafafa',
              borderRadius: 8, border: '1px solid #f0f0f0',
            }}>
              <Text strong style={{ fontSize: 13, marginBottom: 8, display: 'block' }}>
                📍 选择路段查看详细导航
              </Text>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {segments.map((seg, idx) => (
                  <div
                    key={idx}
                    onClick={() => setActiveIndex(idx)}
                    style={{
                      cursor: 'pointer', padding: '6px 12px', borderRadius: 6,
                      background: idx === activeIndex ? '#e6f7ff' : '#fff',
                      border: idx === activeIndex ? '1.5px solid #1890ff' : '1px solid #d9d9d9',
                      display: 'flex', alignItems: 'center', gap: 6, fontSize: 12,
                      transition: 'all 0.2s', flex: '1 1 auto', minWidth: 120,
                    }}
                  >
                    <Tag color={getTransportTagColor(segmentModes[idx])} style={{ margin: 0, fontSize: 11 }}>
                      {getTransportIcon(segmentModes[idx])} {getTransportTypeName(segmentModes[idx])}
                    </Tag>
                    <Text style={{ fontSize: 12 }}>{seg.from} → {seg.to}</Text>
                    {idx === activeIndex && (
                      <Tag color="blue" style={{ margin: 0, fontSize: 10 }}>当前</Tag>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 当前路段的出行方式切换按钮组 */}
          <div style={{ marginBottom: 8, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>出行方式：</Text>
            {(['driving', 'walking', 'bicycling', 'transit'] as TransportMode[]).map(mode => (
              <Tag
                key={mode}
                color={segmentModes[activeIndex] === mode ? getTransportTagColor(mode) : 'default'}
                style={{
                  cursor: 'pointer', fontSize: 12, padding: '2px 8px',
                  opacity: segmentModes[activeIndex] === mode ? 1 : 0.6,
                }}
                onClick={() => {
                  if (segmentModes[activeIndex] !== mode && !loading) {
                    handleModeChange(mode);
                  }
                }}
              >
                {getTransportIcon(mode)} {getTransportTypeName(mode)}
              </Tag>
            ))}
            {loading && <Spin size="small" style={{ marginLeft: 8 }} />}
          </div>

          {/* 当前路段的摘要信息 */}
          {routeSummary && !loading && (
            <div style={{
              background: '#f0f5ff', borderRadius: 8, padding: '8px 16px',
              marginBottom: 8, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap',
            }}>
              <Text><EnvironmentOutlined style={{ color: '#52c41a' }} /> {segments[activeIndex].from}</Text>
              <ArrowRightOutlined style={{ color: '#1890ff', fontSize: 12 }} />
              <Text><EnvironmentOutlined style={{ color: '#ff4d4f' }} /> {segments[activeIndex].to}</Text>
              <Tag color={getTransportTagColor(segmentModes[activeIndex])}>
                {getTransportIcon(segmentModes[activeIndex])} {routeSummary.mode}
              </Tag>
              {routeSummary.distance && <Tag color="green">📏 {routeSummary.distance}</Tag>}
              {routeSummary.duration && <Tag color="blue">⏱ {routeSummary.duration}</Tag>}
            </div>
          )}

          {/* 加载错误提示 */}
          {loadError && !loading && !loadError.includes('地图加载失败') && (
            <Alert message="路线规划提示" description={loadError} type="warning" showIcon
              style={{ marginBottom: 8 }} closable onClose={() => setLoadError(null)} />
          )}

          {/* 地图区域 — 始终显示地图 div，不因 loadError 隐藏 */}
          <div style={{ position: 'relative', minHeight: '200px' }}>
            {loading && (
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#f5f5f5', borderRadius: '8px', zIndex: 1,
              }}>
                <Spin tip={loadError ? '加载中...' : '正在规划路线...'} />
              </div>
            )}
            <div ref={mapRef} style={{
              width: '100%', height: '400px', borderRadius: '8px',
              visibility: loading ? 'hidden' : 'visible',
              position: 'relative', zIndex: 0,
            }} />
          </div>

          {/* 详细导航面板 — 没有初始占位文字 */}
          <div
            ref={panelRef}
            id="route-panel-content"
            style={{
              marginTop: 12, maxHeight: '300px', overflowY: 'auto',
              background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0', fontSize: 13,
            }}
          />
        </>
      )}
    </Card>
  );
};

export { NavigationMapView, MultiRouteMapModal, DayMultiRouteMap };
export type { NavigationData, LocationPoint, RouteSegment };