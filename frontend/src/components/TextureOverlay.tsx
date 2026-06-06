import React from 'react';

/**
 * 纹理覆盖层组件
 * 设计意图：在页面背景叠加极细微的 SVG 噪点，
 * 模拟纸质印刷品的颗粒感，打破 AI 模板的"无菌"平滑质感。
 * 这是"去AI味"策略中"质感与杂质"部分的关键实现。
 */
const TextureOverlay: React.FC = () => (
  <div
    style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      width: '100vw',
      height: '100vh',
      pointerEvents: 'none',
      zIndex: 9999,
      mixBlendMode: 'overlay',
      opacity: 0.35,
      backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
      backgroundRepeat: 'repeat',
      backgroundSize: '256px 256px',
    }}
  />
);

export default TextureOverlay;
