#!/bin/zsh
set -eu
task_dir="${0:A:h}"
exec "$task_dir/.venv/bin/python" "$task_dir/manage.py" start
