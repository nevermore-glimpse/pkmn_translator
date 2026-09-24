# -*- coding: utf-8 -*-
"""Analyze intl.txt structure unambiguously."""
import re, json, sys, collections

sys.stdout.reconfigure(encoding='utf-8')
IN = r'E:\pkmn_translator\examples\intl.txt'
raw = open(IN, 'r', encoding='utf-8-sig', newline='').read()
nl = '\r\n' if '\r\n' in raw else '\n'
lines = raw.split(nl)
print('total lines (split):', len(lines))
print('trailing element empty (file ends with newline):', lines[-1] == '')
if lines[-1] == '':
    lines = lines[:-1]
print('real lines:', len(lines))

BR_MAP = re.compile(r'^\[Map\d+\]$', re.I)
BR_ANY = re.compile(r'^\[[^\[\]]*\]$')

map_lines = [i for i, l in enumerate(lines) if BR_MAP.match(l)]
any_lines = [i for i, l in enumerate(lines) if BR_ANY.match(l)]
print('lines matching [MapN]:', len(map_lines))
print('lines matching any [..]:', len(any_lines))
other = [i for i in any_lines if not BR_MAP.match(lines[i])]
print('bracket-only lines that are NOT [MapN]:', len(other))
# Are those followed by an identical line? (=> message pair) 
pair_like, header_like = [], []
for i in other:
    if i + 1 < len(lines) and lines[i + 1].strip() == lines[i].strip():
        pair_like.append(i)
    else:
        header_like.append(i)
print('  followed by identical line (message pair):', len(pair_like))
print('  NOT followed by identical line (real header?):', len(header_like))
print('  samples pair_like:', [lines[i] for i in pair_like[:15]])
print('  samples header_like:', [(i + 1, lines[i]) for i in header_like[:15]])

# distinct values
print('distinct bracket-only non-Map values:', collections.Counter(lines[i] for i in other).most_common(15))

# Model: headers = [MapN] only. Consume sequentially.
hdrs, pairs, sp = 0, [], []
i = 0
while i < len(lines):
    if BR_MAP.match(lines[i]):
        hdrs += 1; i += 1; continue
    if i + 1 >= len(lines):
        sp.append(i); break
    pairs.append((i, i + 1)); i += 2
print('MODEL A (header=[MapN]): headers=%d pairs=%d consumed=%d leftover=%d' % (hdrs, len(pairs), hdrs + 2 * len(pairs), len(sp)))
ident = sum(1 for a, b in pairs if lines[a] == lines[b])
ws_ident = sum(1 for a, b in pairs if lines[a].strip() == lines[b].strip())
print('  pairs byte-identical: %d  whitespace-identical: %d  truly different: %d' % (ident, ws_ident, len(pairs) - ws_ident))

# Model B: headers = any bracket-only line not followed by identical line, and BR_ANY-with-identical treated as message pairs
def is_hdr(i):
    if BR_MAP.match(lines[i]):
        return True
    if BR_ANY.match(lines[i]) and not (i + 1 < len(lines) and lines[i + 1].strip() == lines[i].strip()):
        return True
    return False
hdrs2, pairs2, sp2 = 0, [], []
i = 0
while i < len(lines):
    if is_hdr(i):
        hdrs2 += 1; i += 1; continue
    if i + 1 >= len(lines):
        sp2.append(i); break
    pairs2.append((i, i + 1)); i += 2
print('MODEL B: headers=%d pairs=%d consumed=%d leftover=%d' % (hdrs2, len(pairs2), hdrs2 + 2 * len(pairs2), len(sp2)))
ident2 = sum(1 for a, b in pairs2 if lines[a] == lines[b])
print('  pairs byte-identical: %d / %d' % (ident2, len(pairs2)))
multi = [(a, b) for a, b in pairs2 if lines[a].strip() != lines[b].strip()]
print('  truly different pairs:', len(multi))
for a, b in multi[:8]:
    print('    L%d %r\n    L%d %r' % (a + 1, lines[a][:100], b + 1, lines[b][:100]))

# cache coverage under MODEL B
cache = json.load(open(r'E:\pkmn_translator\examples\intl_cache.json', encoding='utf-8'))
uniq = []
seen = set()
for a, b in pairs2:
    s = lines[a]
    if s in seen:
        continue
    seen.add(s); uniq.append(s)
print('unique sources:', len(uniq))
cov = [u for u in uniq if cache.get(u)]
print('cache entries:', len(cache), ' covering sources:', len(cov))
zh = sum(1 for u in uniq if re.search(r'[\u4e00-\u9fff]', cache.get(u, '')))
print('sources whose cache value has CJK:', zh)
nozh = [u for u in uniq if cache.get(u) and not re.search(r'[\u4e00-\u9fff]', cache.get(u)) and re.search(r'[A-Za-zÀ-ÿ]', u)]
print('cached but no CJK though source has letters:', len(nozh))
json.dump({'pairs': [[a, b] for a, b in pairs2]}, open(r'E:\pkmn_translator\work\pairs.json', 'w', encoding='utf-8'))
