import { describe, expect, it } from "vitest";

import { inspectSource } from "../../scripts/check-function-length.mjs";

describe("function length checker", () => {
  it("忽略空行和注释并检查箭头函数与方法", () => {
    const source = `
      const short = () => {
        // comment
        return 1;
      };
      class Demo {
        run() {
          /* comment */
          return 2;
        }
      }
    `;

    expect(inspectSource("sample.ts", source, 0).map((item) => item.name)).toEqual(["short", "run"]);
  });
});
