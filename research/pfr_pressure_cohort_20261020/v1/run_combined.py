"""One bounded same-source diagnostic/catalog retry after approval timeout."""
import runpy,signal
from pathlib import Path

def deadline(signum,frame):
    raise TimeoutError('Pressure source/catalog job exceeded its 45-second bound')
signal.signal(signal.SIGALRM,deadline);signal.alarm(45)
root=Path('research/pfr_pressure_cohort_20261020/v1')
try:
    runpy.run_path(str(root/'inspect_source.py'),run_name='__pressure_diagnostic__')
    runpy.run_path(str(root/'derive_actual.py'),run_name='__pressure_catalog__')
finally:
    signal.alarm(0)
