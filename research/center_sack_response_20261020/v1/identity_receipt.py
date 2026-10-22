"""Receipt-only comparison; no database writes or feature derivation."""
def compare_existing_cases(current, prior_queue):
    def keyed(rows):
        result = {}
        for row in rows:
            key = (row['source_table'], row['source_record_key'])
            if key in result:
                raise ValueError('Duplicate identity receipt key')
            result[key] = row
        return result
    durable = keyed(prior_queue['durable_readback_records'])
    companion = keyed(prior_queue['records'])
    evidence = []
    for row in current:
        key = (row['source_table'], row['source_record_key'])
        old = durable.get(key)
        original = companion.get(key)
        prior_id = original.get('identity_quarantine_id') if original else None
        same = bool(old and prior_id and row.get('identity_quarantine_id') == prior_id and
                    all(row.get(field) is not None and str(row[field]) == str(old.get(field))
                        for field in ('status', 'first_seen_at', 'updated_at')))
        evidence.append(dict(source_table=key[0], source_record_key=key[1],
                             prior_durable_id_field_present=bool(old and 'identity_quarantine_id' in old),
                             prior_identity_quarantine_id=prior_id,
                             prior_id_evidence='queue.records companion matched by source_table/source_record_key',
                             unchanged=same))
    return dict(unchanged_existing_cases=sum(row['unchanged'] for row in evidence),
                existing_case_comparison_evidence=evidence)
