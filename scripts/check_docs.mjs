import { readFile, stat, realpath } from 'node:fs/promises';
import { readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(new URL('../service/frontend/package.json', import.meta.url));
const MarkdownIt = require('markdown-it');
const markdown = new MarkdownIt();
const requiredSections = ['Purpose', 'Responsibilities', 'Entry Points', 'Dependencies and Boundaries', 'Tests', 'Related Documentation'];
const excludedDirectories = new Set([
  '.git', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache', '.ruff_cache',
  '.mypy_cache', '.import_linter_cache', '.uv-cache', '.cache', '.tmp', '.task', '.trunk',
  '.playwright', '.playwright-mcp', '.playwright-cli', '.auth', '.deploy', 'data', 'secrets',
  'tmp', 'temp', 'build', 'dist', 'coverage', 'htmlcov', 'test-results', 'playwright-report', 'blob-report',
]);

function included(file) {
  return !file.split('/').some((part) => excludedDirectories.has(part));
}

function inside(root, target) {
  const relative = path.relative(root, target);
  return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

export function repositoryFiles(root) {
  try {
    return [...new Set(execFileSync('git', ['-C', root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], {
      encoding: 'utf8', maxBuffer: 16 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).split('\0').filter(Boolean))].filter(included).sort();
  } catch {
    const files = [];
    const visit = (directory = '') => {
      for (const entry of readdirSync(path.join(root, directory), { withFileTypes: true })) {
        const file = path.posix.join(directory, entry.name);
        if (!included(file) || entry.isSymbolicLink()) continue;
        if (entry.isDirectory()) visit(file);
        else if (entry.isFile()) files.push(file);
      }
    };
    visit();
    return files.sort();
  }
}

const fixedModules = [
  'service/backend', 'service/tool-gateway', 'service/frontend', 'service/code-sync',
  'service/backend/src/bootstrap', 'service/backend/src/entrypoints/cli',
  'service/backend/src/infrastructure', 'service/backend/src/infrastructure/database',
  'service/backend/src/features/chat/infrastructure/hermes',
  'service/backend/src/features/workspace/infrastructure/previews',
  'service/backend/src/features/workspace/infrastructure/confidentiality',
  'service/frontend/src/composables', 'service/frontend/src/lib',
  'infra', 'infra/orchestration', 'infra/nginx', 'infra/sandbox',
  'config', 'config/agents', 'config/agents/prompts', 'scripts',
  '.github/workflows', '.github/workflows/deploy_scripts',
  '.github/workflows/deploy_scripts/infra', '.github/workflows/deploy_scripts/services',
  'service/tool-gateway/src/tool_gateway/bootstrap',
  'service/tool-gateway/src/tool_gateway/entrypoints/mcp',
];
const dynamicModules = [
  /^(service\/backend\/src\/features\/[^/]+)\//,
  /^(service\/backend\/src\/features\/metabase_planning\/infrastructure\/[^/]+)\//,
  /^(service\/tool-gateway\/src\/tool_gateway\/infrastructure\/[^/]+)\//,
  /^(service\/tool-gateway\/src\/tool_gateway\/integrations\/[^/]+)\//,
  /^(service\/tool-gateway\/src\/tool_gateway\/integrations\/payments\/[^/]+)\//,
  /^(service\/frontend\/src\/(?:components|features)\/[^/]+)\//,
];

export function requiredModuleDocs(files) {
  const modules = new Set();
  for (const file of files) {
    if (file.endsWith('/README.md') || file.endsWith('/__init__.py') || /\/tests?\//.test(file)) continue;
    for (const module of fixedModules) {
      if (file.startsWith(`${module}/`)) modules.add(module);
    }
    for (const pattern of dynamicModules) {
      const match = file.match(pattern);
      if (match) modules.add(match[1]);
    }
  }
  return [...modules].sort().map((module) => `${module}/README.md`);
}

export async function checkDocumentation(root, files) {
  root = await realpath(root);
  files = files.filter(included);
  const issues = [];
  const documents = new Map();
  for (const file of files.filter((file) => file.endsWith('.md')).sort()) {
    try {
      const absolute = path.resolve(root, file);
      if (!inside(root, absolute) || !inside(root, await realpath(absolute))) throw new Error('Unsafe path');
      documents.set(file, markdown.parse(await readFile(absolute, 'utf8'), {}));
    } catch {
      issues.push(`${file}: unreadable or unsafe documentation file`);
    }
  }
  for (const file of requiredModuleDocs(files)) {
    if (!files.includes(file)) {
      issues.push(`${file}: missing module README`);
      continue;
    }
    const tokens = documents.get(file);
    if (!tokens) continue;
    const sections = new Map();
    let current;
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index];
      if (token.type === 'heading_open') {
        if (token.tag === 'h1') current = undefined;
        if (token.tag === 'h2') {
          current = tokens[index + 1].content;
          sections.set(current, false);
        }
        index += 2;
      } else if (current && ['inline', 'fence', 'code_block'].includes(token.type)) {
        if (token.content.replace(/<!--[\s\S]*?-->/g, '').trim()) sections.set(current, true);
      }
    }
    for (const title of requiredSections) {
      if (!sections.get(title)) issues.push(`${file}: missing or empty section "${title}"`);
    }
  }
  for (const [file, tokens] of documents) {
    for (const href of linkTargets(tokens)) {
      if (!href || href.startsWith('#') || href.startsWith('//') || /^[a-z][a-z\d+.-]*:/i.test(href)) continue;
      const target = decodeURIComponent(href.split(/[?#]/, 1)[0]);
      const absolute = target.startsWith('/')
        ? path.join(root, target.slice(1))
        : path.resolve(root, path.dirname(file), target);
      try {
        if (!inside(root, absolute) || !inside(root, await realpath(absolute))) {
          issues.push(`${file}: local target outside repository "${target}"`);
          continue;
        }
        await stat(absolute);
      } catch {
        issues.push(`${file}: missing local target "${target}"`);
      }
    }
  }
  return issues;
}

function* linkTargets(tokens) {
  for (const token of tokens) {
    if (token.type === 'link_open') yield token.attrGet('href');
    if (token.type === 'image') yield token.attrGet('src');
    if (token.children) yield* linkTargets(token.children);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const root = path.resolve(process.argv[2] ?? fileURLToPath(new URL('..', import.meta.url)));
    const files = repositoryFiles(root);
    const issues = await checkDocumentation(root, files);
    if (issues.length) {
      console.error(issues.join('\n'));
      process.exitCode = 1;
    } else {
      console.log(`Documentation check passed: ${files.filter((file) => file.endsWith('.md')).length} Markdown files, ${requiredModuleDocs(files).length} module READMEs.`);
    }
  } catch {
    console.error('Documentation check could not run. Check Git access, readable files, and frontend npm dependencies.');
    process.exitCode = 1;
  }
}
