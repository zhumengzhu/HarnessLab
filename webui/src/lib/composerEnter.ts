/** Whether Enter should submit the composer (false during IME composition). */
export function shouldSubmitComposerOnEnter(
  key: string,
  shiftKey: boolean,
  isComposing: boolean
): boolean {
  if (key !== "Enter" || shiftKey) return false;
  return !isComposing;
}
