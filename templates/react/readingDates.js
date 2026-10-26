import { useEffect, useState } from "react";
export function dateKey(value) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
export function dateFromKey(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return dateKey(date) === value ? date : null;
}
export function weekDays(today) {
  const first = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  first.setDate(first.getDate() - (first.getDay() + 6) % 7);
  return Array.from({ length: 7 }, (_, i) => {
    const day = new Date(first); day.setDate(first.getDate() + i); return day;
  });
}
export function hasMemo(record, day) {
  return typeof record.logs?.[day] === "string" && !!record.logs[day].trim();
}
export function useLocalDate() {
  const [current, setCurrent] = useState(() => new Date());
  function refresh() {
    const next = new Date();
    setCurrent((previous) => dateKey(previous) === dateKey(next) ? previous : next);
  }
  useEffect(() => {
    const timer = window.setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", refresh);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, []);
  return [current, refresh];
}
