import { useEffect, useRef, useState } from 'react';

/** Tracks an element's rendered width so SVG charts keep a constant pixel text size. */
export function useElementWidth<T extends HTMLElement>(fallback: number, min = 200) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(Math.max(Math.round(el.getBoundingClientRect().width), min));
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(Math.round(entry.contentRect.width), min));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [min]);

  return [ref, width] as const;
}
