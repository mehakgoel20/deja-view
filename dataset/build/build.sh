#!/bin/bash
# Full dataset rebuild: extract from every source, assemble, finalize, audit.
set -e
cd "$(dirname "$0")"

echo "### extract: statuspage"
python3 -u run_extract2.py 2>&1 | sed -n '1,2p'
echo "### extract: curated index"
python3 -u extract_danluu.py 2>&1 | sed -n '1,2p'
echo "### extract: github availability reports"
python3 -u extract_gh2.py 2>&1 | sed -n '1,2p'
echo "### extract: engineering blog postmortems"
python3 -u extract_blogs.py 2>&1 | sed -n '1,2p'
echo "### extract: aws post-event summaries"
python3 -u extract_aws.py 2>&1 | sed -n '1,1p'
echo "### assemble"
python3 -u assemble.py 2>&1 | tail -13
echo "### finalize"
python3 -u finalize.py 2>&1 | tail -7
echo "### audit"
python3 -u audit.py 2>&1 | tail -24
