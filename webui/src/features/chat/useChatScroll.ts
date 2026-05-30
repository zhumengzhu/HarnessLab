import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export const CHAT_NEAR_BOTTOM_PX = 80;
export const COMPOSER_COLLAPSE_SCROLL_PX = 48;

export function isNearBottom(element: HTMLElement, threshold = CHAT_NEAR_BOTTOM_PX): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}

export function shouldExpandComposerChrome(
  scrollTop: number,
  previousScrollTop: number,
  nearBottom: boolean
): boolean {
  if (nearBottom || scrollTop <= 8) {
    return true;
  }
  return scrollTop < previousScrollTop - 2;
}

export function shouldCollapseComposerChrome(
  scrollTop: number,
  previousScrollTop: number,
  nearBottom: boolean
): boolean {
  if (nearBottom || scrollTop <= COMPOSER_COLLAPSE_SCROLL_PX) {
    return false;
  }
  return scrollTop > previousScrollTop + 2;
}

export function scrollElementToBottom(element: HTMLElement): void {
  element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
}

type UseChatScrollArgs = {
  /** Changes when message list or live turn content grows. */
  scrollSignal: string;
  onComposerChromeChange?: (collapsed: boolean) => void;
};

type UseChatScrollResult = {
  scrollRef: RefObject<HTMLDivElement | null>;
  bottomRef: RefObject<HTMLDivElement | null>;
  showJumpToLatest: boolean;
  scrollToLatest: () => void;
  onScrollAreaScroll: () => void;
};

export function useChatScroll(args: UseChatScrollArgs): UseChatScrollResult {
  const { scrollSignal, onComposerChromeChange } = args;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const updateComposerChrome = useCallback(
    (element: HTMLElement) => {
      if (!onComposerChromeChange) {
        return;
      }
      const scrollTop = element.scrollTop;
      const nearBottom = isNearBottom(element);
      const previous = lastScrollTopRef.current;
      if (shouldExpandComposerChrome(scrollTop, previous, nearBottom)) {
        onComposerChromeChange(false);
      } else if (shouldCollapseComposerChrome(scrollTop, previous, nearBottom)) {
        onComposerChromeChange(true);
      }
      lastScrollTopRef.current = scrollTop;
    },
    [onComposerChromeChange]
  );

  const syncJumpVisibility = useCallback(() => {
    const element = scrollRef.current;
    if (!element) {
      setShowJumpToLatest(false);
      return;
    }
    const near = isNearBottom(element);
    stickToBottomRef.current = near;
    setShowJumpToLatest(!near && element.scrollHeight > element.clientHeight);
  }, []);

  const scrollToLatest = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    scrollElementToBottom(element);
    stickToBottomRef.current = true;
    setShowJumpToLatest(false);
    onComposerChromeChange?.(false);
    lastScrollTopRef.current = element.scrollTop;
  }, [onComposerChromeChange]);

  const onScrollAreaScroll = useCallback(() => {
    const element = scrollRef.current;
    if (element) {
      updateComposerChrome(element);
    }
    syncJumpVisibility();
  }, [syncJumpVisibility, updateComposerChrome]);

  useEffect(() => {
    onComposerChromeChange?.(false);
    lastScrollTopRef.current = 0;
  }, [scrollSignal, onComposerChromeChange]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    if (stickToBottomRef.current) {
      scrollElementToBottom(element);
      setShowJumpToLatest(false);
      return;
    }
    syncJumpVisibility();
  }, [scrollSignal, syncJumpVisibility]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (stickToBottomRef.current) {
        scrollElementToBottom(element);
        setShowJumpToLatest(false);
        return;
      }
      syncJumpVisibility();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [scrollSignal, syncJumpVisibility]);

  return {
    scrollRef,
    bottomRef,
    showJumpToLatest,
    scrollToLatest,
    onScrollAreaScroll,
  };
}
