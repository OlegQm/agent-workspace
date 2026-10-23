import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, symlink, readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { checkDocumentation } from '../check_docs.mjs';

const sections = ['Purpose', 'Responsibilities', 'Entry Points', 'Dependencies and Boundaries', 'Tests', 'Related Documentation'];
const moduleDoc = sections.map((title) => `## ${title}\n\nRelevant module information.\n`).join('\n');

async function fixture(t, contents) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'mesh-docs-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const [file, content] of Object.entries(contents)) {
    await mkdir(path.dirname(path.join(root, file)), { recursive: true });
    await writeFile(path.join(root, file), content);
  }
  return { root, files: Object.keys(contents) };
}

test('reports a new backend feature without a README', async (t) => {
  const { root, files } = await fixture(t, {
    'service/backend/README.md': moduleDoc,
    'service/backend/src/features/new_feature/service.py': '# fixture',
  });
  assert.deepEqual(await checkDocumentation(root, files), [
    'service/backend/src/features/new_feature/README.md: missing module README',
  ]);
});

for (const [module, source] of [
  ['service/tool-gateway/src/tool_gateway/integrations/new_source', 'client.py'],
  ['service/tool-gateway/src/tool_gateway/integrations/payments/new_payment', 'client.py'],
  ['service/frontend/src/components/new_group', 'Panel.vue'],
  ['service/frontend/src/features/new_feature', 'state.ts'],
  ['service/backend/src/infrastructure/database', 'models.py'],
  ['service/tool-gateway/src/tool_gateway/infrastructure/new_transport', 'client.py'],
  ['infra/sandbox', 'spec.yaml'],
]) {
  test(`requires documentation at ${module}`, async (t) => {
    const { root, files } = await fixture(t, { [`${module}/${source}`]: 'fixture' });
    assert.ok((await checkDocumentation(root, files)).includes(`${module}/README.md: missing module README`));
  });
}

test('does not require README files in every layer, test package, or empty package', async (t) => {
  const { root, files } = await fixture(t, {
    'service/backend/README.md': moduleDoc,
    'service/backend/src/features/chat/README.md': moduleDoc,
    'service/backend/src/features/chat/application/service.py': '# fixture',
    'service/backend/src/features/empty/__init__.py': '',
    'service/backend/tests/features/new_test/test_service.py': '# fixture',
  });
  assert.deepEqual(await checkDocumentation(root, files), []);
});

for (const [label, replacement] of [
  ['missing section', ''],
  ['empty section', '## Purpose\n\n'],
  ['comment-only section', '## Purpose\n\n<!-- explain later -->\n'],
  ['heading-only section', '## Purpose\n\n### Overview\n\n'],
  ['incorrect heading level', '### Purpose\n\nDetails.\n'],
]) {
  test(`rejects a ${label}`, async (t) => {
    const { root, files } = await fixture(t, {
      'service/code-sync/src/daemon.py': '# fixture',
      'service/code-sync/README.md': moduleDoc.replace('## Purpose\n\nRelevant module information.\n', replacement),
    });
    assert.deepEqual(await checkDocumentation(root, files), [
      'service/code-sync/README.md: missing or empty section "Purpose"',
    ]);
  });
}

test('accepts complete module sections including nested headings and code', async (t) => {
  const { root, files } = await fixture(t, {
    'service/code-sync/src/daemon.py': '# fixture',
    'service/code-sync/README.md': moduleDoc.replace('Relevant module information.', '### Overview\n\n```text\nDetails\n```'),
  });
  assert.deepEqual(await checkDocumentation(root, files), []);
});

for (const [label, content] of [
  ['link', '[missing](missing.md)'],
  ['image', '![diagram](missing.png)'],
  ['nested image', '[![diagram](missing.png)](README.md)'],
  ['reference link', '[page][ref]\n\n[ref]: missing.md'],
  ['reference image', '![diagram][ref]\n\n[ref]: missing.png'],
  ['fragment on missing file', '[section](missing.md#details)'],
]) {
  test(`reports a broken ${label}`, async (t) => {
    const { root, files } = await fixture(t, { 'README.md': content });
    const issues = await checkDocumentation(root, files);
    assert.equal(issues.length, 1);
    assert.match(issues[0], /^README.md: missing local target "missing\.(md|png)"$/);
  });
}

test('resolves relative, root-relative, encoded, nested and reference targets', async (t) => {
  const { root, files } = await fixture(t, {
    'docs/page.md': '[home](../README.md) [root](/README.md#absent) [encoded](my%20file.md?raw=1#absent)\n\n[![diagram][img]][home]\n\n[img]: diagram.png\n[home]: ../README.md',
    'docs/my file.md': '# Content', 'docs/diagram.png': 'fixture', 'README.md': '# Home',
  });
  assert.deepEqual(await checkDocumentation(root, files), []);
});

