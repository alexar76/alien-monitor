import { describe, expect, it } from "vitest";
import { sensorMatchesQuery, sensorSearchHaystack } from "../lib/sensorSearch";

describe("sensorSearch", () => {
  it("builds a lowercase haystack from mixed parts", () => {
    expect(sensorSearchHaystack("usgs-river-01", "River", null, "LIVE", undefined)).toBe(
      "usgs-river-01 river live",
    );
  });

  it("empty query matches everything", () => {
    expect(sensorMatchesQuery("usgs-river-01 river", "")).toBe(true);
    expect(sensorMatchesQuery("usgs-river-01 river", "  ")).toBe(true);
  });

  it("matches id / site / layer tokens (AND)", () => {
    const h = sensorSearchHaystack("usgs-river-01", "Mississippi", "river", "live");
    expect(sensorMatchesQuery(h, "usgs")).toBe(true);
    expect(sensorMatchesQuery(h, "river live")).toBe(true);
    expect(sensorMatchesQuery(h, "miss")).toBe(true);
    expect(sensorMatchesQuery(h, "usgs tide")).toBe(false);
  });
});
