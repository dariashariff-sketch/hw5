import { useEffect, useState } from "react";

type Theme = "day" | "night";

/** Corner button that flips the desk into "night shift" (dark mode) and remembers it. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem("cc-theme") as Theme) ?? "day");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("cc-theme", theme);
  }, [theme]);

  const night = theme === "night";
  return (
    <button
      className="theme-toggle"
      onClick={() => setTheme(night ? "day" : "night")}
      aria-pressed={night}
      title={night ? "Back to the day shift" : "Switch to the night shift"}
    >
      <span className="orb" aria-hidden />
      {night ? "Day shift" : "Night shift"}
    </button>
  );
}
