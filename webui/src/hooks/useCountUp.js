import { useEffect, useRef, useState } from 'react';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * 数字滚动：用于总览指标。整数展示，动画曲线与全局 easing 保持一致。
 */
export function useCountUp(target, { duration = 900 } = {}) {
  const numeric = Number(target);
  const value = Number.isFinite(numeric) ? numeric : 0;
  const [display, setDisplay] = useState(value);
  const shownRef = useRef(value);

  useEffect(() => {
    if (prefersReducedMotion()) {
      shownRef.current = value;
      setDisplay(value);
      return undefined;
    }

    const from = shownRef.current;
    if (from === value) return undefined;

    let frame = 0;
    const start = performance.now();

    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = Math.round(from + (value - from) * eased);
      shownRef.current = next;
      setDisplay(next);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  return display;
}
