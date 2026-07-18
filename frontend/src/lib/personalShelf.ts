import type { PersonalShelfItem } from '../domain/types';

const PERSONAL_SHELF_KEY = 'qfin.reports-watchlist.v1';
const MAX_PERSONAL_SHELF_ITEMS = 80;

export function readPersonalShelf(): PersonalShelfItem[] {
  try {
    const raw = window.localStorage.getItem(PERSONAL_SHELF_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as PersonalShelfItem[]) : [];
  } catch {
    return [];
  }
}

export function writePersonalShelf(items: PersonalShelfItem[]): void {
  try {
    window.localStorage.setItem(
      PERSONAL_SHELF_KEY,
      JSON.stringify(items.slice(0, MAX_PERSONAL_SHELF_ITEMS))
    );
  } catch {
    // Private shelf persistence should never interrupt the active QFin session.
  }
}
