import { createContext, useContext } from "react";
import type { ActivityDisplayMode, ChatTextSize } from "./chatDisplay";

export type ChatDisplayPreferences = {
  activityDisplay: ActivityDisplayMode;
  setActivityDisplay: (mode: ActivityDisplayMode) => void;
  chatTextSize: ChatTextSize;
  setChatTextSize: (size: ChatTextSize) => void;
  showThinking: boolean;
  setShowThinking: (value: boolean) => void;
  showTools: boolean;
  setShowTools: (value: boolean) => void;
};

const ChatDisplayContext = createContext<ChatDisplayPreferences | null>(null);

export function ChatDisplayProvider({
  value,
  children,
}: {
  value: ChatDisplayPreferences;
  children: React.ReactNode;
}) {
  return <ChatDisplayContext.Provider value={value}>{children}</ChatDisplayContext.Provider>;
}

export function useChatDisplay(): ChatDisplayPreferences {
  const value = useContext(ChatDisplayContext);
  if (!value) {
    throw new Error("useChatDisplay must be used within ChatDisplayProvider");
  }
  return value;
}
