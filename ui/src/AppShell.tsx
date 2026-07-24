import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import "./AppShell.css";

export type ViewMode =
  | "digital-twin"
  | "model-workbench"
  | "contest-workflow"
  | "war-room"
  | "research"
  | "workspace"
  | "preview"
  | "news-brief";

type AppShellProps = {
  activeView: ViewMode;
  season: number;
  week: number;
  slate: string;
  pendingAction?: string | null;
  onNavigate: (view: ViewMode) => void;
  children: ReactNode;
};

type IconName = "twin" | "models" | "war" | "research" | "delivery" | "news" | "operations" | "vision" | "search" | "spark";

const NAV_ITEMS: Array<{ view: ViewMode; label: string; shortLabel: string; icon: IconName }> = [
  { view: "digital-twin", label: "Digital Twin", shortLabel: "Twin", icon: "twin" },
  { view: "model-workbench", label: "Models", shortLabel: "Models", icon: "models" },
  { view: "war-room", label: "War Room", shortLabel: "War", icon: "war" },
  { view: "research", label: "Research Lab", shortLabel: "Lab", icon: "research" },
  { view: "contest-workflow", label: "Delivery", shortLabel: "Deliver", icon: "delivery" },
  { view: "news-brief", label: "Intelligence", shortLabel: "Intel", icon: "news" },
  { view: "workspace", label: "Operations", shortLabel: "Ops", icon: "operations" },
];

const COMMAND_ITEMS = [
  ...NAV_ITEMS,
  { view: "preview" as ViewMode, label: "Experience Lab", shortLabel: "Lab", icon: "vision" as IconName },
];

const VIEW_META: Record<ViewMode, { eyebrow: string; title: string; description: string }> = {
  "digital-twin": {
    eyebrow: "Personal Intelligence",
    title: "Digital Twin",
    description: "Combine model evidence, field behavior, and your accumulated judgment.",
  },
  "model-workbench": {
    eyebrow: "Forecasting",
    title: "Model Workbench",
    description: "Build projections, evaluate rules, and inspect model readiness.",
  },
  "war-room": {
    eyebrow: "Decision Layer",
    title: "Slate War Room",
    description: "Convert signals, leverage, and conviction into portfolio decisions.",
  },
  research: {
    eyebrow: "Simulation Intelligence",
    title: "Research Lab",
    description: "Run shocks, historical backtests, and baseline-versus-shock portfolio comparisons.",
  },
  "contest-workflow": {
    eyebrow: "Execution",
    title: "Contest Delivery",
    description: "Import entries, assign lineups, validate, and export with confidence.",
  },
  "news-brief": {
    eyebrow: "Live Intelligence",
    title: "Daily Briefing",
    description: "Review slate-moving news and teach the system what matters to you.",
  },
  workspace: {
    eyebrow: "System Control",
    title: "Operations",
    description: "Run ingestion, data-quality, agent, and optimization workflows.",
  },
  preview: {
    eyebrow: "Product Vision",
    title: "Experience Lab",
    description: "Explore the visual direction for your decision-intelligence system.",
  },
};

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    twin: <><circle cx="10" cy="7" r="3" /><path d="M4.5 17c.7-3.1 2.5-4.7 5.5-4.7s4.8 1.6 5.5 4.7" /><path d="M3 4.5 5 3m12 1.5L15 3M10 1V0" /></>,
    models: <><path d="M4 18V9" /><path d="M10 18V5" /><path d="M16 18v-7" /><path d="M3 18h15" /></>,
    war: <><circle cx="10" cy="10" r="6" /><path d="M10 1v3M10 16v3M1 10h3M16 10h3" /><circle cx="10" cy="10" r="2" /></>,
    research: <><path d="M7 2v5l-4 8a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-4-8V2" /><path d="M6 11h8M6 2h8" /></>,
    delivery: <><path d="M3 6h14v10H3z" /><path d="m3 6 7 5 7-5" /><path d="M14 3h3v3" /></>,
    news: <><path d="M4 3h12v14H4z" /><path d="M7 7h6M7 10h6M7 13h4" /></>,
    operations: <><path d="M4 5h12M4 10h12M4 15h12" /><circle cx="8" cy="5" r="1.5" /><circle cx="13" cy="10" r="1.5" /><circle cx="7" cy="15" r="1.5" /></>,
    vision: <><path d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5Z" /><circle cx="10" cy="10" r="2.5" /></>,
    search: <><circle cx="9" cy="9" r="5" /><path d="m13 13 4 4" /></>,
    spark: <><path d="m10 2 1.4 4.6L16 8l-4.6 1.4L10 14l-1.4-4.6L4 8l4.6-1.4L10 2Z" /><path d="m16 14 .6 1.9 1.9.6-1.9.6L16 19l-.6-1.9-1.9-.6 1.9-.6L16 14Z" /></>,
  };

  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      {paths[name]}
    </svg>
  );
}

