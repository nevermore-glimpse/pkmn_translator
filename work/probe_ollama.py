# -*- coding: utf-8 -*-
"""Probe Ollama throughput using the project's real translate path."""
import time, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'E:\pkmn_translator')
import config, processor as PR
from translator import OllamaClient

raw = open(r'E:\pkmn_translator\examples\intl.txt', 'r', encoding='utf-8-sig', newline='').read()
lines = raw.split('\r\n')
BR = re.compile(r'^\[[^\[\]]*\]$')
if lines and lines[-1] == '':
    lines = lines[:-1]

# take a contiguous block of real sources (skip headers naively by bracket test)
todo = []
i = 0
while i < len(lines) and len(todo) < 12:
    if BR.match(lines[i]):
        i += 1; continue
    s = lines[i]
    if s.strip() and not PR.is_pure_control(s):
        todo.append(s)
    i += 2

PR.load_terms()
print('glossary terms loaded:', len(PR._TERMS))
client = OllamaClient()
client.translate_batch([(0, 'ping')])  # warm up / load model
print('model loaded')

# batch of 10, matching BATCH_SIZE=10
batch = []
for k, t in enumerate(todo[:10]):
    safe, maps, breaks, hits = PR.prepare(t)
    batch.append((k, safe))

t0 = time.time()
res = client.translate_batch(batch)
el = time.time() - t0
print('batch of %d took %.1fs -> %.2f items/s' % (len(batch), el, len(batch) / el))
ok = 0
for k, safe in batch:
    r = res.get(k)
    st = 'OK ' if r and r.strip() else 'MISS'
    print('%s idx%d src=%r' % (st, k, safe[:60]))
    if r:
        print('      zh=%r' % r[:60])
    if r and r.strip():
        ok += 1
print('returned:', ok, '/', len(batch))
