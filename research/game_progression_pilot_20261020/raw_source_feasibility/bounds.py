"""Byte/integrity boundaries for a single data-only source check."""
import gzip,hashlib,io

def bounded_chunks(chunks,cap):
    result=bytearray()
    for chunk in chunks:
        if len(result)+len(chunk)>cap:raise ValueError('Compressed byte cap exceeded')
        result.extend(chunk)
    return bytes(result)

def verify(raw,expected):
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Frozen source SHA256 differs')

def expand(raw,cap):
    with gzip.GzipFile(fileobj=io.BytesIO(raw))as source:value=source.read(cap+1)
    if len(value)>cap:raise ValueError('Decoded serialization byte cap exceeded')
    return value
