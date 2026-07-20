import { PAGE_SIZE } from "./constants";

export interface PaginationState<T> {
  page: number;
  pageCount: number;
  totalItems: number;
  items: T[];
  hasPagination: boolean;
}

export function clampPage(page: number, totalItems: number, pageSize = PAGE_SIZE): number {
  const pageCount = Math.max(1, Math.ceil(totalItems / pageSize));
  if (!Number.isFinite(page)) {
    return 1;
  }
  return Math.min(Math.max(1, Math.trunc(page)), pageCount);
}

export function paginate<T>(items: T[], page: number, pageSize = PAGE_SIZE): PaginationState<T> {
  const safePage = clampPage(page, items.length, pageSize);
  const start = (safePage - 1) * pageSize;
  return {
    page: safePage,
    pageCount: Math.max(1, Math.ceil(items.length / pageSize)),
    totalItems: items.length,
    items: items.slice(start, start + pageSize),
    hasPagination: items.length > pageSize
  };
}
