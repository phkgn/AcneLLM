import assert from "node:assert/strict";
import test from "node:test";
import { lineClass } from "../lib/log-lines.ts";

test("lineClass highlights full-evaluation markers by terminal status", () => {
  assert.match(
    lineClass("[runall] step=4/7 id=answer_generation status=start"),
    /text-clay/,
  );
  assert.match(
    lineClass("[runall] step=4/7 id=answer_generation status=ok duration=1.0s"),
    /#cde76c/,
  );
  assert.match(
    lineClass("[runall] step=4/7 id=answer_generation status=fail duration=1.0s"),
    /#ff9278/,
  );
});
