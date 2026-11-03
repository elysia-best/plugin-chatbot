import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const webuiDirectory = path.resolve(scriptDirectory, '..');
const repositoryDirectory = path.resolve(webuiDirectory, '..');
const sourceDirectory = path.join(webuiDirectory, 'dist');
const targetDirectory = path.join(
  repositoryDirectory,
  'plugin_chatbot',
  'plugins',
  'webui',
);

if (!fs.existsSync(path.join(sourceDirectory, 'index.html'))) {
  throw new Error(`Vite output is missing: ${sourceDirectory}`);
}

fs.rmSync(targetDirectory, { recursive: true, force: true });
fs.cpSync(sourceDirectory, targetDirectory, { recursive: true });
console.log(`Copied WebUI static files to ${targetDirectory}`);
