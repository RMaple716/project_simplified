/**
 * 效用轨迹图组件（纯 Canvas 实现，无外部依赖）
 *
 * 功能：
 * 1. X轴为调度中心效用，Y轴为承包商效用
 * 2. 从协商事件中提取每轮效用值，散点连线
 * 3. 标注帕累托前沿（近似）
 * 4. 标注最终协议点
 */
import React, { useEffect, useRef, useMemo, useCallback, useState } from 'react';
import { Card, Typography } from 'antd';
import type { NegotiationEvent } from '../types/negotiation';

const { Text } = Typography;

// ===== Canvas 绘图常量 =====
const PADDING = { top: 40, right: 30, bottom: 50, left: 65 };
const POINT_RADIUS = 5;
const FINAL_POINT_RADIUS = 8;
const AXIS_COLOR = '#5a4e48';
const GRID_COLOR = '#e0d8ce';
const BG_COLOR = '#faf7f2';
const LINE_COLOR = '#4a7a8c';
const FRONTIER_COLOR = '#c45a4a';
const FINAL_COLOR = '#6a8f6a';
const FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

interface UtilityTrajectoryChartProps {
  events: NegotiationEvent[];
  title?: string;
  /** @deprecated 宽度固定为父容器100%，此参数已弃用 */
  width?: number | string;
  height?: number;
}

// ===== 工具函数 =====

/** 将数据坐标 (domain) 映射到 Canvas 像素坐标（动态范围） */
function mapToPixel(
  x: number,
  y: number,
  chartWidth: number,
  chartHeight: number,
  xMin: number = 0,
  xMax: number = 1,
  yMin: number = 0,
  yMax: number = 1
): { px: number; py: number } {
  const plotW = chartWidth - PADDING.left - PADDING.right;
  const plotH = chartHeight - PADDING.top - PADDING.bottom;
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  return {
    px: PADDING.left + ((x - xMin) / xRange) * plotW,
    py: PADDING.top + (1 - (y - yMin) / yRange) * plotH,
  };
}

/** 绘制圆点 */
function drawDot(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  fill: string,
  stroke: string = fill,
  strokeWidth: number = 1
) {
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = strokeWidth;
  ctx.stroke();
}

/** 绘制箭头 */
function drawArrowHead(
  ctx: CanvasRenderingContext2D,
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  size: number = 6
) {
  const angle = Math.atan2(toY - fromY, toX - fromX);
  ctx.beginPath();
  ctx.moveTo(toX, toY);
  ctx.lineTo(
    toX - size * Math.cos(angle - Math.PI / 6),
    toY - size * Math.sin(angle - Math.PI / 6)
  );
  ctx.lineTo(
    toX - size * Math.cos(angle + Math.PI / 6),
    toY - size * Math.sin(angle + Math.PI / 6)
  );
  ctx.closePath();
  ctx.fillStyle = AXIS_COLOR;
  ctx.fill();
}

