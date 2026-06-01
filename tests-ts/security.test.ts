import { describe, expect, it } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { sanitizeForLog } from "../src/backend/logging/logger";
import { safeDisplayText, validateGoogleFolderLink } from "../src/renderer/utils/googleLinks";
import {
  validateDuplicateResetConfirmation,
  validateExcelFilePaths,
  validatePostingPayload,
  validateSheetId
} from "../src/backend/security/validation";

describe("security wrappers", () => {
  it("redacts secrets before logging", () => {
    expect(
      sanitizeForLog({
        access_token: "secret",
        nested: { client_secret: "secret", ok: "visible" }
      })
    ).toEqual({
      access_token: "[REDACTED]",
      nested: { client_secret: "[REDACTED]", ok: "visible" }
    });
  });

  it("redacts secret-looking text before display or logs", () => {
    expect(sanitizeForLog("Authorization: Bearer abc.def-123")).toBe("Authorization: [REDACTED]");
    expect(safeDisplayText('{"access_token":"ya29.secret-token"}')).toContain("[REDACTED]");
    expect(safeDisplayText("-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----")).toBe("[REDACTED]");
  });

  it("requires https Google folder links", () => {
    expect(validateGoogleFolderLink("http://drive.google.com/drive/folders/abc123").ok).toBe(false);
    expect(validateGoogleFolderLink("https://drive.google.com/drive/folders/abc123").ok).toBe(true);
  });

  it("validates Google Sheet IDs", () => {
    expect(validateSheetId("abc12345678901234567890")).toBe("abc12345678901234567890");
    expect(() => validateSheetId("../bad")).toThrow("Invalid Google Sheet ID");
  });

  it("rejects malformed IPC posting payloads", () => {
    expect(() => validatePostingPayload({})).toThrow("SIMSOFT Excel file is required");
    expect(() =>
      validatePostingPayload({
        filePath: "missing.xlsx",
        folderUrl: "https://drive.google.com/drive/folders/abc123",
        branchId: "../bad",
        branchIndex: {}
      })
    ).toThrow();
  });

  it("validates multi-file upload payloads with count and duplicate guards", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "simsoft-security-"));
    const first = path.join(root, "one.xlsx");
    const second = path.join(root, "two.xlsm");
    fs.writeFileSync(first, "one");
    fs.writeFileSync(second, "two");

    expect(validateExcelFilePaths([first, second])).toHaveLength(2);
    expect(() => validateExcelFilePaths([first, first])).toThrow("Duplicate SIMSOFT Excel files are not allowed");
  });

  it("requires exact duplicate reset confirmation", () => {
    expect(validateDuplicateResetConfirmation("Reset Duplicate History")).toBe("Reset Duplicate History");
    expect(() => validateDuplicateResetConfirmation("reset")).toThrow("Reset confirmation is required");
  });
});
