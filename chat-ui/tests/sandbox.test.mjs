import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { entriesFromStored } from '../src/lib/transcript.ts';

const source = readFileSync(new URL('../public/sandbox.js', import.meta.url), 'utf8');
test('sandbox forwards only its parent and opaque inner app', () => {
  const parentMessages = [], innerMessages = [];
  const parent = { postMessage: (...args) => parentMessages.push(args) };
  const innerWindow = { postMessage: (...args) => innerMessages.push(args) };
  const attributes = {};
  const inner = { contentWindow: innerWindow, style: {}, setAttribute: (key, value) => attributes[key] = value };
  let listener;
  const context = { URL, location: { origin: 'http://localhost:3004', hostname: 'localhost', port: '3004' },
    window: { parent, addEventListener: (_, callback) => listener = callback },
    document: { referrer: 'http://127.0.0.1:3004/', createElement: () => inner, body: { appendChild() {} } } };
  vm.runInNewContext(source, context);
  assert.equal(attributes.sandbox, 'allow-scripts');
  const data = { jsonrpc: '2.0', method: 'ui/notifications/sandbox-resource-ready', params: { html: '<p>app</p>' } };
  listener({ source: parent, origin: 'http://evil.example', data });
  assert.equal(inner.srcdoc, undefined);
  listener({ source: parent, origin: 'http://127.0.0.1:3004', data });
  assert.equal(inner.srcdoc, '<p>app</p>');
  listener({ source: {}, origin: 'null', data: { jsonrpc: '2.0', method: 'tools/call' } });
  assert.equal(parentMessages.length, 1);
  listener({ source: innerWindow, origin: 'null', data: { jsonrpc: '2.0', method: 'tools/call' } });
  assert.equal(parentMessages.length, 2);
  listener({ source: innerWindow, origin: 'null', data });
  assert.equal(parentMessages.length, 2);
  assert.equal(parentMessages[1][1], 'http://127.0.0.1:3004');
});

test('history restores app snapshots without duplicate product cards and accepts legacy records', () => {
  const app = { id: 'bound', server: 'shop', tool: 'open_storefront', uri: 'ui://store', input: {} };
  const messages = [
    { id: 1, role: 'user', content: 'Hello' },
    { id: 2, role: 'tool', tool_name: 'search_products', payload: { groups: [{ products: [{ id: 3 }] }] } },
    { id: 3, role: 'tool', tool_name: 'shop__open_storefront', payload: { _mcp_app: app, groups: [{ products: [{ id: 4 }] }] } },
    { id: 4, role: 'tool', tool_name: 'ops__get_dashboard', payload: { _ops_request: { id: 'pending' } } },
  ];
  const entries = entriesFromStored(messages);
  assert.equal(entries.filter(entry => entry.kind === 'products').length, 1);
  const view = entries.find(entry => entry.kind === 'app');
  assert.equal(view.restored, true);
  assert.equal(view.descriptor, app);
  assert.equal(entries.find(entry => entry.kind === 'identity')?.id, 'pending');
});
