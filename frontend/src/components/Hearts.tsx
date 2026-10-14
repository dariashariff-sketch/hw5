import { useEffect, useState } from "react";

const COLORS = ["#f4a7b6", "#e57991", "#9fbbd3", "#ffd98a", "#d7c6ec", "#b9dfc7"];

interface Heart { id: number; left: number; delay: number; size: number; color: string; drift: number }

/** A little burst of floating hearts whenever `trigger` changes. */
export default function Hearts({ trigger }: { trigger: number }) {
  const [hearts, setHearts] = useState<Heart[]>([]);
  useEffect(() => {
    if (!trigger) return;
    const batch = Array.from({ length: 26 }, (_, i) => ({
      id: trigger * 100 + i,
      left: 10 + Math.random() * 80,
      delay: Math.random() * 0.5,
      size: 14 + Math.random() * 18,
      color: COLORS[i % COLORS.length],
      drift: (Math.random() - 0.5) * 120,
    }));
    setHearts(batch);
    const id = setTimeout(() => setHearts([]), 3200);
    return () => clearTimeout(id);
  }, [trigger]);

  return (
    <div className="hearts" aria-hidden>
      {hearts.map((h) => (
        <span
          key={h.id}
          style={{ left: `${h.left}%`, animationDelay: `${h.delay}s`, fontSize: h.size, color: h.color, "--drift": `${h.drift}px` } as React.CSSProperties}
        >
          &#9829;
        </span>
      ))}
    </div>
  );
}
