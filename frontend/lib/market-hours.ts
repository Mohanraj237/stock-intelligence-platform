/**
 * NSE India market-hours utilities (IST = UTC+5:30).
 * No external dependencies — all pure date arithmetic.
 */

export type MarketStatus = "open" | "preopen" | "closed" | "weekend";

export interface MarketInfo {
  status:      MarketStatus;
  label:       string;           // "LIVE", "Pre-open", "Closed", "Weekend"
  labelColor:  string;           // Tailwind text colour class
  dotColor:    string;           // Tailwind background colour for the dot
  nextOpenIST: Date | null;      // null when market is currently open
  minutesToOpen: number | null;  // minutes until next open (null if already open)
  sessionNote: string;           // human-readable context line
}

const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun",
                      "Jul","Aug","Sep","Oct","Nov","Dec"];

/** Convert any Date to IST (UTC+5:30). */
export function toIST(d: Date = new Date()): Date {
  return new Date(d.getTime() + (5.5 * 60 - d.getTimezoneOffset()) * 60_000);
}

/** Format a Date (in IST) as "DD-Mon-YYYY". */
export function fmtISTDate(d: Date): string {
  const ist = toIST(d);
  return `${String(ist.getDate()).padStart(2,"0")}-${MONTHS_SHORT[ist.getMonth()]}-${ist.getFullYear()}`;
}

/** Format a Date as readable time "9:15 AM IST". */
export function fmtISTTime(d: Date): string {
  const ist = toIST(d);
  const h   = ist.getHours();
  const m   = String(ist.getMinutes()).padStart(2,"0");
  const ap  = h >= 12 ? "PM" : "AM";
  return `${h > 12 ? h - 12 : h || 12}:${m} ${ap} IST`;
}

/**
 * Get the nearest WEEKLY expiry Thursday.
 * - If today IS Thursday and market is still open → current week.
 * - Otherwise → next Thursday (or the Thursday after if today is Thursday after-hours).
 */
export function nearestWeeklyExpiry(): string {
  const ist  = toIST();
  const dow  = ist.getDay(); // 0=Sun … 6=Sat
  const hm   = ist.getHours() * 60 + ist.getMinutes();
  const CLOSE = 15 * 60 + 30;

  let d = new Date(ist);
  // days until Thursday (0 if already Thursday)
  let diff = (4 - dow + 7) % 7;
  if (diff === 0 && hm >= CLOSE) diff = 7; // Thursday after close → next week
  d.setDate(d.getDate() + diff);
  return fmtISTDate(d);
}

/**
 * Compute next monthly expiry (last Thursday of the current or next month).
 * Used as a fallback for equity options.
 */
export function nearestMonthlyExpiry(): string {
  const ist = toIST();
  const y   = ist.getFullYear();
  const m   = ist.getMonth();

  const lastThursday = (year: number, month: number): Date => {
    const last = new Date(year, month + 1, 0); // last day of month
    while (last.getDay() !== 4) last.setDate(last.getDate() - 1);
    return last;
  };

  let exp = lastThursday(y, m);
  // If that expiry has already passed (or today is expiry day after market close)
  const hm = ist.getHours() * 60 + ist.getMinutes();
  if (toIST(exp) < ist || (exp.getDate() === ist.getDate() && hm >= 15 * 60 + 30)) {
    exp = lastThursday(y, m + 1);
  }
  return fmtISTDate(exp);
}

/** Core: get the current NSE market status. */
export function getMarketInfo(): MarketInfo {
  const ist = toIST();
  const dow = ist.getDay();
  const hm  = ist.getHours() * 60 + ist.getMinutes();

  const PREOPEN_START = 9  * 60;           //  9:00 AM
  const OPEN_START    = 9  * 60 + 15;      //  9:15 AM
  const CLOSE         = 15 * 60 + 30;      //  3:30 PM

  if (dow === 0 || dow === 6) {
    const nextMon = new Date(ist);
    nextMon.setDate(ist.getDate() + (dow === 6 ? 2 : 1));
    nextMon.setHours(9, 15, 0, 0);
    const mins = Math.round((nextMon.getTime() - ist.getTime()) / 60_000);
    return {
      status:        "weekend",
      label:         "Weekend",
      labelColor:    "text-slate-400",
      dotColor:      "bg-slate-500",
      nextOpenIST:   nextMon,
      minutesToOpen: mins,
      sessionNote:   `NSE reopens ${dow === 6 ? "Monday" : "tomorrow"} at 9:15 AM IST`,
    };
  }

  if (hm >= OPEN_START && hm < CLOSE) {
    const closeToday = new Date(ist);
    closeToday.setHours(15, 30, 0, 0);
    const minsLeft = Math.round((closeToday.getTime() - ist.getTime()) / 60_000);
    return {
      status:        "open",
      label:         "LIVE",
      labelColor:    "text-emerald-400",
      dotColor:      "bg-emerald-400",
      nextOpenIST:   null,
      minutesToOpen: null,
      sessionNote:   `Market closes in ${minsLeft} min · Exit intraday trades by 3:10 PM`,
    };
  }

  if (hm >= PREOPEN_START && hm < OPEN_START) {
    const openNow = new Date(ist);
    openNow.setHours(9, 15, 0, 0);
    const mins = Math.round((openNow.getTime() - ist.getTime()) / 60_000);
    return {
      status:        "preopen",
      label:         "Pre-open",
      labelColor:    "text-amber-400",
      dotColor:      "bg-amber-400",
      nextOpenIST:   openNow,
      minutesToOpen: mins,
      sessionNote:   `Pre-open session · Main session starts in ${mins} min`,
    };
  }

  // Closed (after 3:30 PM or before 9:00 AM on a weekday)
  const nextOpen = new Date(ist);
  if (hm >= CLOSE) {
    // After close — next open is tomorrow (or Monday if Friday)
    const nextDay = dow === 5 ? 3 : 1;
    nextOpen.setDate(nextOpen.getDate() + nextDay);
  }
  nextOpen.setHours(9, 15, 0, 0);
  const mins = Math.round((nextOpen.getTime() - ist.getTime()) / 60_000);
  const hrsLeft = Math.floor(mins / 60);
  const minLeft = mins % 60;
  const timeStr = hrsLeft > 0
    ? `${hrsLeft}h ${minLeft}m`
    : `${minLeft}m`;

  return {
    status:        "closed",
    label:         "Closed",
    labelColor:    "text-slate-400",
    dotColor:      "bg-slate-500",
    nextOpenIST:   nextOpen,
    minutesToOpen: mins,
    sessionNote:   `Opens in ${timeStr} · ${fmtISTTime(nextOpen)}`,
  };
}
