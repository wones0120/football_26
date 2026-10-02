import type { SavedContest } from "./api";

const record = (value: unknown): Record<string, unknown> =>
  value != null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};

function number(value: unknown, integer = false): number | null {
  if (typeof value !== "number" && (typeof value !== "string" || !value.trim())) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && (!integer || Number.isInteger(parsed)) ? parsed : null;
}

const count = (value: unknown) => number(value, true)?.toLocaleString("en-US") ?? "Unavailable";
const money = (value: unknown) => {
  const amount = number(value);
  return amount == null ? "Unavailable" : amount.toLocaleString("en-US", { style: "currency", currency: "USD" });
};

function contestType(facts: Record<string, unknown>, name: string) {
  const detail = record(record(facts.source_payload).contestDetail);
  const tiers = Array.isArray(detail.payoutSummary) ? detail.payoutSummary.map(record) : [];
  const tickets = record(detail.payoutDescriptions).Ticket != null || tiers.some((tier) => record(tier.tierPayoutDescriptions).Ticket != null);
  const cash = record(detail.payoutDescriptions).Cash != null || tiers.some((tier) => record(tier.tierPayoutDescriptions).Cash != null);
  if (tickets) return cash ? "Ticket + cash prizes" : "Ticket satellite";
  if (record(detail.attributes).IsQualifier === "true" || /\b(satellite|supersat|qualifier)\b/i.test(name)) return "Qualifier / satellite";
  if (/\b(head[ -]to[ -]head|h2h)\b/i.test(name)) return "Head-to-head";
  if (/\bdouble[ -]?up\b/i.test(name)) return "Double-up";
  if (/\b50\s*[\/-]\s*50\b/.test(name)) return "50/50";
  if (/\b(triple[ -]?up|triple|multiplier)\b/i.test(name)) return "Cash multiplier";
  if (cash || detail.IsCashPrizeOnly === true) return "Cash-prize tournament";
  return "Type unavailable";
}

/** Display one dated observation without mixing fresh and older field values. */
export function savedContestSummary(row: SavedContest) {
  const latest = row.latest_contest;
  const failed = Boolean(row.latest_error || latest?.error || latest?.source === "unavailable");
  const useSaved = Boolean(row.latest_successful_contest && (!latest || failed));
  const facts = (useSaved ? row.latest_successful_contest : latest) ?? {};
  const name = typeof facts.name === "string" ? facts.name : row.name ?? row.contest_id;
  const maximum = number(facts.maximum_entries, true);
  const type = contestType(facts, name);
  return {
    name, type,
    entryLimit: maximum == null || maximum < 1 ? "Entry limit unavailable" : maximum === 1 ? "Single entry" : `${maximum.toLocaleString("en-US")}-max per person`,
    entries: count(facts.current_entries), capacity: count(facts.capacity),
    entryFee: money(facts.entry_fee), prizePool: money(facts.prize_pool),
    prizeLabel: type === "Ticket satellite" ? "Ticket value" : type === "Ticket + cash prizes" ? "Total prize value" : "Prize pool",
    snapshotLabel: useSaved ? "Saved snapshot" : failed || !latest ? "Details unavailable" : "Observed",
    observedAt: typeof facts.observed_at === "string" ? facts.observed_at : useSaved ? null : row.latest_observed_at ?? null,
  };
}
