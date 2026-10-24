import { useCallback, useMemo, useState, type KeyboardEvent, type PointerEvent, type RefObject } from 'react';

/**
 * Pointer and keyboard inspection of one night in a chart of `count` equal slots.
 * `originRef` is the element whose left edge is x = 0 (defaults to the event target),
 * which lets several stacked charts share one hover position.
 */
export function useSlotHover(count: number, width: number, padLeft: number, padRight: number, originRef?: RefObject<Element | null>) {
  const [active, setActive] = useState<number | null>(null);
  const slot = (width - padLeft - padRight) / Math.max(count, 1);

  const fromPointer = useCallback(
    (e: PointerEvent<Element>) => {
      const rect = (originRef?.current ?? e.currentTarget).getBoundingClientRect();
      const i = Math.floor((e.clientX - rect.left - padLeft) / slot);
      setActive(i < 0 || i >= count ? null : i);
    },
    [originRef, padLeft, slot, count],
  );

  const onKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const last = count - 1;
      if (e.key === 'ArrowRight') setActive((a) => (a === null ? last : Math.min(a + 1, last)));
      else if (e.key === 'ArrowLeft') setActive((a) => (a === null ? last : Math.max(a - 1, 0)));
      else if (e.key === 'Home') setActive(0);
      else if (e.key === 'End') setActive(last);
      else if (e.key === 'Escape') setActive(null);
      else return;
      e.preventDefault();
    },
    [count],
  );

  const handlers = useMemo(
    () => ({
      onPointerMove: fromPointer,
      onPointerDown: fromPointer,
      onPointerLeave: () => setActive(null),
      onKeyDown,
      onBlur: () => setActive(null),
    }),
    [fromPointer, onKeyDown],
  );

  return { active, slot, handlers };
}
