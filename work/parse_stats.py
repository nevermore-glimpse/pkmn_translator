# -*- coding: utf-8 -*-
import sys, re, collections, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'E:\pkmn_translator')
import parser as P

path = r'E:\pkmn_translator\examples\intl.txt'
lines, newline = P.read_file(path, 'utf-8-sig')
print('lines:', len(lines), 'newline:', repr(newline))
entries, special = P.extract_entries(lines)
print('entries:', len(entries), 'special:', len(special))
print('reasons:', collections.Counter(s['reason'] for s in special).most_common())

# which lines are "skipped"?
skipped = set()
for i, l in enumerate(lines):
    s = l.strip()
    if not s or P.is_block(s) or P.is_number(s):
        skipped.add(i)
print('skipped lines:', len(skipped))

covered = set()
for ln, src in entries:
    covered.add(ln - 1); covered.add(ln)
for s in special:
    covered.add(s['line_no'])
    if s['next_line_no'] is not None:
        covered.add(s['next_line_no'])
print('covered by entries+special:', len(covered), ' uncovered(non-skipped):', len(set(range(len(lines))) - skipped - covered))

# special cases that are actually whitespace-variant pairs
ws = [s for s in special if s['next_text'] is not None and s['text'].strip() == (s['next_text'] or '').strip()]
print('special with whitespace-identical next line:', len(ws))
real_special = [s for s in special if s not in ws]
print('remaining specials:', len(real_special))
for s in real_special[:20]:
    print('  L%d [%s] %r -> %r' % (s['line_no'] + 1, s['reason'], s['text'][:70], (s['next_text'] or '')[:70]))

# unique sources incl. specials that are pairs
seen = []
st = set()
for ln, src in entries:
    if src not in st:
        st.add(src); seen.append(src)
for s in ws:
    if s['text'] not in st:
        st.add(s['text']); seen.append(s['text'])
print('unique sources (entries + ws-specials):', len(seen))
json.dump({'entries': [[ln, src] for ln, src in entries],
           'ws_special': [[s['line_no'], s['text']] for s in ws],
           'real_special': [s for s in real_special]},
          open(r'E:\pkmn_translator\work\parsed.json', 'w', encoding='utf-8'), ensure_ascii=False)
