"""Non-mutating browser views; full saved evidence remains the default API."""


def readiness_summary(value, *, omit):
    if not isinstance(value, dict):
        return value
    summary={key:item for key,item in value.items() if key not in omit}
    summary['browser_summary']={
        'omitted_audits':[key for key in omit if key in value],
        'full_saved_evidence_retained':True,
    }
    return summary
