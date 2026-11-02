import { dateFromKey, dateKey, hasMemo } from './readingDates';
export function activityCounts(records, communityDays = [], today = new Date()) {
  const last = dateKey(today), counts = {};
  const add = (day) => { if (dateFromKey(day) && day <= last) counts[day] = (counts[day] || 0) + 1; };
  records.forEach((record) => {
    add(record.startDate); add(record.endDate);
    Object.keys(record.logs || {}).forEach((day) => { if (hasMemo(record, day)) add(day); });
  });
  communityDays.forEach(add);
  return counts;
}
export function streakStats(counts, today = new Date()) {
  const days = Object.keys(counts).filter((day) => counts[day] > 0 && dateFromKey(day) && day <= dateKey(today)).sort();
  let longest = 0, run = 0, previous = null;
  for (const day of days) {
    const date = dateFromKey(day), yesterday = new Date(date); yesterday.setDate(date.getDate() - 1);
    run = previous === dateKey(yesterday) ? run + 1 : 1; longest = Math.max(longest, run); previous = day;
  }
  let cursor = new Date(today.getFullYear(), today.getMonth(), today.getDate()), current = 0;
  if (!counts[dateKey(cursor)]) cursor.setDate(cursor.getDate() - 1);
  while (counts[dateKey(cursor)]) { current++; cursor.setDate(cursor.getDate() - 1); }
  return { current, longest, activeDays: days.length };
}
export function heatmapDays(today, weeks) {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  start.setDate(start.getDate() - start.getDay() - (weeks - 1) * 7);
  return Array.from({ length: weeks * 7 }, (_, i) => { const date = new Date(start); date.setDate(start.getDate() + i); return date; });
}
