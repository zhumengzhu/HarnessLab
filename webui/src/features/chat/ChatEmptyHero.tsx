import type { AgentPersona } from "../../lib/agentPersona";
import { useI18n } from "../../lib/i18n";

type ChatEmptyHeroProps = {
  persona: AgentPersona;
  onPickPrompt: (text: string) => void;
};

export function ChatEmptyHero({ persona, onPickPrompt }: ChatEmptyHeroProps) {
  const { t } = useI18n();
  const quickPrompts = [
    {
      label: t("chat.quickWhatCanYouDo"),
      text: t("chat.quickWhatCanYouDoText"),
    },
    { label: t("chat.quickSkills"), text: "/skill list" },
    { label: t("chat.quickCompact"), text: "/compact" },
    {
      label: t("chat.quickSummarize"),
      text: t("chat.quickSummarizeText"),
    },
  ];

  return (
    <div className="chat-empty-hero">
      <div className="chat-empty-avatar" aria-hidden>
        {persona.avatar}
      </div>
      <h2 className="chat-empty-name">{persona.name}</h2>
      <p className="chat-empty-tagline">
        <span className="chat-empty-diamond" aria-hidden>
          ◇
        </span>
        {t("chat.readyTagline")}
      </p>
      <p className="chat-empty-hint">{t("chat.readyHint")}</p>
      <div className="chat-empty-chips">
        {quickPrompts.map((item) => (
          <button
            key={item.label}
            type="button"
            className="chat-empty-chip"
            onClick={() => onPickPrompt(item.text)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}
