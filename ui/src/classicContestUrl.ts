/** Optional reporting context for one Classic small-field contest. */
export function classicContestUrls(value: string): string[] {
  const urls = value.trim().split(/\s+/).filter(Boolean);
  if (urls.length > 1) {
    throw new Error("Classic small-field reporting accepts one DraftKings contest URL. Remove the extra URL before running the optimizer.");
  }
  if (urls.length === 1) {
    let parsed: URL;
    try {
      parsed = new URL(urls[0]);
    } catch {
      throw new Error("Enter a DraftKings contest URL in the form https://www.draftkings.com/draft/contest/<id>.");
    }
    if (parsed.protocol !== "https:" || !["draftkings.com", "www.draftkings.com"].includes(parsed.hostname)
      || !/^\/draft\/contest\/\d+\/?$/.test(parsed.pathname)) {
      throw new Error("Enter a DraftKings contest URL in the form https://www.draftkings.com/draft/contest/<id>.");
    }
  }
  return urls;
}
