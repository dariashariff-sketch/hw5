import type { Role } from "../api";

/** Little hand-drawn SVG characters, one per teammate, drawn inside their colored circle.
 *  Boss (she): blazer, pink bow, gold earrings and a tiny crown. Inventory: cap and a taped cardboard box.
 *  Accounting (she): green visor over a bun, round glasses, pencil behind the ear.
 *  Facilities: hard hat and overalls. Customer Service: headset with a mic. */

const INK = "#4a3640";

function Face({ skin, lashes = false, cx = 32, cy = 31 }: { skin: string; lashes?: boolean; cx?: number; cy?: number }) {
  return (
    <>
      <rect x={cx - 4} y={cy + 12} width="8" height="8" fill={skin} />
      <circle cx={cx} cy={cy} r="16" fill={skin} />
      <ellipse cx={cx - 9.5} cy={cy + 6} rx="3.2" ry="1.9" fill="#f59fb0" opacity=".75" />
      <ellipse cx={cx + 9.5} cy={cy + 6} rx="3.2" ry="1.9" fill="#f59fb0" opacity=".75" />
      <circle cx={cx - 6} cy={cy + 1} r="2.1" fill={INK} />
      <circle cx={cx + 6} cy={cy + 1} r="2.1" fill={INK} />
      <path d={`M${cx - 3} ${cy + 7} Q${cx} ${cy + 10} ${cx + 3} ${cy + 7}`} stroke={INK} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      {lashes && (
        <path d={`M${cx - 8} ${cy} L${cx - 10} ${cy - 1.8} M${cx + 8} ${cy} L${cx + 10} ${cy - 1.8}`} stroke={INK} strokeWidth="1.4" strokeLinecap="round" />
      )}
    </>
  );
}

const body = (fill: string) => <path d="M10 66 Q13 49 32 48 Q51 49 54 66 Z" fill={fill} />;

function Boss() {
  return (
    <>
      <path d="M12.5 50 L13.5 30 Q13.5 12 32 12 Q50.5 12 50.5 30 L51.5 50 Q46 48 46.5 32 Q41 23 32 23 Q23 23 17.5 32 Q18 48 12.5 50 Z" fill="#4a2e26" />
      {body("#4a4e69")}
      <path d="M24 49 L32 60 L28 49 Z M40 49 L32 60 L36 49 Z" fill="#5d6286" />
      <path d="M32 53 L26.5 50.5 L26.5 55.5 Z M32 53 L37.5 50.5 L37.5 55.5 Z" fill="#e5566f" />
      <circle cx="32" cy="53" r="1.6" fill="#c9425b" />
      <Face skin="#f1c9a5" lashes />
      <circle cx="16.3" cy="36" r="1.4" fill="#ffd66b" />
      <circle cx="47.7" cy="36" r="1.4" fill="#ffd66b" />
      <path d="M16 31 Q16.5 15 32 15 Q47.5 15 48 31 Q45 22 37 20.5 Q29 25 16 31 Z" fill="#4a2e26" />
      <path d="M22 15 L23.5 6.5 L28.5 11 L32 4 L35.5 11 L40.5 6.5 L42 15 Z" fill="#ffd66b" stroke="#d99a2b" strokeWidth="1" strokeLinejoin="round" />
      <circle cx="32" cy="11.5" r="1.4" fill="#e5566f" />
    </>
  );
}

function Inventory() {
  return (
    <>
      {body("#5d84a6")}
      <Face skin="#e2b48c" />
      <path d="M15.5 27 Q16 13 32 13 Q48 13 48.5 27 Z" fill="#4f7699" />
      <path d="M40 25.5 Q52 24 57 28 Q49 30 40 28.5 Z" fill="#3e6385" />
      <circle cx="32" cy="13.5" r="1.6" fill="#3e6385" />
      <rect x="17" y="47" width="30" height="19" rx="2.5" fill="#d9a46a" stroke="#b9824a" strokeWidth="1" />
      <rect x="29.5" y="47" width="5" height="19" fill="#f2d2a2" />
      <path d="M17 52 L47 52" stroke="#b9824a" strokeWidth="1" />
    </>
  );
}

