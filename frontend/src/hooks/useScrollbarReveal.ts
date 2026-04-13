import { useEffect, type RefObject } from "react";

/**
 * 滚动时在元素上临时加上 revealClass，超时后移除，配合 `.scrollbarAutoHide` 实现滚动条自适应隐藏。
 */
export function useScrollbarReveal(
  ref: RefObject<HTMLElement | null>,
  revealClass: string,
  options?: { hideAfterMs?: number; enabled?: boolean },
) {
  const hideAfterMs = options?.hideAfterMs ?? 1400;
  const enabled = options?.enabled ?? true;

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;

    let t: ReturnType<typeof setTimeout> | undefined;

    const reveal = () => {
      el.classList.add(revealClass);
      if (t !== undefined) clearTimeout(t);
      t = setTimeout(() => {
        el.classList.remove(revealClass);
        t = undefined;
      }, hideAfterMs);
    };

    el.addEventListener("scroll", reveal, { passive: true });
    return () => {
      if (t !== undefined) clearTimeout(t);
      el.removeEventListener("scroll", reveal);
      el.classList.remove(revealClass);
    };
  }, [ref, revealClass, hideAfterMs, enabled]);
}
