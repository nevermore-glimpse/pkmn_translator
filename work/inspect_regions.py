# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
raw = open(r'E:\pkmn_translator\examples\intl.txt', 'r', encoding='utf-8-sig', newline='').read()
L = raw.split('\r\n')[:-1]
for a, b in [(374, 392), (3708, 3720), (4730, 4740), (18728, 18740)]:
    print('===== lines %d..%d =====' % (a + 1, b))
    for j in range(a - 1, min(len(L), b)):
        print('  %d| %s' % (j + 1, L[j][:110]))