const UtilityTrajectoryChart: React.FC<UtilityTrajectoryChartProps> = ({
  events,
  title = '效用轨迹图',
  height = 350,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  // hover 交互（P1 新增）
  const [tooltip, setTooltip] = useState<{
    visible: boolean;
    x: number;
    y: number;
    dispatcher: string;
    vehicle: string;
    label: string;
    isFinal: boolean;
  }>({ visible: false, x: 0, y: 0, dispatcher: '', vehicle: '', label: '', isFinal: false });

  // 提取效用数据
  const chartData = useMemo(() => {
    return events
      .map((event) => {
        const u = event.utility;
        if (u && u.dispatcher !== undefined && u.vehicle !== undefined) {
          return {
            dispatcher: u.dispatcher,
            vehicle: u.vehicle,
            label: `${event.eventType}${event.proposal?.action ? `(${event.proposal.action})` : ''}`,
            isFinal: event.eventType === 'FINALIZED',
          };
        }
        return null;
      })
      .filter((p): p is NonNullable<typeof p> => p !== null);
  }, [events]);

  // 计算近似帕累托前沿
  const paretoFrontier = useMemo(() => {
    if (chartData.length < 2) return [];
    const sorted = [...chartData].sort((a, b) => b.dispatcher - a.dispatcher);
    const frontier: { dispatcher: number; vehicle: number }[] = [];
    let maxVehicle = -Infinity;
    for (const p of sorted) {
      if (p.vehicle > maxVehicle) {
        frontier.push({ dispatcher: p.dispatcher, vehicle: p.vehicle });
        maxVehicle = p.vehicle;
      }
    }
    return frontier;
  }, [chartData]);

  // ===== 核心绘制函数 =====
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || chartData.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // 高 DPI 支持
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const cw = rect.width;
    const ch = height;
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
    ctx.scale(dpr, dpr);

    const plotW = cw - PADDING.left - PADDING.right;
    const plotH = ch - PADDING.top - PADDING.bottom;
    const plotLeft = PADDING.left;
    const plotTop = PADDING.top;
    const plotRight = cw - PADDING.right;
    const plotBottom = ch - PADDING.bottom;

    ctx.clearRect(0, 0, cw, ch);

    // ---- 动态坐标范围（P2 新增：根据数据实际范围自动调整） ----
    const allX = chartData.map(p => p.dispatcher);
    const allY = chartData.map(p => p.vehicle);
    const xMin = Math.min(...allX);
    const xMax = Math.max(...allX);
    const yMin = Math.min(...allY);
    const yMax = Math.max(...allY);
    // 加上 10% 的边距，避免点贴在坐标轴上
    const xPad = (xMax - xMin) * 0.1 || 0.05;
    const yPad = (yMax - yMin) * 0.1 || 0.05;
    const axisXMin = Math.max(0, Math.floor((xMin - xPad) * 20) / 20);
    const axisXMax = Math.min(1, Math.ceil((xMax + xPad) * 20) / 20);
    const axisYMin = Math.max(0, Math.floor((yMin - yPad) * 20) / 20);
    const axisYMax = Math.min(1, Math.ceil((yMax + yPad) * 20) / 20);

    // ---- 1. 背景 ----
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, cw, ch);

    // ---- 2. 网格线 ----
    ctx.strokeStyle = GRID_COLOR;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    for (let i = 0; i <= 5; i++) {
      const x = plotLeft + (plotW * i) / 5;
      const y = plotTop + (plotH * i) / 5;
      ctx.beginPath();
      ctx.moveTo(x, plotTop);
      ctx.lineTo(x, plotBottom);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(plotLeft, y);
      ctx.lineTo(plotRight, y);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // ---- 3. 坐标轴 ----
    ctx.strokeStyle = AXIS_COLOR;
    ctx.lineWidth = 1.5;

    ctx.beginPath();
    ctx.moveTo(plotLeft, plotBottom);
    ctx.lineTo(plotRight, plotBottom);
    ctx.stroke();
    drawArrowHead(ctx, plotRight + 5, plotBottom, plotRight, plotBottom);

    ctx.beginPath();
    ctx.moveTo(plotLeft, plotTop);
    ctx.lineTo(plotLeft, plotBottom);
    ctx.stroke();
    drawArrowHead(ctx, plotLeft, plotTop - 5, plotLeft, plotTop);

    // ---- 4. 动态轴刻度标签（P2 改进） ----
    ctx.fillStyle = AXIS_COLOR;
    ctx.font = `11px ${FONT_FAMILY}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (let i = 0; i <= 5; i++) {
      const val = (axisXMin + (axisXMax - axisXMin) * i / 5).toFixed(2);
      const x = plotLeft + (plotW * i) / 5;
      ctx.fillText(val, x, plotBottom + 6);
    }
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i <= 5; i++) {
      const val = (axisYMin + (axisYMax - axisYMin) * (1 - i / 5)).toFixed(2);
      const y = plotTop + (plotH * i) / 5;
      ctx.fillText(val, plotLeft - 8, y);
    }

    // ---- 5. 轴名称 ----
    ctx.fillStyle = '#333';
    ctx.font = `12px ${FONT_FAMILY}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('调度中心效用', (plotLeft + plotRight) / 2, ch - 12);
    ctx.save();
    ctx.translate(14, (plotTop + plotBottom) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillText('车辆效用', 0, 0);
    ctx.restore();

    // ---- 6. 标题 + 副标题 ----
    ctx.fillStyle = '#333';
    ctx.font = `bold 14px ${FONT_FAMILY}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(title, cw / 2, 8);
    ctx.fillStyle = AXIS_COLOR;
    ctx.font = `10px ${FONT_FAMILY}`;
    ctx.fillText('每个点=一次提案，连线展示调度中心与车辆利益变化', cw / 2, 8 + 18);

    // ---- 7. 近似帕累托前沿（虚线，仅数据点≥5时标注以避免误导） ----
    if (paretoFrontier.length >= 2 && chartData.length >= 5) {
      ctx.strokeStyle = FRONTIER_COLOR;
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      paretoFrontier.forEach((p, i) => {
        const { px, py } = mapToPixel(p.dispatcher, p.vehicle, cw, ch, axisXMin, axisXMax, axisYMin, axisYMax);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.stroke();
      ctx.setLineDash([]);

      const lastF = paretoFrontier[paretoFrontier.length - 1];
      const { px: lx, py: ly } = mapToPixel(lastF.dispatcher, lastF.vehicle, cw, ch, axisXMin, axisXMax, axisYMin, axisYMax);
      ctx.fillStyle = FRONTIER_COLOR;
      ctx.font = `11px ${FONT_FAMILY}`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText('近似帕累托前沿', lx + 6, ly - 2);
    }

    // ---- 8. 轨迹连线 + 散点 ----
    const points = chartData.map((p) => ({
      ...p,
      ...mapToPixel(p.dispatcher, p.vehicle, cw, ch, axisXMin, axisXMax, axisYMin, axisYMax),
    }));

    if (points.length >= 2) {
      ctx.strokeStyle = LINE_COLOR;
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      points.forEach((p, i) => {
        if (i === 0) ctx.moveTo(p.px, p.py);
        else ctx.lineTo(p.px, p.py);
      });
      ctx.stroke();
      ctx.globalAlpha = 1;

      for (let i = 1; i < points.length; i++) {
        const from = points[i - 1];
        const to = points[i];
        drawArrowHead(ctx, from.px, from.py, to.px, to.py, 5);
      }
    }

    points.forEach((p, i) => {
      const isFinal = i === points.length - 1;
      const radius = isFinal ? FINAL_POINT_RADIUS : POINT_RADIUS;
      const color = isFinal ? FINAL_COLOR : '#1890ff';
      drawDot(ctx, p.px, p.py, radius, color, '#fff', 2);
    });

    // ---- 8.5 趋势标注（P2 新增） ----
    if (points.length >= 2) {
      const first = points[0];
      const last = points[points.length - 1];
      const dispatcherDelta = last.dispatcher - first.dispatcher;
      const vehicleDelta = last.vehicle - first.vehicle;
      const trendLabel = `调度: ${dispatcherDelta > 0.01 ? '↑' : dispatcherDelta < -0.01 ? '↓' : '→'} ${Math.abs(dispatcherDelta).toFixed(3)}  |  车辆: ${vehicleDelta > 0.01 ? '↑' : vehicleDelta < -0.01 ? '↓' : '→'} ${Math.abs(vehicleDelta).toFixed(3)}`;
      ctx.fillStyle = AXIS_COLOR;
      ctx.font = `11px ${FONT_FAMILY}`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText(trendLabel, plotRight, plotTop + 14);
    }

    // ---- 9. 图例 ----
    ctx.font = `11px ${FONT_FAMILY}`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';

    drawDot(ctx, plotLeft + 20, plotTop + 20, 4, LINE_COLOR);
    ctx.fillStyle = '#333';
    ctx.fillText('协商轨迹', plotLeft + 30, plotTop + 20);

    drawDot(ctx, plotLeft + 20, plotTop + 40, 5, FINAL_COLOR, '#fff', 2);
    ctx.fillStyle = '#333';
    ctx.fillText('最终协议', plotLeft + 30, plotTop + 40);

    if (paretoFrontier.length >= 2 && chartData.length >= 5) {
      ctx.strokeStyle = FRONTIER_COLOR;
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(plotLeft + 20, plotTop + 62);
      ctx.lineTo(plotLeft + 60, plotTop + 62);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#333';
      ctx.fillText('近似帕累托前沿', plotLeft + 65, plotTop + 62);
    }
  }, [chartData, paretoFrontier, title, height]);

  // 绘制
  useEffect(() => {
    cancelAnimationFrame(animFrameRef.current);
    animFrameRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [draw]);

  // 响应窗口大小变化（带 debounce 防抖，P1 修复）
  useEffect(() => {
    let debounceTimer: ReturnType<typeof setTimeout>;
    const handleResize = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = requestAnimationFrame(draw);
      }, 200);
    };
    window.addEventListener('resize', handleResize);
    return () => {
      clearTimeout(debounceTimer);
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [draw]);

  // ===== 鼠标交互：悬停显示 tooltip（P1 新增） =====
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas || chartData.length === 0) {
        setTooltip((prev) => ({ ...prev, visible: false }));
        return;
      }
      const rect = canvas.getBoundingClientRect();
      const cw = rect.width;
      const ch = height;
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // 计算动态坐标范围（与 draw 中保持一致）
      const allX = chartData.map(p => p.dispatcher);
      const allY = chartData.map(p => p.vehicle);
      const xMin = Math.min(...allX);
      const xMax = Math.max(...allX);
      const yMin = Math.min(...allY);
      const yMax = Math.max(...allY);
      const xPad = (xMax - xMin) * 0.1 || 0.05;
      const yPad = (yMax - yMin) * 0.1 || 0.05;
      const axisXMin = Math.max(0, Math.floor((xMin - xPad) * 20) / 20);
      const axisXMax = Math.min(1, Math.ceil((xMax + xPad) * 20) / 20);
      const axisYMin = Math.max(0, Math.floor((yMin - yPad) * 20) / 20);
      const axisYMax = Math.min(1, Math.ceil((yMax + yPad) * 20) / 20);

      // 计算每个点的像素坐标
      const points = chartData.map((p) => ({
        ...p,
        ...mapToPixel(p.dispatcher, p.vehicle, cw, ch, axisXMin, axisXMax, axisYMin, axisYMax),
      }));

      // 找最近的点（距离 < 15px）
      const HIT_RADIUS = 15;
      let nearest: (typeof points)[0] | null = null;
      let minDist = HIT_RADIUS;
      for (const p of points) {
        const dx = mouseX - p.px;
        const dy = mouseY - p.py;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < minDist) {
          minDist = dist;
          nearest = p;
        }
      }

      if (nearest) {
        setTooltip({
          visible: true,
          x: e.clientX,
          y: e.clientY,
          dispatcher: nearest.dispatcher.toFixed(3),
          vehicle: nearest.vehicle.toFixed(3),
          label: nearest.label,
          isFinal: nearest.isFinal,
        });
      } else {
        setTooltip((prev) => ({ ...prev, visible: false }));
      }
    },
    [chartData, height]
  );

  const handleMouseLeave = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false }));
  }, []);

  if (chartData.length === 0) {
    return (
      <Card size="small" style={{ marginBottom: 16 }}>
        <Text type="secondary">无效用数据，无法生成轨迹图</Text>
      </Card>
    );
  }

  return (
    <Card size="small" style={{ marginBottom: 16, position: 'relative' }}>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height, cursor: 'pointer' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      />
      {/* 悬停 tooltip */}
      {tooltip.visible && (
        <div
          style={{
            position: 'fixed',
            left: tooltip.x + 12,
            top: tooltip.y - 10,
            background: 'var(--paper-light, #faf7f2)',
            border: '1px solid var(--border-faded, #e0d8ce)',
            padding: '6px 10px',
            fontSize: 12,
            pointerEvents: 'none',
            zIndex: 1000,
            boxShadow: '2px 2px 8px rgba(0,0,0,0.1)',
            lineHeight: 1.6,
          }}
        >
          <div><strong>{tooltip.label}</strong></div>
          <div>调度: {tooltip.dispatcher} | 车辆: {tooltip.vehicle}</div>
          {tooltip.isFinal && (
            <div style={{ color: 'var(--stamp-green, #6a8f6a)' }}>最终协议</div>
          )}
        </div>
      )}
    </Card>
  );
};

export default UtilityTrajectoryChart;
