import { expect, test } from "vitest";

// Temporary test to verify CI blocks auto-merge on failure.
// This file will be removed after verification.
test("CI failure simulation", () => {
  expect(true).toBe(false);
});
