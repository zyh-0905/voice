import {it,expect} from "vitest";import fs from "node:fs";it("defines semantic tokens",()=>{const css=fs.readFileSync("src/styles/tokens.css","utf8");expect(css).toContain("--vl-color-primary")})
