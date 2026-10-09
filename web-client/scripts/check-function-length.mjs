import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const SUPPORTED = new Set([".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"]);

/** 检查源码中超过阈值的具名或匿名函数；返回文件、行号、名称和有效行数。 */
export function inspectSource(file, source, limit = 50) {
  const kind = file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, kind);
  const violations = [];
  visitFunctions(sourceFile, sourceFile, source, limit, violations);
  return violations;
}

function visitFunctions(node, sourceFile, source, limit, violations) {
  if (isFunctionWithBody(node)) {
    const lines = countEffectiveLines(source.slice(node.body.pos, node.body.end));
    if (lines > limit) {
      const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      violations.push({ file: sourceFile.fileName, line: position.line + 1, lines, name: functionName(node) });
    }
  }
  ts.forEachChild(node, (child) => visitFunctions(child, sourceFile, source, limit, violations));
}

function isFunctionWithBody(node) {
  return (ts.isFunctionDeclaration(node)
    || ts.isFunctionExpression(node)
    || ts.isArrowFunction(node)
    || ts.isMethodDeclaration(node)
    || ts.isConstructorDeclaration(node)
    || ts.isGetAccessorDeclaration(node)
    || ts.isSetAccessorDeclaration(node)) && Boolean(node.body);
}

function functionName(node) {
  if (node.name?.getText) return node.name.getText();
  if (ts.isArrowFunction(node) && ts.isVariableDeclaration(node.parent)) return node.parent.name.getText();
  return "<anonymous>";
}

function countEffectiveLines(source) {
  let inBlock = false;
  let count = 0;
  for (const line of source.split(/\r?\n/)) {
    const result = stripComments(line, inBlock);
    inBlock = result.inBlock;
    if (result.code.trim() && !/^[{}();]+$/.test(result.code.trim())) count += 1;
  }
  return count;
}

function stripComments(line, startsInBlock) {
  let code = "";
  let inBlock = startsInBlock;
  for (let index = 0; index < line.length; index += 1) {
    if (inBlock && line.slice(index, index + 2) === "*/") { inBlock = false; index += 1; continue; }
    if (inBlock) continue;
    if (line.slice(index, index + 2) === "/*") { inBlock = true; index += 1; continue; }
    if (line.slice(index, index + 2) === "//") break;
    code += line[index];
  }
  return { code, inBlock };
}

function collectFiles(target) {
  if (!statSync(target).isDirectory()) return shouldScan(target) ? [target] : [];
  return readdirSync(target, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === "node_modules" || entry.name === "dist") return [];
    return collectFiles(path.join(target, entry.name));
  });
}

function shouldScan(file) {
  const normalized = file.replaceAll("\\", "/");
  return SUPPORTED.has(path.extname(file))
    && !normalized.endsWith("/src/api/schema.ts")
    && !normalized.endsWith(".d.ts");
}

function main() {
  const scriptDir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
  const defaults = [path.resolve(scriptDir, "..", "src")];
  const targets = (process.argv.slice(2).length ? process.argv.slice(2) : defaults).map((item) => path.resolve(item));
  const files = targets.flatMap(collectFiles);
  const violations = files.flatMap((file) => inspectSource(file, readFileSync(file, "utf8")));
  if (violations.length) {
    violations.forEach((item) => console.error(`${item.file}:${item.line} ${item.name} ${item.lines} effective lines`));
    process.exitCode = 1;
  } else {
    console.log(`Checked ${files.length} source files; 0 functions over 50 effective lines.`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
