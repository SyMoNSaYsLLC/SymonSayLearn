"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/* The navigation.
 *
 * Grouped, not flat. The three surfaces come first and together because they are
 * peers and each maps to one model card the gateway serves. Operator views are a
 * separate group: inspecting the rack is a different activity from using it, and
 * mixing the two makes a list you have to read rather than scan.
 */

interface Item {
  href: string;
  label: string;
  hint: string;
}

const SURFACES: Item[] = [
  { href: "/chat", label: "Chat", hint: "Quick questions and drafting" },
  { href: "/code", label: "Code", hint: "Write and run code" },
  { href: "/work", label: "Cowork", hint: "Longer tasks and documents" },
];

const OPERATOR: Item[] = [
  { href: "/", label: "Overview", hint: "What is serving right now" },
  { href: "/models", label: "Models", hint: "The registry the gateway projects" },
  { href: "/rack", label: "Rack", hint: "Units, ports and the GPU lock" },
  { href: "/settings", label: "Settings", hint: "Surfaces, tools and policy" },
];

function Group({ title, items, pathname }: { title: string; items: Item[]; pathname: string }) {
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <div
        className="faint"
        style={{
          fontSize: "var(--text-xs)",
          fontWeight: 600,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          padding: "0 var(--space-3)",
        }}
      >
        {title}
      </div>
      <nav className="nav">
        {items.map((item) => {
          // Exact match for the root, prefix match elsewhere, so /models/symon-chat
          // still marks Models as current without / matching everything.
          const current = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className="nav-link"
              aria-current={current ? "page" : undefined}
              title={item.hint}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function Nav() {
  const pathname = usePathname();
  return (
    <div className="stack" style={{ gap: "var(--space-5)" }}>
      <Group title="Surfaces" items={SURFACES} pathname={pathname} />
      <Group title="Estate" items={OPERATOR} pathname={pathname} />
    </div>
  );
}
