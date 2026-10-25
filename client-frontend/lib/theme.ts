export type Theme = "light" | "dark";

const THEME_KEY_PREFIX = "fintrack.theme";

function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "dark";
}

export function themeStorageKey(userId: number): string {
  return `${THEME_KEY_PREFIX}.${userId}`;
}

export function readThemePreference(userId: number): Theme {
  if (typeof window === "undefined") return "light";

  const key = themeStorageKey(userId);
  const value = localStorage.getItem(key);

  if (isTheme(value)) return value;
  if (value !== null) localStorage.removeItem(key);
  return "light";
}

export function saveThemePreference(userId: number, theme: Theme): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(themeStorageKey(userId), theme);
}

export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;

  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.style.colorScheme = theme;
}
