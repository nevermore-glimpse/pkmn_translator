# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
raw = open(r'E:\pkmn_translator\examples\intl.txt', 'r', encoding='utf-8-sig', newline='').read()
L = raw.split('\r\n')[:-1]
BR_MAP = re.compile(r'^\[Map\d+\]$', re.I)
BR_ANY = re.compile(r'^\[[^\[\]]*\]$')
n = 0
for i, l in enumerate(L):
    if BR_ANY.match(l) and not BR_MAP.match(l):
        n += 1
        print('=== line %d : %r ===' % (i + 1, l))
        for j in range(max(0, i - 3), min(len(L), i + 4)):
            mark = '>>' if j == i else '  '
            print('  %s %d| %s' % (mark, j + 1, L[j][:90]))
print('total non-Map bracket-only lines:', n)
