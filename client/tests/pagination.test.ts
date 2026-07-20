import { describe, expect, it } from "vitest";
import { clampPage, paginate } from "../src/pagination";

describe("pagination", () => {
  it("does not require controls for exactly one page", () => {
    const result = paginate(Array.from({ length: 10 }, (_, index) => index), 1);
    expect(result.hasPagination).toBe(false);
    expect(result.items).toHaveLength(10);
  });

  it("paginates above ten results", () => {
    const result = paginate(Array.from({ length: 11 }, (_, index) => index), 2);
    expect(result.hasPagination).toBe(true);
    expect(result.items).toEqual([10]);
  });

  it("clamps pages into range", () => {
    expect(clampPage(99, 20)).toBe(2);
    expect(clampPage(-1, 20)).toBe(1);
  });
});
