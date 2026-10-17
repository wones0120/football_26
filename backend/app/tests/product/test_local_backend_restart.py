"""Duplicate worker cleanup must preserve managed and unrelated consumers."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('extra_repo_worker', [False, True])
def test_launchd_cleanup_stops_only_extra_repository_worker(tmp_path, extra_repo_worker):
    script=Path(__file__).resolve().parents[4]/'scripts'/'restart_local_backend.sh'
    shell=r'''
      task_script="$1"
      launchctl() { if [[ "$1" == "list" ]]; then printf '101\t0\tcom.football26.worker\n201\t0\tcom.football26.api\n'; fi; }
      set -- status
      source "${task_script}" >/dev/null
      pgrep() { printf '101\n102\n103\n'; }
      is_repo_process() { [[ "$1" == "102" && "${EXTRA_REPO_WORKER}" == "yes" ]]; }
      stop_pid() { printf '%s\n' "$1"; }
      stop_extra_repo_workers
    '''
    result=subprocess.run(['bash','-c',shell,'test-restart',str(script)],
        env={**os.environ,'TMPDIR':str(tmp_path),'EXTRA_REPO_WORKER':'yes' if extra_repo_worker else 'no'},
        text=True,capture_output=True,check=True)
    assert result.stdout.strip()==('102' if extra_repo_worker else '')
