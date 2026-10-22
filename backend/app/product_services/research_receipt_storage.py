"""Lossless, bounded storage of repeated research provenance; no fact filtering."""
import json
from collections import Counter
from copy import deepcopy

from .analyst_shadow import digest

CONTRACT = 'research_receipt_shared_objects_v1'
REF = '$research_object'
LITERAL = '$research_literal'


def payload(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def pack(value, *, expanded_limit):
    if len(payload(value)) > expanded_limit:
        raise ValueError('Research expanded receipt exceeds bounded size')
    counts = Counter()

    def count(node, depth=0):
        if depth > 64:
            raise ValueError('Research receipt nesting exceeds bounded size')
        if isinstance(node, (dict, list)):
            if len(payload(node)) >= 1024:
                counts[digest(node)] += 1
            for child in node.values() if isinstance(node, dict) else node:
                count(child, depth + 1)

    count(value)
    objects = {}

    def encode(node):
        if isinstance(node, (dict, list)):
            key = digest(node) if len(payload(node)) >= 1024 else None
            if key and counts[key] > 1:
                if key not in objects:
                    objects[key] = content(node)
                return {REF: key}
            return content(node)
        return node

    def content(node):
        if isinstance(node, list):
            return [encode(v) for v in node]
        if isinstance(node, dict):
            if set(node) in ({REF}, {LITERAL}):
                return {LITERAL: [[k, encode(v)] for k, v in node.items()]}
            return {k: encode(v) for k, v in node.items()}
        return node

    record = encode(value)
    if len(objects) > 4096:
        raise ValueError('Research shared-object table exceeds bounded size')
    return dict(storage_contract=CONTRACT, record=record, objects=objects)


def unpack(envelope, *, expanded_limit):
    if set(envelope) != {'storage_contract', 'record', 'objects'} or envelope['storage_contract'] != CONTRACT:
        raise ValueError('Invalid research shared-object envelope')
    objects = envelope['objects']
    if not isinstance(objects, dict) or len(objects) > 4096:
        raise ValueError('Research shared-object table exceeds bounded size')
    cache = {}; active = set()

    def decode(node, depth=0):
        if depth > 64:
            raise ValueError('Research receipt nesting exceeds bounded size')
        if isinstance(node, dict) and set(node) == {REF}:
            key = node[REF]
            if not isinstance(key, str) or key not in objects or key in active:
                raise ValueError('Invalid research object reference')
            if key not in cache:
                active.add(key)
                result = decode(objects[key], depth + 1)
                active.remove(key)
                if digest(result[0]) != key:
                    raise ValueError('Research object checksum mismatch')
                cache[key] = result
            value, size = cache[key]
            return deepcopy(value), size
        if isinstance(node, dict):
            pairs = node.items()
            if set(node) == {LITERAL}:
                pairs = node[LITERAL]
                if not isinstance(pairs, list) or any(not isinstance(p, list) or len(p) != 2 or not isinstance(p[0], str) for p in pairs):
                    raise ValueError('Invalid research literal object')
            out = {}; size = 2
            for key, value in pairs:
                if key in out:
                    raise ValueError('Duplicate research literal object key')
                child, child_size = decode(value, depth + 1)
                size += len(payload(key)) + 1 + child_size + int(bool(out))
                if size > expanded_limit:
                    raise ValueError('Research expanded receipt exceeds bounded size')
                out[key] = child
            return out, size
        if isinstance(node, list):
            out = []; size = 2
            for value in node:
                child, child_size = decode(value, depth + 1)
                size += child_size + int(bool(out))
                if size > expanded_limit:
                    raise ValueError('Research expanded receipt exceeds bounded size')
                out.append(child)
            return out, size
        size = len(payload(node))
        if size > expanded_limit:
            raise ValueError('Research expanded receipt exceeds bounded size')
        return node, size

    value, _ = decode(envelope['record'])
    if set(cache) != set(objects):
        raise ValueError('Research envelope contains unused objects')
    return value