function Accounting() {
  return (
    <>
      <path d="M14.5 44 L15 30 Q15 16 32 16 Q49 16 49 30 L49.5 44 Q46 42 46 31 Q40 24 32 24 Q24 24 18 31 Q18 42 14.5 44 Z" fill="#a0522d" />
      <circle cx="32" cy="11" r="6.5" fill="#a0522d" />
      {body("#f2c35f")}
      <path d="M26 49 L32 54 L38 49" stroke="#fff" strokeWidth="2" fill="none" strokeLinejoin="round" />
      <Face skin="#ffdcc2" lashes />
      <path d="M16 30 Q16.5 17 32 17 Q47.5 17 48 30 Q42 23 32 24 Q22 23 16 30 Z" fill="#a0522d" />
      <path d="M14 23 Q32 13 50 23 L50 26.5 Q32 17 14 26.5 Z" fill="#4fae7a" />
      <path d="M13 26.5 Q32 19 51 26.5 Q46 31.5 32 29 Q18 31.5 13 26.5 Z" fill="#86d3a6" opacity=".9" />
      <circle cx="26" cy="32" r="5" fill="#ffffff" fillOpacity=".35" stroke={INK} strokeWidth="1.6" />
      <circle cx="38" cy="32" r="5" fill="#ffffff" fillOpacity=".35" stroke={INK} strokeWidth="1.6" />
      <path d="M31 31.5 Q32 30.5 33 31.5" stroke={INK} strokeWidth="1.6" fill="none" />
      <g transform="rotate(-35 48 30)">
        <rect x="45" y="21" width="4" height="15" rx="1" fill="#ffd66b" stroke="#d99a2b" strokeWidth=".8" />
        <rect x="45" y="19" width="4" height="3" rx="1" fill="#f4a7b6" />
        <path d="M45 36 L47 40 L49 36 Z" fill="#f2d2a2" />
      </g>
    </>
  );
}

function Facilities() {
  return (
    <>
      {body("#6fae88")}
      <rect x="23" y="50" width="4" height="16" fill="#4d8a64" />
      <rect x="37" y="50" width="4" height="16" fill="#4d8a64" />
      <rect x="25" y="56" width="14" height="10" rx="2" fill="#5f9c78" />
      <Face skin="#c98f66" />
      <path d="M15 27 Q15 11 32 11 Q49 11 49 27 Z" fill="#ffd166" />
      <rect x="29.5" y="11" width="5" height="16" rx="2" fill="#f4b942" />
      <path d="M10 27 L54 27 Q54 31 50 31 L14 31 Q10 31 10 27 Z" fill="#f4b942" />
    </>
  );
}

function CustomerService() {
  return (
    <>
      {body("#b9a3dc")}
      <path d="M29 55 C29 53 31.5 52.5 32 54.5 C32.5 52.5 35 53 35 55 C35 57 32 58.5 32 58.5 C32 58.5 29 57 29 55 Z" fill="#f4a7b6" />
      <path d="M13.5 46 L14 30 Q14 15 32 15 Q50 15 50 30 L50.5 46 Q46 42 46.5 30 Q42 22 32 22 Q22 22 17.5 30 Q18 42 13.5 46 Z" fill="#8a5a44" />
      <Face skin="#ffe3d1" />
      <path d="M17.5 30 Q19 21 32 21 Q45 21 46.5 30 Q40 25 32 25 Q24 25 17.5 30 Z" fill="#8a5a44" />
      <path d="M14 30 Q14 10 32 10 Q50 10 50 30" stroke="#6b5694" strokeWidth="3" fill="none" strokeLinecap="round" />
      <rect x="10" y="26" width="7" height="11" rx="3.5" fill="#7c63a3" />
      <rect x="47" y="26" width="7" height="11" rx="3.5" fill="#7c63a3" />
      <path d="M14 36 Q15 44 25 43.5" stroke="#7c63a3" strokeWidth="2" fill="none" strokeLinecap="round" />
      <circle cx="26.5" cy="43.5" r="2.3" fill="#6b5694" />
    </>
  );
}

const CHARACTERS: Record<Role, () => React.JSX.Element> = {
  boss: Boss,
  inventory: Inventory,
  accounting: Accounting,
  facilities: Facilities,
  customer_service: CustomerService,
};

export default function AgentIcon({ role, label }: { role: Role; label?: string }) {
  const Character = CHARACTERS[role];
  return (
    <svg viewBox="0 0 64 64" className="agent-icon" role="img" aria-label={label ?? role}>
      <Character />
    </svg>
  );
}
