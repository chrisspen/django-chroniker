#!/bin/bash
set -e
if [ ! -d .env ]; then
    echo "[$(date)] Initializing environment."
    virtualenv -p python3.7 .env
    . .env/bin/activate
    pip install -U pip setuptools wheel
    pip install -r requirements-test.txt
fi
. .env/bin/activate
echo "[$(date)] Building package."
python setup.py sdist
FN=`find ./dist -name "*.tar.gz" -print0 | xargs -r -0 ls -1 -t | head -1`
echo "[$(date)] Uploading $FN."
twine upload $FN