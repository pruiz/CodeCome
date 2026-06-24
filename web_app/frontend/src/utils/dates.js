const SPAIN_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('es-ES', {
  timeZone: 'Europe/Madrid',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const SPAIN_TIME_FORMATTER = new Intl.DateTimeFormat('es-ES', {
  timeZone: 'Europe/Madrid',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

function parseDate(value) {
  if (!value) return null;
  // The backend currently emits local Europe/Madrid wall-clock timestamps with
  // a UTC suffix (for example, 11:01+00:00 even when the server clock is 11:01 CEST).
  // Strip that suffix so the UI does not add two hours on display.
  const normalized = typeof value === 'string'
    ? value.replace(/(?:Z|\+00:00)$/, '')
    : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatSpainDateTime(value) {
  const date = parseDate(value);
  return date ? SPAIN_DATE_TIME_FORMATTER.format(date) : '-';
}

export function formatSpainTime(value) {
  const date = parseDate(value);
  return date ? SPAIN_TIME_FORMATTER.format(date) : '-';
}
