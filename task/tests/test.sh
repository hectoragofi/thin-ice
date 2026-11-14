#!/bin/bash
# Writes one score between 0 and 1 to /logs/verifier/reward.txt.
mkdir -p /logs/verifier
python3 /tests/verify.py || echo 0 > /logs/verifier/reward.txt
[ -s /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
