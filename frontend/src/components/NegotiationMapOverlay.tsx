/**
 * 协商路线预览图层组件
 *
 * 功能：
 * 1. 在已有地图上叠加临时协商路线图层
 * 2. 根据 NegotiationEvent.routePreview 动态更新
 * 3. 支持多车辆提案路线的彩色虚线展示
 * 4. 接受/最终确定时转为实线
 *
 * 使用方式：
 *   <NegotiationMapOverlay
 *     map={mapInstance}          // AMap 实例
 *     events={negotiationEvents} // 当前可见的协商事件
 *     visible={true}
 *   />
 */
import React, { useEffect, useRef, useCallback } from 'react';
import type { NegotiationEvent } from '../types/negotiation';

interface NegotiationMapOverlayProps {
  /** 高德地图实例 */
  map: any;
  /** 高德地图构造函数（通过 props 注入，避免全局变量依赖，P2 修复） */
  AMap?: any;
  /** 协商事件列表（将根据事件的 routePreview 绘制） */
  events: NegotiationEvent[];
  /** 是否可见 */
  visible?: boolean;
  /** 当前回放索引（若为回放模式），-1 表示非回放 */
  replayIndex?: number;
}

/** 管理一条提案路线的状态 */
interface RouteLineState {
  vehicleId: string;
  polyline: any;      // AMap.Polyline
  label: any;         // AMap.Text / AMap.Marker
  color: string;
  accepted: boolean;
}

const DEFAULT_COLORS = ['#c45a4a', '#4a7a8c', '#6a8f6a', '#8a7a70', '#2c2420'];