function formatSlate(value: string) {
  return value.replaceAll("_", " ");
}

export function AppShell({
  activeView,
  season,
  week,
  slate,
  pendingAction,
  onNavigate,
  children,
}: AppShellProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const commandTriggerRef = useRef<HTMLButtonElement>(null);
  const firstCommandRef = useRef<HTMLButtonElement>(null);
  const meta = VIEW_META[activeView];
  const contextLabel = useMemo(
    () => `${season} · W${week} · ${formatSlate(slate)}`,
    [season, week, slate],
  );

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
      }
      const shortcutIndex = Number(event.key) - 1;
      if (paletteOpen && shortcutIndex >= 0 && shortcutIndex < COMMAND_ITEMS.length) {
        event.preventDefault();
        onNavigate(COMMAND_ITEMS[shortcutIndex].view);
        setPaletteOpen(false);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        window.requestAnimationFrame(() => commandTriggerRef.current?.focus());
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onNavigate, paletteOpen]);

  useEffect(() => {
    if (paletteOpen) firstCommandRef.current?.focus();
  }, [paletteOpen]);

  const navigate = (view: ViewMode) => {
    onNavigate(view);
    setPaletteOpen(false);
  };

  return (
    <div className="product-shell">
      <aside className="shell-rail" aria-label="Primary navigation">
        <button className="shell-brand" type="button" onClick={() => navigate("digital-twin")} aria-label="Football Opt home">
          <span className="shell-brand-mark"><Icon name="spark" /></span>
          <span className="shell-brand-copy"><strong>Football Opt</strong><small>Decision OS</small></span>
        </button>

        <nav className="shell-nav">
          <p>Workspaces</p>
          {NAV_ITEMS.map((item) => (
            <button
              type="button"
              key={item.view}
              className={activeView === item.view ? "active" : ""}
              aria-current={activeView === item.view ? "page" : undefined}
              onClick={() => navigate(item.view)}
            >
              <span className="shell-nav-icon"><Icon name={item.icon} /></span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="shell-rail-footer">
          <button type="button" className={activeView === "preview" ? "shell-vision active" : "shell-vision"} onClick={() => navigate("preview")}>
            <Icon name="vision" /><span>Experience Lab</span>
          </button>
          <div className="shell-context-card">
            <span><i /> Active context</span>
            <strong>{season} · Week {week}</strong>
            <small>{formatSlate(slate)}</small>
          </div>
        </div>
      </aside>

      <div className="shell-stage">
        <header className="shell-topbar">
          <div className="shell-page-identity">
            <span>{meta.eyebrow}</span>
            <div><h1>{meta.title}</h1><p>{meta.description}</p></div>
          </div>
          <div className="shell-top-actions">
            {pendingAction && <span className="shell-pending" aria-live="polite"><i />{pendingAction}</span>}
            <div className="shell-slate-chip"><span>Live context</span><strong>{contextLabel}</strong></div>
            <button ref={commandTriggerRef} className="shell-command-trigger" type="button" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">
              <Icon name="search" /><span>Jump to</span><kbd>⌘ K</kbd>
            </button>
          </div>
        </header>

        <div className="shell-view">{children}</div>
      </div>

      <nav className="shell-mobile-nav" aria-label="Mobile navigation">
        {NAV_ITEMS.map((item) => (
          <button
            type="button"
            key={item.view}
            className={activeView === item.view ? "active" : ""}
            aria-current={activeView === item.view ? "page" : undefined}
            onClick={() => navigate(item.view)}
          >
            <Icon name={item.icon} />
            <span>{item.shortLabel}</span>
          </button>
        ))}
      </nav>

      {paletteOpen && (
        <div
          className="command-backdrop"
          role="presentation"
          onMouseDown={() => {
            setPaletteOpen(false);
            commandTriggerRef.current?.focus();
          }}
        >
          <section className="command-palette" role="dialog" aria-modal="true" aria-label="Workspace command palette" onMouseDown={(event) => event.stopPropagation()}>
            <div className="command-search"><Icon name="search" /><span>Go to a workspace</span><kbd>ESC</kbd></div>
            <div className="command-context"><span>Current slate</span><strong>{contextLabel}</strong></div>
            <div className="command-list">
              {COMMAND_ITEMS.map((item, index) => (
                <button ref={index === 0 ? firstCommandRef : undefined} type="button" key={item.view} onClick={() => navigate(item.view)}>
                  <span className="command-item-icon"><Icon name={item.icon} /></span>
                  <span><strong>{item.label}</strong><small>{VIEW_META[item.view].description}</small></span>
                  <kbd>{index + 1}</kbd>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
