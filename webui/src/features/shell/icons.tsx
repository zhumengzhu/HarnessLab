import type { ReactNode } from "react";

type IconProps = { size?: number; className?: string };

function base(size: number, className: string | undefined, children: ReactNode) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {children}
    </svg>
  );
}

export function IconMessage({ size = 16, className }: IconProps) {
  return base(size, className, <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />);
}

export function IconFileText({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </>
  ));
}

export function IconSparkles({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="m12 3 1.2 3.6L17 8l-3.8 1.4L12 13l-1.2-3.6L7 8l3.8-1.4z" />
      <path d="M19 14l.6 1.8L21 16l-1.4.2-.6 1.8-.6-1.8L17 16l1.4-.2z" />
    </>
  ));
}

export function IconSettings({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </>
  ));
}

export function IconSearch({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </>
  ));
}

export function IconSun({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </>
  ));
}

export function IconMoon({ size = 16, className }: IconProps) {
  return base(size, className, <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 1 0 9.8 9.8z" />);
}

export function IconMonitor({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </>
  ));
}

export function IconBrain({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="M9.5 4A2.5 2.5 0 0 1 12 6.5v11a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.04-2.04V8a4 4 0 0 1 4-4z" />
      <path d="M14.5 4A2.5 2.5 0 0 0 12 6.5v11a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.04-2.04V8a4 4 0 0 0-4-4z" />
    </>
  ));
}

export function IconWrench({ size = 16, className }: IconProps) {
  return base(size, className, <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />);
}

export function IconFocus({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3" />
    </>
  ));
}

export function IconHistory({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 3v6h6M12 7v5l3 2" />
    </>
  ));
}

export function IconRefresh({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
      <path d="M16 21h5v-5" />
    </>
  ));
}

export function IconSend({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="m22 2-7 20-4-9-9-4z" />
      <path d="M22 2 11 13" />
    </>
  ));
}

export function IconStop({ size = 16, className }: IconProps) {
  return base(size, className, <rect x="6" y="6" width="12" height="12" rx="1" />);
}

export function IconGear({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </>
  ));
}

export function IconChevron({ size = 16, className, open }: IconProps & { open?: boolean }) {
  return base(size, className, open ? <path d="m6 9 6 6 6-6" /> : <path d="m9 18 6-6-6-6" />);
}

export function IconPlus({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <path d="M12 5v14M5 12h14" />
    </>
  ));
}

export function IconPanelLeftClose({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </>
  ));
}

export function IconPanelLeftOpen({ size = 16, className }: IconProps) {
  return base(size, className, (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
      <path d="M14 9l-3 3-3-3" />
    </>
  ));
}