const NegotiationMapOverlay: React.FC<NegotiationMapOverlayProps> = ({
  map,
  AMap: AMapProp,
  events,
  visible = true,
  replayIndex = -1,
}) => {
  // 优先使用 props 注入的 AMap，否则回退到全局对象
  const getAMap = useCallback(() => AMapProp || (window as any).AMap, [AMapProp]);
  const layerGroupRef = useRef<any>(null);
  const routeLinesRef = useRef<Map<string, RouteLineState>>(new Map());
  const animFrameRef = useRef<number>(0);

  // 获取当前可见的事件列表
  const getVisibleEvents = useCallback(() => {
    if (replayIndex >= 0 && replayIndex < events.length) {
      return events.slice(0, replayIndex + 1);
    }
    return events;
  }, [events, replayIndex]);

  // 清除所有路线
  const clearAllRoutes = useCallback(() => {
    if (layerGroupRef.current) {
      layerGroupRef.current.clearLayers();
    }
    routeLinesRef.current.forEach((line) => {
      if (line.polyline) line.polyline = null;
      if (line.label) line.label = null;
    });
    routeLinesRef.current.clear();
  }, []);

  // 创建或更新路线
  const updateRoutes = useCallback(() => {
    if (!map || !visible) {
      if (layerGroupRef.current) {
        layerGroupRef.current.hide();
      }
      return;
    }

    // 延迟初始化图层组
    const AMap = getAMap();
    if (!layerGroupRef.current && AMap) {
      layerGroupRef.current = new AMap.LayerGroup();
      layerGroupRef.current.setMap(map);
    }

    if (layerGroupRef.current) {
      layerGroupRef.current.show();
    }

    // 使用 requestAnimationFrame 批量更新
    cancelAnimationFrame(animFrameRef.current);
    animFrameRef.current = requestAnimationFrame(() => {
      const AMap = getAMap();
      if (!AMap) return;

      const visibleEvents = getVisibleEvents();
      const activeVehicleIds = new Set<string>();
      const newRoutes = new Map<string, RouteLineState>();

      // 遍历事件，收集每个车辆的最新路线
      visibleEvents.forEach((event) => {
        const rp = event.routePreview;
        if (!rp || !rp.vehicleId || !rp.coordinates || rp.coordinates.length < 2) return;

        const vid = rp.vehicleId;
        activeVehicleIds.add(vid);

        const isAccepted =
          event.eventType === 'ACCEPT' || event.eventType === 'FINALIZED';
        const colorIndex = Array.from(activeVehicleIds).indexOf(vid) % DEFAULT_COLORS.length;
        const color = rp.color || DEFAULT_COLORS[colorIndex];

        // 检查是否需要更新（仅当状态变化时重建）
        const existing = routeLinesRef.current.get(vid);
        if (
          existing &&
          existing.accepted === isAccepted &&
          existing.color === color
        ) {
          // 保留已有路线
          newRoutes.set(vid, existing);
          return;
        }

        // 构建坐标数组
        const path = rp.coordinates.map(
          (coord: [number, number]) => new AMap.LngLat(coord[0], coord[1])
        );

        // 创建 Polyline（P2 新增：路径生长动画）
        const polyline = new AMap.Polyline({
          path,
          strokeColor: color,
          strokeWeight: 4,
          strokeOpacity: isAccepted ? 0.9 : 0.6,
          strokeStyle: isAccepted ? 'solid' : 'dashed',
          strokeDasharray: isAccepted ? undefined : '10, 10',
          lineJoin: 'round',
          lineCap: 'round',
          zIndex: isAccepted ? 120 : 100,
          showDir: true,
        });

        // 如果是从 dashed 变为 solid（刚被接受），做一次闪烁动画
        if (isAccepted && existing && !existing.accepted) {
          let flashCount = 0;
          const flashTimer = setInterval(() => {
            flashCount++;
            if (flashCount > 6) {
              clearInterval(flashTimer);
              return;
            }
            // 交替 0.3/0.9 透明度产生闪烁效果
            polyline.setOptions({
              strokeOpacity: flashCount % 2 === 0 ? 0.9 : 0.3,
            });
          }, 200);
        }

        // 创建标签（显示价格等）
        let label = null;
        if (event.proposal?.price !== undefined) {
          const lastCoord = rp.coordinates[rp.coordinates.length - 1];
          label = new AMap.Text({
            text: `¥${event.proposal.price}`,
            anchor: 'bottom-center',
            offset: new AMap.Pixel(0, -8),
            position: new AMap.LngLat(lastCoord[0], lastCoord[1]),
            style: {
              'font-size': '12px',
              'font-weight': 'bold',
              color: '#fff',
              background: color,
              'border-radius': '4px',
              padding: '2px 6px',
              'white-space': 'nowrap',
            },
          });
        }

        // 移除旧路线
        if (existing) {
          if (existing.polyline) layerGroupRef.current?.removeOverlay(existing.polyline);
          if (existing.label) layerGroupRef.current?.removeOverlay(existing.label);
        }

        // 添加到图层
        if (polyline) layerGroupRef.current?.addOverlay(polyline);
        if (label) layerGroupRef.current?.addOverlay(label);

        newRoutes.set(vid, {
          vehicleId: vid,
          polyline,
          label,
          color,
          accepted: isAccepted,
        });
      });

      // 移除不再活跃的车辆路线
      routeLinesRef.current.forEach((line, vid) => {
        if (!activeVehicleIds.has(vid)) {
          if (line.polyline) layerGroupRef.current?.removeOverlay(line.polyline);
          if (line.label) layerGroupRef.current?.removeOverlay(line.label);
        }
      });

      routeLinesRef.current = newRoutes;
    });
  }, [map, events, visible, getVisibleEvents]);

  // 当事件变化时重新绘制
  useEffect(() => {
    updateRoutes();
    return () => {
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [updateRoutes]);

  // 清理
  useEffect(() => {
    return () => {
      cancelAnimationFrame(animFrameRef.current);
      clearAllRoutes();
      if (layerGroupRef.current) {
        layerGroupRef.current.setMap(null);
        layerGroupRef.current = null;
      }
    };
  }, [clearAllRoutes]);

  return null; // 无 DOM 渲染
};

export default NegotiationMapOverlay;
