# Copyright NEXTGGTECH. Elastic License 2.0.

import subprocess
res = subprocess.run([
    'docker', 'inspect', '--format',
    '{\"running\":{{.State.Running}},\"status\":\"{{.State.Status}}\",\"mounts\":\"{{range .Mounts}}{{.Source}}{{end}}\"}',
    'mcp-sandbox'
], capture_output=True, text=True)
print('RC:', res.returncode)
print('STDOUT:', repr(res.stdout))
print('STDERR:', repr(res.stderr))
if res.returncode == 0:
    try:
        print('JSON format works')
        # print('JSON:', json.loads(res.stdout))
    except Exception as e:
        print('Error:', e)
