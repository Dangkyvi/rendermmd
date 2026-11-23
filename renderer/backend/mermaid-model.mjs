// Version-pinned model adapter: use Mermaid's grammar/FlowDB, never its DOM renderer.
import mermaid from 'mermaid';
import { detectType, matchFrontMatter } from 'mermaid/dist/chunks/mermaid.core/chunk-BG4553SI.mjs';
import { createFlowDiagram } from 'mermaid/dist/chunks/mermaid.core/chunk-QB3YPZ4I.mjs';
import { encodeEntities } from 'mermaid/dist/chunks/mermaid.core/chunk-6MUBBAK2.mjs';
import { sourceConfiguration, plainLabel, SourceError } from './theme-source.mjs';

export async function parseFlowchart(source, requested = sourceConfiguration(source)) {
  // Keep strict config. Replace only this FlowDB instance's text hooks with our
  // supported plain-text/br policy; DOMPurify and Mermaid's SVG renderer are not called.
  mermaid.initialize({
    ...requested.config, startOnLoad: false, securityLevel: 'strict',
    fontFamily: requested.config.fontFamily ?? 'Noto Sans',
    fontSize: requested.config.fontSize ?? 15,
    themeVariables: {fontFamily: 'Noto Sans', fontSize: '15px', ...requested.config.themeVariables},
  });
  const config = mermaid.mermaidAPI.getConfig();
  const normalized = source.replace(/\r\n?/g, '\n');
  const frontMatter = matchFrontMatter(normalized);
  // These are the pinned public API's cleanup/encoding operations; directives
  // are already rejected by sourceConfiguration. Keep original line mapping there.
  const body = normalized.slice(frontMatter?.length ?? 0)
    .replace(/^\s*%%(?!{)[^\n]+\n?/gm, '').trimStart();
  let type;
  try { type = detectType(body, config); }
  catch (error) {
    if (error.name === 'UnknownDiagramError') throw new SourceError(error.message, 'unsupported');
    throw error;
  }
  if (!['flowchart', 'flowchart-v2'].includes(type)) {
    throw new SourceError(`Loại diagram chưa được hỗ trợ: ${type}`, 'unsupported');
  }
  const definition = createFlowDiagram();
  const db = definition.db;
  db.clear();
  const supportedText = (value) => {
    const text = String(value ?? '');
    plainLabel(text); // validate supported markup; retain encoded model text for the final text pass
    return text;
  };
  db.sanitizeText = supportedText;
  // Count actual expanded edges at the model boundary; no error-message matching.
  const addSingleLink = db.addSingleLink.bind(db);
  db.addSingleLink = (...args) => {
    if (db.getEdges().length >= (db.config.maxEdges ?? 500)) {
      throw new SourceError(`Edge limit exceeded: tối đa ${db.config.maxEdges ?? 500} edges.`, 'limit');
    }
    return addSingleLink(...args);
  };
  let title = '', accTitle = '', accDescription = '';
  db.setDiagramTitle = (value) => { title = supportedText(value); };
  db.getDiagramTitle = () => title;
  db.setAccTitle = (value) => { accTitle = supportedText(value).trimStart(); };
  db.getAccTitle = () => accTitle;
  db.setAccDescription = (value) => { accDescription = supportedText(value).replace(/\n\s+/g, '\n'); };
  db.getAccDescription = () => accDescription;
  definition.parser.parser.yy = db;
  definition.init(config);
  if (requested.title) db.setDiagramTitle(requested.title);
  // Preserve HTML numeric references through Mermaid's hash-entity encoder;
  // never decode delimiters into source before grammar parsing.
  const encodedBody = body.replace(/&#(x[\da-f]+|\d+);/gi, (_, value) =>
    `#${Number.parseInt(value.replace(/^x/i, ''), /^x/i.test(value) ? 16 : 10)};`);
  try { await definition.parser.parse(encodeEntities(encodedBody) + '\n'); }
  catch (error) {
    if (!(error instanceof SourceError) &&
        (Number.isInteger(error.hash?.line) || Number.isInteger(error.hash?.loc?.first_line))) {
      error.kind = 'syntax';
    }
    throw error;
  }
  return {diagram: {type, db}, config, requested};
}