test('does not check anchors, external URLs, or Markdown inside code', async (t) => {
  const { root, files } = await fixture(t, {
    'README.md': '[self](#missing) [web](https://unreachable.invalid/x) [mail](mailto:nobody@example.invalid) [protocol relative](//unreachable.invalid/x)\n\n`[code](missing.md)`\n\n```md\n![code](missing.png)\n```',
  });
  assert.deepEqual(await checkDocumentation(root, files), []);
});

test('excludes runtime directories even if their contents are tracked', async (t) => {
  const { root, files } = await fixture(t, {
    'README.md': '# Good',
    'data/runtime/README.md': '[broken](absent)',
    'service/frontend/node_modules/dependency/README.md': '[broken](absent)',
    '.playwright-mcp/page.md': '[broken](absent)',
    'tmp/private.md': '[broken](absent)',
  });
  assert.deepEqual(await checkDocumentation(root, files), []);
});

test('rejects targets outside the repository, including symlink targets', async (t) => {
  const { root, files } = await fixture(t, { 'README.md': '[outside](../) [alias](alias)' });
  await symlink(os.tmpdir(), path.join(root, 'alias'));
  assert.deepEqual(await checkDocumentation(root, files), [
    'README.md: local target outside repository "../"',
    'README.md: local target outside repository "alias"',
  ]);
});

test('reports malformed percent encoding without crashing', async (t) => {
  const { root, files } = await fixture(t, { 'README.md': '[broken](bad%XX.md)' });
  assert.equal((await checkDocumentation(root, files)).length, 1);
});

test('CLI checks untracked documentation, respects Git ignores, and exits nonzero on errors', async (t) => {
  const { root } = await fixture(t, {
    '.gitignore': 'ignored/\n', 'ignored/private.md': '[broken](absent)',
    'README.md': '[broken](absent.md)',
  });
  execFileSync('git', ['init', '-q', root]);
  const script = fileURLToPath(new URL('../check_docs.mjs', import.meta.url));
  let failure;
  try {
    execFileSync(process.execPath, [script, root], { encoding: 'utf8', stdio: 'pipe' });
  } catch (error) {
    failure = error;
  }
  assert.equal(failure?.status, 1);
  assert.match(failure.stderr, /README.md: missing local target "absent.md"/);
  assert.doesNotMatch(failure.stderr, /private.md/);
  await writeFile(path.join(root, 'README.md'), '# Good');
  assert.match(execFileSync(process.execPath, [script, root], { encoding: 'utf8' }), /Documentation check passed/);
});

test('CLI checks a source archive without Git metadata', async (t) => {
  const { root } = await fixture(t, {
    'README.md': '# Public archive',
    'service/code-sync/src/daemon.py': '# fixture',
    'service/code-sync/README.md': moduleDoc,
  });
  const script = fileURLToPath(new URL('../check_docs.mjs', import.meta.url));
  const output = execFileSync(process.execPath, [script, root], { encoding: 'utf8' });
  assert.match(output, /Documentation check passed/);
});

test('does not read Markdown symlinks outside the repository', async (t) => {
  const { root, files } = await fixture(t, { 'README.md': '# Good' });
  await symlink(path.join(root, '..', 'unavailable.md'), path.join(root, 'alias.md'));
  assert.deepEqual(await checkDocumentation(root, [...files, 'alias.md']), [
    'alias.md: unreadable or unsafe documentation file',
  ]);
});

test('reports a missing tracked documentation file instead of aborting the check', async (t) => {
  const { root } = await fixture(t, {});
  assert.deepEqual(await checkDocumentation(root, ['README.md']), [
    'README.md: unreadable or unsafe documentation file',
  ]);
});

test('Task, Make, workspace lint and CI expose the same documentation gate', async () => {
  const repository = new URL('../../', import.meta.url);
  const task = await readFile(new URL('Taskfile.yml', repository), 'utf8');
  const make = await readFile(new URL('Makefile', repository), 'utf8');
  const workspace = await readFile(new URL('scripts/workspace.sh', repository), 'utf8');
  const ci = await readFile(new URL('.github/workflows/ci.yml', repository), 'utf8');
  assert.match(task, /docs:check:\s+cmds: \['\.\/scripts\/workspace\.sh docs-check'\]/);
  assert.match(make, /docs-check:\n\s+@\.\/scripts\/workspace\.sh docs-check/);
  assert.match(workspace, /docs_check\(\) \{\s+node --test .*check_docs\.test\.mjs.*\s+node .*check_docs\.mjs/s);
  assert.match(workspace, /lint\(\) \{\s+docs_check/);
  assert.match(workspace, /docs-check\|docs:check\) docs_check/);
  assert.match(ci, /Install frontend dependencies[\s\S]*Run documentation, lint, and type checks\s+run: \.\/scripts\/workspace\.sh lint/);
});
