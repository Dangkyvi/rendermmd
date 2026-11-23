"""Bounded current-state metadata in SVG/PNG. No database, cache or history.

Only extract inert UTF-8 JSON. Uploaded graphics are never forwarded/rendered:
callers rebuild images from validated Mermaid through the existing renderer.
"""
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zlib

MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 68 * 1024 * 1024
SVG_NS = 'http://www.w3.org/2000/svg'
METADATA_ID = 'mmdToDiagram-edit'
PNG_KEY = b'mmdToDiagram.edit'
SIGNATURE = b'\x89PNG\r\n\x1a\n'


class ArtifactError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def pack(diagram_id, revision, source, state, *, preview=False):
    payload = dict(format='mmdToDiagram/editable', schema=1, diagram_id=diagram_id,
                   revision=revision, source=source, state=state, preview=preview)
    payload['checksum'] = hashlib.sha256(canonical(payload)).hexdigest()
    raw = canonical(payload)
    if len(raw) > MAX_METADATA_BYTES:
        raise ArtifactError('Metadata vượt giới hạn 2 MiB; không công bố kết quả.')
    return raw


def _unique_pairs(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ArtifactError('Metadata có JSON key trùng nhau.')
        result[key] = value
    return result


def unpack(raw):
    if not raw or len(raw) > MAX_METADATA_BYTES:
        raise ArtifactError('Metadata rỗng hoặc vượt giới hạn 2 MiB.')
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_pairs,
                             parse_constant=lambda v: (_ for _ in ()).throw(ArtifactError('JSON không hữu hạn.')))
        keys = {'format','schema','diagram_id','revision','source','state','preview','checksum'}
        if not isinstance(payload,dict) or set(payload)!=keys or payload['format']!='mmdToDiagram/editable' or type(payload['schema']) is not int or payload['schema']!=1:
            raise ArtifactError('Không đúng schema metadata chỉnh sửa v1.')
        if not isinstance(payload['diagram_id'],str) or not payload['diagram_id'] or type(payload['revision']) is not int or payload['revision']<1 or type(payload['preview']) is not bool:
            raise ArtifactError('diagram_id/revision/preview trong metadata không hợp lệ.')
        if not isinstance(payload['source'],str) or not isinstance(payload['state'],dict):
            raise ArtifactError('Source/model trong metadata không hợp lệ.')
        checksum = payload['checksum']
        unsigned = {k:v for k,v in payload.items() if k!='checksum'}
        if not isinstance(checksum,str) or checksum!=hashlib.sha256(canonical(unsigned)).hexdigest():
            raise ArtifactError('Checksum metadata không khớp; file có thể đã bị thay đổi.')
        return payload
    except (ValueError, TypeError, UnicodeError, RecursionError) as e:
        if isinstance(e,ArtifactError):
            raise
        raise ArtifactError('Metadata JSON không hợp lệ.') from e


def _png_chunks(data):
    if not data.startswith(SIGNATURE):
        raise ArtifactError('PNG signature không hợp lệ.')
    offset=8;first=True;has_data=False
    while offset+12<=len(data):
        size,kind=struct.unpack_from('>I4s',data,offset)
        end=offset+size+12
        if end>len(data):
            raise ArtifactError('PNG chunk bị cắt ngắn.')
        body=data[offset+8:offset+8+size]
        crc=struct.unpack_from('>I',data,offset+8+size)[0]
        if zlib.crc32(body,zlib.crc32(kind)) & 0xffffffff != crc:
            raise ArtifactError('PNG CRC không hợp lệ.')
        if first and (kind!=b'IHDR' or size!=13):
            raise ArtifactError('Thiếu PNG IHDR.')
        first=False;has_data |= kind==b'IDAT'
        yield kind,body,offset,end
        offset=end
        if kind==b'IEND':
            if size or offset!=len(data) or not has_data:
                raise ArtifactError('PNG IEND không hợp lệ.')
            return
    raise ArtifactError('PNG chưa hoàn chỉnh.')


def extract(data):
    if isinstance(data,str):
        try:data=data.encode('utf-8')
        except UnicodeError as e:raise ArtifactError('Artifact không phải UTF-8 hợp lệ.') from e
    if not isinstance(data,bytes) or len(data)>MAX_ARTIFACT_BYTES:
        raise ArtifactError('Artifact phải là SVG/PNG bytes trong giới hạn 68 MiB.')
    candidates=[]
    if data.startswith(SIGNATURE):
        prefix=PNG_KEY+b'\0\0\0\0\0'
        for kind,body,_,_ in _png_chunks(data):
            if kind==b'iTXt' and body.split(b'\0',1)[0]==PNG_KEY:
                if not body.startswith(prefix):
                    raise ArtifactError('Metadata PNG cần iTXt UTF-8 không nén, không language tag.')
                candidates.append(body[len(prefix):])
    else:
        try:
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ArtifactError('Không nhận DTD/entity trong SVG.')
            root=ET.fromstring(data)
            if root.tag!='{'+SVG_NS+'}svg':
                raise ArtifactError('Artifact không phải SVG.')
            for element in root.iter():
                if element.tag=='{'+SVG_NS+'}metadata' and element.attrib.get('id')==METADATA_ID:
                    if element not in list(root) or len(element):
                        raise ArtifactError('Metadata phải là JSON text trong con trực tiếp của SVG.')
                    candidates.append((element.text or '').encode('utf-8'))
        except (ET.ParseError,UnicodeError,RecursionError) as e:
            raise ArtifactError('SVG không hợp lệ.') from e
    if len(candidates)!=1:
        raise ArtifactError('Cần đúng một metadata chỉnh sửa. Hãy dùng file SVG/PNG gốc hoặc khởi tạo từ .mmd.')
    return unpack(candidates[0])


def embed_svg(svg, raw):
    # The renderer supplies validated SVG with a plain <svg> root. Inserting
    # only this escaped text node leaves all drawing primitives untouched.
    if not svg.startswith('<svg ') or '<metadata' in svg:
        raise ArtifactError('Chỉ nhúng vào SVG mới từ renderer.')
    end=svg.index('>')+1
    return svg[:end]+'<metadata id="'+METADATA_ID+'">'+escape(raw.decode('utf-8'))+'</metadata>'+svg[end:]


def embed_png(png, raw):
    body=PNG_KEY+b'\0\0\0\0\0'+raw
    kind=b'iTXt'
    chunk=struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(body,zlib.crc32(kind)) & 0xffffffff)
    chunks=list(_png_chunks(png))
    if any(k==b'iTXt' and b.split(b'\0',1)[0]==PNG_KEY for k,b,_,_ in chunks):
        raise ArtifactError('Chỉ nhúng vào PNG mới từ renderer.')
    end=chunks[0][3]
    return png[:end]+chunk+png[end:]
