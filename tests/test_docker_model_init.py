import os
from pathlib import Path
import subprocess


def test_model_download_failure_can_retry_and_existing_model_is_reused(tmp_path):
    fake = tmp_path / 'ollama'
    fake.write_text('''#!/bin/sh
case "$1" in
  show) test -f "$MODEL_STATE" ;;
  pull) test "$FAIL_DOWNLOAD" != 1 || exit 7
        touch "$MODEL_STATE"
        echo pull >> "$MODEL_CALLS" ;;
esac
''')
    fake.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + ':' + os.environ['PATH'],
           'OLLAMA_MODEL': 'qwen3:8b', 'MODEL_STATE': str(tmp_path / 'model'),
           'MODEL_CALLS': str(tmp_path / 'calls'), 'FAIL_DOWNLOAD': '1'}
    script = Path(__file__).resolve().parents[1] / 'docker/model-init.sh'
    assert subprocess.run(['sh', str(script)], env=env).returncode == 7
    assert not Path(env['MODEL_STATE']).exists()
    env['FAIL_DOWNLOAD'] = '0'
    assert subprocess.run(['sh', str(script)], env=env).returncode == 0
    assert subprocess.run(['sh', str(script)], env=env).returncode == 0
    assert Path(env['MODEL_CALLS']).read_text() == 'pull\n'
