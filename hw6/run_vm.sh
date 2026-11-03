#!/bin/bash
set -euo pipefail

cd /opt/hw6

set -a
source ./runtime-config.sh
set +a

export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export MKL_NUM_THREADS=2

exec .venv/bin/python vm_runner.py
