export type AgentPersona = {
  name: string;
  avatar: string;
  tagline: string;
  hint: string;
};

export const DEFAULT_AGENT_PERSONA: AgentPersona = {
  name: "HarnessLab",
  avatar: "HL",
  tagline: "准备好聊天",
  hint: "在下方输入消息 · 输入 / 查看命令",
};

export const QUICK_PROMPTS = [
  { label: "你能做什么？", text: "你能做什么？简要介绍你的能力和可用工具。" },
  { label: "查看 Skills", text: "/skill list" },
  { label: "压缩上下文", text: "/compact" },
  { label: "总结本会话", text: "请简要总结我们目前这个会话在做什么。" },
] as const;
