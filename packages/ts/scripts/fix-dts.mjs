// tsc keeps ".ts" specifiers in emitted .d.ts files (rewriteRelativeImportExtensions only rewrites the JS).
// Rewrite them to ".js" so the declarations resolve for consumers under NodeNext.
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const dist = resolve(dirname(fileURLToPath(import.meta.url)), "../dist");
let changed = 0;
for (const file of readdirSync(dist).filter((f) => f.endsWith(".d.ts"))) {
  const path = resolve(dist, file);
  const before = readFileSync(path, "utf8");
  const after = before.replace(/(from |import\()"(\.{1,2}\/[^"]+)\.ts"/g, '$1"$2.js"');
  if (after !== before) {
    writeFileSync(path, after);
    changed++;
  }
}
console.log(`fixed .ts specifiers in ${changed} declaration file(s)`);
