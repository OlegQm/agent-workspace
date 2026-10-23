import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';
import test from 'node:test';

const helper = new URL('../wait_for_backend.py', import.meta.url);

async function startServer(handler) {
  const server = createServer(handler);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return {
    server,
    url: `http://127.0.0.1:${server.address().port}/healthz`,
  };
}

function runHelper(url, timeout = '2') {
  return new Promise((resolve) => {
    const child = spawn('python3', [helper.pathname, '--url', url, '--timeout', timeout], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8').on('data', (chunk) => { stdout += chunk; });
    child.stderr.setEncoding('utf8').on('data', (chunk) => { stderr += chunk; });
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

test('waits through startup failures and succeeds when the backend becomes healthy', async (t) => {
  let requests = 0;
  const { server, url } = await startServer((_request, response) => {
    requests += 1;
    response.writeHead(requests < 3 ? 503 : 200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ status: 'ok' }));
  });
  t.after(() => server.close());

  const result = await runHelper(url);

  assert.equal(result.code, 0, result.stderr);
  assert.ok(requests >= 3);
  assert.match(result.stdout, /Backend health check passed/);
});

test('fails with a safe diagnostic when the backend does not become healthy in time', async (t) => {
  const { server, url } = await startServer((_request, response) => {
    response.writeHead(503);
    response.end('not ready');
  });
  t.after(() => server.close());

  const result = await runHelper(url, '0.3');

  assert.equal(result.code, 1);
  assert.match(result.stderr, /Backend health check failed before timeout/);
  assert.doesNotMatch(result.stderr, /not ready|127\.0\.0\.1/);
});

test('rejects a non-loopback URL without making a request', async () => {
  const result = await runHelper('https://example.invalid/healthz');

  assert.equal(result.code, 2);
  assert.match(result.stderr, /Backend health check configuration is invalid/);
  assert.doesNotMatch(result.stderr, /example\.invalid/);
});

test('does not follow redirects from the loopback health endpoint', async (t) => {
  let redirectedRequests = 0;
  const { server, url } = await startServer((request, response) => {
    if (request.url === '/healthz') {
      response.writeHead(302, { Location: '/redirect-target' });
      response.end();
      return;
    }
    redirectedRequests += 1;
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ status: 'ok' }));
  });
  t.after(() => server.close());

  const result = await runHelper(url, '0.3');

  assert.equal(result.code, 1);
  assert.equal(redirectedRequests, 0);
});
