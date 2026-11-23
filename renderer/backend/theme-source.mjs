// Adapter for the installed, pinned Mermaid 12.3.0 bundle. No new dependency.
import { createRequire } from 'node:module';
import { decodeHTML } from 'entities';
import { channel } from 'khroma';
import { matchFrontMatter } from 'mermaid/dist/chunks/mermaid.core/chunk-BG4553SI.mjs';
import { load, JSON_SCHEMA } from 'mermaid/dist/chunks/mermaid.core/chunk-HPSUCWAI.mjs';
import { decodeEntities, encodeEntities } from 'mermaid/dist/chunks/mermaid.core/chunk-6MUBBAK2.mjs';
const require = createRequire(import.meta.url);
if (require('mermaid/package.json').version !== '12.3.0') {
  throw new Error('Theme adapter cần Mermaid 12.3.0; kiểm tra lại internal API trước khi cập nhật.');
}
// Only explicit source validation failures carry this type. Unknown failures
// stay engine errors, even if their message mentions a style/font or parser.
export class SourceError extends Error {
  constructor(message, code = 'source_policy') {
    super(message);
    this.name = 'SourceError';
    this.kind = 'source';
    this.code = code;
  }
}
function object(value, context) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new SourceError(`${context}: cần mapping.`);
}
function keys(value, allowed, context) {
  object(value, context);
  for (const key of Object.keys(value)) if (!allowed.includes(key)) throw new SourceError(`${context}: thuộc tính chưa hỗ trợ/không an toàn: ${key}`);
}
export function color(value) {
  if (typeof value !== 'string' || !/^(?:#[\da-f]{3,8}|[a-z]+|(?:rgb|rgba|hsl|hsla)\([\d.%+\-,\s]+\))$/i.test(value)) {
    throw new SourceError(`Màu không an toàn hoặc chưa hỗ trợ: ${String(value)}`);
  }
  if (['inherit','initial','unset','revert','currentcolor'].includes(value.toLowerCase())) throw new SourceError(`Màu cần giá trị tuyệt đối: ${value}`);
  if (value === 'none') return value;
  if (value.startsWith('#') && !/^#(?:[\da-f]{3}|[\da-f]{4}|[\da-f]{6}|[\da-f]{8})$/i.test(value)) {
    throw new SourceError(`Màu không hợp lệ: ${value}`);
  }
  try { channel(value.toLowerCase(), 'r'); }
  catch { throw new SourceError(`Màu không hợp lệ: ${value}`); }
  return value;
}
export function fontSize(value) {
  if (typeof value !== 'number' && (typeof value !== 'string' || !/^\d+(?:\.\d+)?(?:px)?$/.test(value))) {
    throw new SourceError(`Cỡ chữ cần số hoặc px: ${String(value)}`);
  }
  const size = Number.parseFloat(value);
  if (!Number.isFinite(size) || size < 1 || size > 256) throw new SourceError('Cỡ chữ phải trong khoảng 1..256 px.');
  return size;
}
export function fontFamily(value) {
  if (typeof value !== 'string' || value.length > 256) throw new SourceError('fontFamily không hợp lệ.');
  // Font lists are names, not CSS. Quoted names are accepted, no URL/path/code.
  const names = value.split(',').map((item) => item.trim().replace(/^(['"])(.*)\1$/, '$2'));
  if (!names.length || names.some((name) => !/^[\p{L}\p{N} _-]+$/u.test(name))) {
    throw new SourceError(`fontFamily không an toàn: ${value}`);
  }
  return names.join(', ');
}
export function sourceConfiguration(source) {
  if (/<\s*(?:script|iframe|object|embed|img|svg|foreignObject)\b/i.test(source)) throw new SourceError('Nhãn HTML chủ động/tài nguyên ngoài không được phép.');
  for (const br of source.matchAll(/<br\b([^>]*)>/gi)) {
    if (!/^\s*\/?\s*$/.test(br[1])) throw new SourceError('br không được chứa thuộc tính/event handler.');
  }
  // Directives are deliberately outside the supported config surface. Front
  // matter is read with Mermaid's own fence matcher and bundled YAML JSON schema.
  if (source.includes('%%{')) throw new SourceError('Config directive chưa hỗ trợ; dùng front matter YAML với config được cho phép.');
  const normalized = source.replace(/\r\n?/g, '\n');
  const match = matchFrontMatter(normalized);
  let metadata = {};
  if (match) {
    const yaml = match.indent ? match.body.split('\n').map((line) => line.startsWith(match.indent) ? line.slice(match.indent.length) : line).join('\n') : match.body;
    try {
      metadata = load(yaml, {schema:JSON_SCHEMA}) ?? {};
    } catch (error) {
      if (Number.isInteger(error.mark?.line)) {
        const start = normalized.indexOf(match.body, normalized.indexOf('\n') + 1);
        const prefixLines = normalized.slice(0, start).split('\n').length - 1;
        error.hash = {line:prefixLines + error.mark.line};
        error.kind = "syntax";
      }
      throw error;
    }
  }
  keys(metadata, ['title','config'], 'Front matter');
  if (metadata.title !== undefined && typeof metadata.title !== 'string') throw new SourceError('title cần chuỗi.');
  const config = metadata.config ?? {};
  keys(config, ['theme','themeVariables','fontFamily','fontSize','flowchart'], 'config');
  if (config.theme !== undefined && !['default','base','dark','forest','neutral'].includes(config.theme)) throw new SourceError(`Theme chưa hỗ trợ: ${config.theme}`);
  if (config.fontFamily !== undefined) fontFamily(config.fontFamily);
  if (config.fontSize !== undefined) fontSize(config.fontSize);
  if (config.flowchart !== undefined) {
    keys(config.flowchart, ['htmlLabels','inheritDir'], 'config.flowchart');
    for (const [key,value] of Object.entries(config.flowchart)) if (typeof value !== 'boolean') throw new SourceError(`flowchart.${key} cần boolean.`);
  }
  const variables = config.themeVariables ?? {};
  const paints = ['background','primaryColor','primaryTextColor','primaryBorderColor','secondaryColor','secondaryTextColor','secondaryBorderColor','tertiaryColor','tertiaryTextColor','tertiaryBorderColor','textColor','lineColor','edgeLabelBackground','clusterBkg','clusterBorder','clusterTextColor','titleColor','nodeBkg','nodeBorder','nodeTextColor','mainBkg','defaultLinkColor','arrowheadColor'];
  keys(variables, [...paints,'fontFamily','fontSize','darkMode'], 'themeVariables');
  for (const [key,value] of Object.entries(variables)) {
    if (key === 'fontFamily') fontFamily(value);
    else if (key === 'fontSize') fontSize(value);
    else if (key === 'darkMode') {if (typeof value !== 'boolean') throw new SourceError('darkMode cần boolean.');}
    else color(value);
  }
  // Map the exact pinned preprocess cleanup back to original source lines.
  // This maps comments too: a constant front-matter offset is insufficient.
  const lineAt = []; let line = 1;
  for (let i=0;i<normalized.length;i++) {lineAt[i]=line; if (normalized[i]==='\n') line++;}
  const start = match?.length ?? 0;
  const body = normalized.slice(start);
  const kept = []; let cursor = 0;
  for (const comment of body.matchAll(/^\s*%%(?!{)[^\n]+\n?/gm)) {
    for (;cursor<comment.index;cursor++) kept.push(cursor+start);
    cursor=comment.index+comment[0].length;
  }
  for (;cursor<body.length;cursor++) kept.push(cursor+start);
  let first = 0;
  while (first<kept.length && /\s/.test(normalized[kept[first]])) first++;
  const lineMap = []; let newLine = true;
  for (let i=first;i<kept.length;i++) {
    const position = kept[i];
    if (newLine) lineMap.push(lineAt[position]);
    newLine = normalized[position]==='\n';
  }
  if (newLine && kept.length) lineMap.push(Math.min(line,lineAt[kept.at(-1)]+1));
  return {title:metadata.title ?? '', config, lineMap, sourceLineCount:line};
}
export function plainLabel(value) {
  const text = decodeEntities(String(value ?? '').replace(/(?<!&)#\w+;/g, (entity) => encodeEntities(entity))).replace(/<br\s*\/?>/gi, '\n');
  if (/<\/?[a-z][^>]*>/i.test(text)) throw new SourceError('Nhãn HTML chưa hỗ trợ; chỉ cho phép br và entity.');
  // Decode text references once; the result becomes glyph paths, never markup.
  return decodeHTML(text);
}
export function parseStyles(declarations, context) {
  const result = {};
  for (const declaration of declarations) {
    const colon = declaration.indexOf(':');
    const key = declaration.slice(0,colon).trim().toLowerCase();
    let value = declaration.slice(colon+1).trim();
    if (value.endsWith('!important')) value=value.slice(0,-10).trim();
    if (colon<1) throw new SourceError(`${context}: style không hợp lệ: ${declaration}`);
    if (['fill','stroke','color'].includes(key)) {
      if (key==='color' && value==='none') throw new SourceError(`${context}: color:none không được hỗ trợ.`);
      result[key]=color(value);
    }
    else if (key==='font-family') result[key]=fontFamily(value);
    else if (key==='font-size') result[key]=fontSize(value);
    else if (key==='font-weight' && /^(normal|bold|[1-9]00|1000)$/.test(value)) result[key]=value;
    else if (key==='font-style' && ['normal','italic','oblique'].includes(value)) result[key]=value;
    else if (key==='stroke-width' && /^\d+(?:\.\d+)?(?:px)?$/.test(value) && Number.parseFloat(value)<=16) result[key]=Number.parseFloat(value);
    else if (key==='stroke-dasharray' && /^(none|\d+(?:\.\d+)?(?:[ ,]+\d+(?:\.\d+)?)*)$/.test(value) && value.length<128) result[key]=value;
    else throw new SourceError(`${context}: style chưa hỗ trợ/không an toàn: ${declaration}`);
  }
  return result;
}
export function shapePaint(style) {
  return Object.fromEntries(Object.entries(style).filter(([key]) => ['fill','stroke','stroke-width','stroke-dasharray'].includes(key)));
}
export function labelFont(style) {
  return {font_family:style['font-family'],font_px:style['font-size'],font_weight:style['font-weight'] ?? 'normal',font_style:style['font-style'] ?? 'normal'};
}
