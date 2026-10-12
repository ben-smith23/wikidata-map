const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "18 Jun 1815", "Jun 1815" or "1815" depending on precision (11 day, 10 month, 9 year); BC for negative years. */
export function formatDate(iso, precision) {
  const m = /^(-?)(\d+)-(\d\d)-(\d\d)/.exec(iso);
  if (!m) return iso;
  const year = Number(m[2]);
  const y = m[1] ? `${year} BC` : String(year);
  if (precision >= 11) return `${Number(m[4])} ${MONTHS[Number(m[3]) - 1]} ${y}`;
  if (precision === 10) return `${MONTHS[Number(m[3]) - 1]} ${y}`;
  return y;
}

export function dateRange(e) {
  const start = formatDate(e.date, e.prec);
  return e.end && e.end !== e.date ? `${start} – ${formatDate(e.end, e.endPrec)}` : start;
}
