import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import openapiTS, { astToString } from "openapi-typescript";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const clientRoot = path.resolve(scriptDir, "..");
const repositoryRoot = path.resolve(clientRoot, "..");
const schemaPath = path.join(clientRoot, "src", "api", "openapi.json");
const typesPath = path.join(clientRoot, "src", "api", "schema.ts");
const defaultPython = process.platform === "win32"
  ? path.join(repositoryRoot, ".venv", "Scripts", "python.exe")
  : path.join(repositoryRoot, ".venv", "bin", "python");

execFileSync(process.env.M5_PYTHON ?? defaultPython, [
  path.join(scriptDir, "export_openapi.py"),
  schemaPath,
], { cwd: repositoryRoot, stdio: "inherit" });

const ast = await openapiTS(pathToFileURL(schemaPath));
writeFileSync(typesPath, astToString(ast), "utf8");
