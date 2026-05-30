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
  /** Changes when switching sessions — resets stick-to-bottom. */
  resetKey?: string | null;
  onComposerChromeChange?: (collapsed: boolean) => void;
};

type UseChatScrollResult = {
  scrollRef: RefObject<HTMLDivElement>;
  bottomRef: RefObject<HTMLDivElement>;
  newMessagesBelow: boolean;
  scrollToLatest: () => void;
  onScrollAreaScroll: () => void;
};

export function useChatScroll(args: UseChatScrollArgs): UseChatScrollResult {
  const { scrollSignal, resetKey, onComposerChromeChange } = args;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const prevScrollSignalRef = useRef(scrollSignal);
  const [newMessagesBelow, setNewMessagesBelow] = useState(false);

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

  const syncStickState = useCallback(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }
    const near = isNearBottom(element);
    stickToBottomRef.current = near;
    if (near) {
      setNewMessagesBelow(false);
    }
  }, []);

  const scrollToLatest = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    scrollElementToBottom(element);
    stickToBottomRef.current = true;
    setNewMessagesBelow(false);
    onComposerChromeChange?.(false);
    lastScrollTopRef.current = element.scrollTop;
  }, [onComposerChromeChange]);

  const onScrollAreaScroll = useCallback(() => {
    const element = scrollRef.current;
    if (element) {
      updateComposerChrome(element);
    }
    syncStickState();
  }, [syncStickState, updateComposerChrome]);

  useEffect(() => {
    stickToBottomRef.current = true;
    setNewMessagesBelow(false);
    lastScrollTopRef.current = 0;
    onComposerChromeChange?.(false);
  }, [resetKey, onComposerChromeChange]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const signalChanged = prevScrollSignalRef.current !== scrollSignal;
    prevScrollSignalRef.current = scrollSignal;

    if (stickToBottomRef.current) {
      scrollElementToBottom(element);
      setNewMessagesBelow(false);
      return;
    }

    if (signalChanged) {
      setNewMessagesBelow(true);
    }
  }, [scrollSignal]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (stickToBottomRef.current) {
        scrollElementToBottom(element);
        setNewMessagesBelow(false);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [scrollSignal]);

  return {
    scrollRef: scrollRef as RefObject<HTMLDivElement>,
    bottomRef: bottomRef as RefObject<HTMLDivElement>,
    newMessagesBelow,
    scrollToLatest,
    onScrollAreaScroll,
  };
}
