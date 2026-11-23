import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { parseFlowchart } from '/app/mermaid-model.mjs';
import { plainLabel, color } from '/app/theme-source.mjs';
assert.equal(typeof globalThis.window, 'undefined');
assert.equal(typeof globalThis.document, 'undefined');
assert.equal(existsSync('/app/node_modules/jsdom'), false);
const {diagram, config} = await parseFlowchart('---\ntitle: "Tiếng Việt #amp; AIZ"\n---\nflowchart TB\nA["Dòng 1<br/>#quot;Dòng 2#quot;"] --> B\naccTitle: Sơ đồ kiểm thử\naccDescr: Mô tả\n');
assert.equal(config.securityLevel, 'strict');
assert.equal(plainLabel(diagram.db.getDiagramTitle()), 'Tiếng Việt & AIZ');
assert.equal(plainLabel(diagram.db.getVertices().get('A').text), 'Dòng 1\n"Dòng 2"');
assert.equal(diagram.db.getAccTitle(), 'Sơ đồ kiểm thử');
assert.equal(plainLabel('#amp;lt;script#amp;gt;'), '&lt;script&gt;');
assert.equal(plainLabel('&#x1f600; &copy; #273;'), '😀 © đ');
assert.equal(plainLabel('&lt;script&gt;'), '<script>'); // plain glyph text, never reparsed as SVG/HTML
for (const bad of ['<script>alert(1)</script>', '<img src="file:///etc/passwd">', '<br onclick="x()">']) {
  await assert.rejects(() => parseFlowchart(`flowchart TB\nA["${bad}"]\n`));
}
for (const bad of ['notacolor', '#abcde', '#abcdefg', 'url(file:///etc/passwd)', 'currentColor']) {
  assert.throws(() => color(bad));
}
for (const good of ['red', '#abc', '#abcd', '#abcdef', '#abcdef12', 'rgb(1, 2, 3)', 'rgba(1, 2, 3, 0.5)', 'hsl(120, 50%, 50%)']) {
  assert.equal(color(good), good);
}
assert.equal(typeof globalThis.window, 'undefined');
assert.equal(typeof globalThis.document, 'undefined');
console.log('PASS no-DOM: no jsdom/window/document; strict model adapter, title/accessibility, entities, markup and color policy');
