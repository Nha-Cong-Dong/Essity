// C4C (review #280): the graph fits itself to its box until the reader takes the view: a pan, a
// wheel turn, a two-finger pinch or the +/- buttons. After that a resize of the box (the
// ResizeObserver) must not fit over what they chose. The lock reads the input events, not
// cytoscape's "zoom", because fit() itself zooms.

export type FitLock = {
  readonly touched: boolean;
  /** The reader has taken the view (also called by the zoom buttons and by dragpan). */
  lock: () => void;
  /** "Đặt lại": the next resize may fit again. */
  reset: () => void;
  /** Listens for wheel and pinch on the frame; returns the way to stop listening. */
  attach: (el: HTMLElement | null) => () => void;
};

export function createFitLock(): FitLock {
  let touched = false;
  const lock = () => {
    touched = true;
  };
  const pinch = (ev: TouchEvent) => {
    if (ev.touches.length >= 2) lock();
  };
  return {
    get touched() {
      return touched;
    },
    lock,
    reset: () => {
      touched = false;
    },
    attach: (el) => {
      el?.addEventListener("wheel", lock, { passive: true });
      el?.addEventListener("touchstart", pinch, { passive: true });
      return () => {
        el?.removeEventListener("wheel", lock);
        el?.removeEventListener("touchstart", pinch);
      };
    },
  };
}
