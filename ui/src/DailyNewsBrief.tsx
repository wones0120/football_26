import { useEffect, useState } from "react";
import {
  fetchNewsMonitorFeedback,
  fetchNewsMonitorReport,
  runNewsMonitor,
  upsertNewsMonitorFeedback,
  type NewsMonitorFeedbackChoice,
  type NewsMonitorFeedbackRow,
  type NewsMonitorHeadline,
  type NewsMonitorRunResponse,
  type NewsMonitorSignal,
} from "./api";
import "./DailyNewsBrief.css";

type DailyNewsBriefProps = {
  onBack: () => void;
};

type SignalSection = {
  label: string;
  signals: NewsMonitorSignal[];
};

type BriefingSummary = {
  changed: string;
  matters: string;
  watch: string;
};

type NewsFeedbackEntry = {
  choice: NewsMonitorFeedbackChoice | null;
  note: string;
};

type NewsFeedbackMap = Record<string, NewsFeedbackEntry>;
type FeedbackSaveState = "idle" | "saving" | "saved" | "error";
type FeedbackStatusMap = Record<string, FeedbackSaveState>;

const FEEDBACK_CHOICES: NewsMonitorFeedbackChoice[] = ["Valuable", "Relevant", "Monitor", "Noise"];
const NEWS_BRIEF_ENABLED = false;

function formatLocalDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function titleCase(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value
    .replaceAll("_", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function signalLabel(signal: NewsMonitorSignal) {
  const pieces = [signal.player_name, signal.team].filter(Boolean);
  return pieces.length > 0 ? `${pieces.join(" · ")}: ${signal.signal_text}` : signal.signal_text;
}

function signalSource(signal: NewsMonitorSignal, headlines: NewsMonitorHeadline[]) {
  if (signal.source_link) {
    try {
      return new URL(signal.source_link).hostname.replace(/^www\./, "");
    } catch {
      // Fall back to headline metadata below.
    }
  }
  const headline = headlines.find((item) => item.link === signal.source_link);
  return headline?.source_id ? titleCase(headline.source_id) : titleCase(signal.signal_type);
}

function signalTime(signal: NewsMonitorSignal, headlines: NewsMonitorHeadline[]) {
  const headline = headlines.find((item) => item.link === signal.source_link);
  if (!headline?.published_at) return "";
  const parsed = new Date(headline.published_at);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function summarizeReport(report: NewsMonitorRunResponse) {
  const summary = report.report.summary;
  const sourceErrors = report.report.source_errors.length;
  if (summary.high_priority_count === 0) {
    return "No high-priority DFS signals were identified in the latest report.";
  }
  return `${summary.high_priority_count} high-priority signals across ${report.sources_checked} source checks.${sourceErrors > 0 ? ` ${sourceErrors} source issue${sourceErrors === 1 ? "" : "s"} need review.` : ""}`;
}

function signalFeedbackKey(reportDate: string, signal: NewsMonitorSignal) {
  return [reportDate, signal.signal_type, signal.signal_text, signal.source_link ?? "", signal.player_name ?? "", signal.team ?? ""].join("|");
}

function toFeedbackMap(rows: NewsMonitorFeedbackRow[]): NewsFeedbackMap {
  return rows.reduce<NewsFeedbackMap>((accumulator, row) => {
    accumulator[row.signal_key] = {
      choice: row.feedback_choice ?? null,
      note: row.note_text ?? "",
    };
    return accumulator;
  }, {});
}

function topSignal(report: NewsMonitorRunResponse) {
  return (
    report.report.high_priority_signals[0] ??
    report.report.injury_updates[0] ??
    report.report.roster_moves[0] ??
    report.report.depth_chart_notes[0] ??
    report.report.manual_review[0] ??
    null
  );
}

function buildBriefingSummary(report: NewsMonitorRunResponse): BriefingSummary {
  const leadSignal = topSignal(report);
  const sourceErrors = report.report.source_errors.length;
  const injuryCount = report.report.injury_updates.length;
  const rosterCount = report.report.roster_moves.length;
  const depthCount = report.report.depth_chart_notes.length;
  const reviewCount = report.report.manual_review.length;

  const changed = leadSignal
    ? `${titleCase(leadSignal.signal_type)} pressure is leading the report: ${signalLabel(leadSignal)}`
    : "No fresh slate-moving item took control of the report.";

  const matters = injuryCount > 0
    ? `${injuryCount} injury update${injuryCount === 1 ? "" : "s"} are driving the most immediate DFS review, with ${report.report.summary.high_priority_count} high-priority signals total.`
    : rosterCount > 0 || depthCount > 0
      ? `${rosterCount} roster move${rosterCount === 1 ? "" : "s"} and ${depthCount} depth-chart note${depthCount === 1 ? "" : "s"} are shaping the current slate outlook.`
      : "The current report is more informational than disruptive, with no concentrated injury wave yet.";

  const watch = sourceErrors > 0
    ? `${sourceErrors} source issue${sourceErrors === 1 ? "" : "s"} still need attention, and ${reviewCount} item${reviewCount === 1 ? "" : "s"} remain in manual-review watch if the signal mix changes.`
    : reviewCount > 0
      ? `${reviewCount} item${reviewCount === 1 ? "" : "s"} remain in manual review. Watch for confirmation before changing portfolio posture.`
      : "Watch the next source refresh for confirmations, especially if ownership or depth-chart assumptions move before lock.";

  return { changed, matters, watch };
}

export function DailyNewsBrief({ onBack }: DailyNewsBriefProps) {
  const [reportDate, setReportDate] = useState(formatLocalDate(new Date()));
  const [report, setReport] = useState<NewsMonitorRunResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<NewsFeedbackMap>({});
  const [feedbackStatus, setFeedbackStatus] = useState<FeedbackStatusMap>({});

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!NEWS_BRIEF_ENABLED) {
        setLoading(false);
        setError(null);
        setReport(null);
        setFeedback({});
        setFeedbackStatus({});
        setBanner("Daily news processing is paused while model workbench work is the focus.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const nextReport = await fetchNewsMonitorReport(reportDate);
        const nextFeedback = await fetchNewsMonitorFeedback(reportDate);
        if (!cancelled) {
          setReport(nextReport);
          setFeedback(toFeedbackMap(nextFeedback.rows));
          setFeedbackStatus({});
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : String(nextError));
          setReport(null);
          setFeedback({});
          setFeedbackStatus({});
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load().catch(() => {
      // UI state already handled above.
    });

    return () => {
      cancelled = true;
    };
  }, [reportDate]);

  const handleRun = async () => {
    if (!NEWS_BRIEF_ENABLED) {
      setBanner("Daily news processing is paused while model workbench work is the focus.");
      setLoading(false);
      return;
    }
    setRunLoading(true);
    setBanner(null);
    setError(null);
    try {
      const result = await runNewsMonitor({ run_date: reportDate, force: true });
      const nextFeedback = await fetchNewsMonitorFeedback(reportDate);
      setReport(result);
      setFeedback(toFeedbackMap(nextFeedback.rows));
      setFeedbackStatus({});
      setBanner(result.message);
    } catch (nextError) {
      setBanner(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setRunLoading(false);
      setLoading(false);
    }
  };

  const signalSections: SignalSection[] = report
    ? [
        { label: "High Priority", signals: report.report.high_priority_signals },
        { label: "Injury Updates", signals: report.report.injury_updates },
        { label: "Roster Moves", signals: report.report.roster_moves },
        { label: "Depth Chart", signals: report.report.depth_chart_notes },
        { label: "Manual Review", signals: report.report.manual_review },
      ].filter((section) => section.signals.length > 0)
    : [];
  const briefingSummary = report ? buildBriefingSummary(report) : null;

  const updateFeedback = (key: string, next: Partial<NewsFeedbackEntry>) => {
    setFeedback((current) => ({
      ...current,
      [key]: {
        choice: current[key]?.choice ?? null,
        note: current[key]?.note ?? "",
        ...next,
      },
    }));
  };

  const saveFeedback = async (signal: NewsMonitorSignal, nextEntry: NewsFeedbackEntry) => {
    const key = signalFeedbackKey(reportDate, signal);
    setFeedbackStatus((current) => ({ ...current, [key]: "saving" }));
    try {
      await upsertNewsMonitorFeedback({
        run_date: reportDate,
        signal_key: key,
        signal_type: signal.signal_type,
        signal_text: signal.signal_text,
        player_name: signal.player_name ?? null,
        team: signal.team ?? null,
        source_link: signal.source_link ?? null,
        feedback_choice: nextEntry.choice,
        note_text: nextEntry.note,
      });
      setFeedbackStatus((current) => ({ ...current, [key]: "saved" }));
    } catch {
      setFeedbackStatus((current) => ({ ...current, [key]: "error" }));
    }
  };

  const feedbackStatusLabel = (key: string) => {
    const state = feedbackStatus[key] ?? "idle";
    if (state === "saving") return "Saving feedback...";
    if (state === "saved") return "Saved";
    if (state === "error") return "Could not save";
    return " ";
  };

  return (
    <main className="news-brief">
      <header className="news-brief-hero">
        <div>
          <p className="news-brief-kicker">Daily Brief</p>
          <h1>DFS News Briefing</h1>
          <p className="news-brief-summary">
            {report ? summarizeReport(report) : "Load the latest news-monitor report and read the slate-moving summary in one place."}
          </p>
        </div>

        <div className="news-brief-actions">
          <label>
            Report Date
            <input type="date" value={reportDate} onChange={(event) => setReportDate(event.target.value)} />
          </label>
          <button type="button" onClick={handleRun} disabled={runLoading}>
            {runLoading ? "Running News" : "Run News"}
          </button>
          <button type="button" className="brief-secondary" onClick={onBack}>
            Back To War Room
          </button>
        </div>
      </header>

      {banner && <div className={`news-brief-banner ${error ? "error" : ""}`}>{banner}</div>}

      <section className="news-brief-grid">
        <section className="brief-main">
          {loading && (
            <article className="brief-state-card">
              <span>Loading</span>
              <strong>Fetching the requested daily report.</strong>
            </article>
          )}

          {!loading && error && (
            <article className="brief-state-card error">
              <span>Unavailable</span>
              <strong>{error}</strong>
            </article>
          )}

          {!loading && !error && !report && (
            <article className="brief-state-card">
              <span>No Report</span>
              <strong>No daily news report is stored for {reportDate} yet.</strong>
            </article>
          )}

          {!loading && !error && report && (
            <>
              <section className="brief-metrics">
                <article>
                  <span>Run Status</span>
                  <strong>{titleCase(report.status)}</strong>
                  <small>{report.message}</small>
                </article>
                <article>
                  <span>High Priority</span>
                  <strong>{report.report.summary.high_priority_count}</strong>
                  <small>Signals worth immediate slate review.</small>
                </article>
                <article>
                  <span>Items Ingested</span>
                  <strong>{report.items_ingested}</strong>
                  <small>{report.signals_extracted} signals extracted.</small>
                </article>
                <article>
                  <span>Source Errors</span>
                  <strong>{report.report.source_errors.length}</strong>
                  <small>{report.sources_checked} sources checked in this run.</small>
                </article>
              </section>

              {briefingSummary && (
                <section className="brief-narrative">
                  <article>
                    <span>What Changed</span>
                    <strong>{briefingSummary.changed}</strong>
                  </article>
                  <article>
                    <span>What Matters</span>
                    <strong>{briefingSummary.matters}</strong>
                  </article>
                  <article>
                    <span>What To Watch</span>
                    <strong>{briefingSummary.watch}</strong>
                  </article>
                </section>
              )}

              {signalSections.map((section) => (
                <section className="brief-section" key={section.label}>
                  <div className="brief-section-head">
                    <span>{section.label}</span>
                    <strong>{section.signals.length} item{section.signals.length === 1 ? "" : "s"}</strong>
                  </div>
                  <div className="brief-signal-list">
                    {section.signals.map((signal) => {
                      const feedbackKey = signalFeedbackKey(report.run_date, signal);
                      const signalFeedback = feedback[feedbackKey] ?? { choice: null, note: "" };
                      return (
                        <article key={`${section.label}-${signal.signal_type}-${signal.signal_text}-${signal.source_link ?? ""}`} className="brief-signal-card">
                          <div className="brief-signal-meta">
                            <span>{signalSource(signal, report.report.team_headlines)}</span>
                            <span>{signalTime(signal, report.report.team_headlines) || titleCase(signal.confidence)}</span>
                          </div>
                          <strong>{signalLabel(signal)}</strong>
                          <div className="brief-feedback">
                            <div className="brief-feedback-choices" role="group" aria-label="News feedback">
                              {FEEDBACK_CHOICES.map((choice) => (
                                <button
                                  key={choice}
                                  type="button"
                                  className={signalFeedback.choice === choice ? "active" : ""}
                                  onClick={() => {
                                    const nextChoice = signalFeedback.choice === choice ? null : choice;
                                    const nextEntry = {
                                      ...signalFeedback,
                                      choice: nextChoice,
                                    };
                                    updateFeedback(feedbackKey, { choice: nextChoice });
                                    void saveFeedback(signal, nextEntry);
                                  }}
                                >
                                  {choice}
                                </button>
                              ))}
                            </div>
                            <label>
                              Note
                              <textarea
                                rows={2}
                                value={signalFeedback.note}
                                onChange={(event) => updateFeedback(feedbackKey, { note: event.target.value })}
                                onBlur={(event) =>
                                  void saveFeedback(signal, {
                                    ...signalFeedback,
                                    note: event.currentTarget.value,
                                  })
                                }
                                placeholder="Why is this useful, relevant, or not worth surfacing?"
                              />
                            </label>
                            <small className={`brief-feedback-status ${feedbackStatus[feedbackKey] ?? "idle"}`}>
                              {feedbackStatusLabel(feedbackKey)}
                            </small>
                          </div>
                          <footer>
                            <span>{titleCase(signal.signal_type)}</span>
                            <span>{titleCase(signal.dfs_relevance)}</span>
                            {signal.source_link ? (
                              <a href={signal.source_link} target="_blank" rel="noreferrer">
                                Source
                              </a>
                            ) : null}
                          </footer>
                        </article>
                      );
                    })}
                  </div>
                </section>
              ))}
            </>
          )}
        </section>

        <aside className="brief-rail">
          <section className="brief-rail-card">
            <div className="brief-section-head">
              <span>Top Headlines</span>
              <strong>{report?.report.team_headlines.length ?? 0}</strong>
            </div>
            <div className="brief-headlines">
              {(report?.report.team_headlines ?? []).slice(0, 12).map((headline) => (
                <article key={`${headline.source_id}-${headline.link ?? headline.title ?? ""}`}>
                  <span>{titleCase(headline.source_id)}</span>
                  <strong>{headline.title ?? "Untitled headline"}</strong>
                  {headline.link ? (
                    <a href={headline.link} target="_blank" rel="noreferrer">
                      Open Source
                    </a>
                  ) : null}
                </article>
              ))}
              {report && report.report.team_headlines.length === 0 && (
                <p className="brief-empty">No headlines were attached to this report.</p>
              )}
            </div>
          </section>

          <section className="brief-rail-card">
            <div className="brief-section-head">
              <span>Source Health</span>
              <strong>{report?.report.sources_checked.length ?? 0}</strong>
            </div>
            <div className="brief-source-health">
              {(report?.report.sources_checked ?? []).map((source) => (
                <article key={source.source_id}>
                  <div>
                    <span>{source.source_name}</span>
                    <strong>{titleCase(source.status)}</strong>
                  </div>
                  <small>{source.items_seen} seen · {source.signals_inserted} signals</small>
                </article>
              ))}
              {(report?.report.source_errors ?? []).map((source) => (
                <article key={`error-${source.source_id}`} className="source-error">
                  <div>
                    <span>{titleCase(source.source_id)}</span>
                    <strong>Error</strong>
                  </div>
                  <small>{source.error}</small>
                </article>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}
