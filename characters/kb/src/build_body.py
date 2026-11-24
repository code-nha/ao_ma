import json, re, sys
cards = {}
for l in open(r'C:/Users/khoa/code_nha/ebook_maker/work/_skill_trial/lanes/build1/cards/out.jsonl', encoding='utf-8'):
    d = json.loads(l); cards[d['cid']] = d['slug']
AG = {'Y':'young','A':'adult','M':'middle','E':'elderly'}
FQ = {'c':'common','u':'uncommon','r':'rare'}
SX = {'m':'male','f':'female','a':'any'}
BAD = re.compile(r'beautiful|handsome|attractive|perfect|flawless|pretty|gorgeous|sexy', re.I)
slots = {}; errs = []; ids = set()
for fn in ['body_a.txt','body_d.txt','body_efg.txt']:
    cur = None
    for n, l in enumerate(open(fn, encoding='utf-8').read().splitlines(), 1):
        if not l.strip(): continue
        if l.startswith('##'):
            s, g, vi = l[3:].split('|'); cur = s
            slots[s] = {'group': g, 'vi': vi, 'values': []}; continue
        p = l.split('|')
        if len(p) != 8: errs.append(f'{fn}:{n} fields {len(p)}'); continue
        sid, sx, ph, vi, fq, ag, ca, src = p
        vid = f'{cur}.{sid}'
        if vid in ids: errs.append('dup '+vid)
        ids.add(vid)
        if BAD.search(ph): errs.append('bad word '+vid)
        wc = len(ph.replace(',', ' ').split())
        if not 3 <= wc <= 10: errs.append(f'wordcount {wc} {vid}')
        srcs = ['k%05d' % int(x) for x in src.split(',') if x] or ['general']
        for c in srcs:
            if c != 'general' and c not in cards: errs.append('nocard '+c)
        slots[cur]['values'].append({'id': vid, 'sex': SX[sx], 'phrase': ph, 'vi': vi, 'freq': FQ[fq],
            'ages': [AG[c] for c in ag], 'causes': [x for x in ca.split(',') if x], 'src': srcs})
for s, d in slots.items():
    sx = {v['sex'] for v in d['values'] if v['id'].split('.')[1] in ('normal-m','normal-f','normal')}
    ok = 'any' in sx or {'male','female'} <= sx
    if not ok: errs.append('no normal '+s)
print('\n'.join(errs) or 'OK')
out = {'version': 1, 'age_bands': {'young':[18,30],'adult':[30,45],'middle':[45,65],'elderly':[65,120]}, 'slots': slots}
path = r'C:/Users/khoa/code_nha/ao_ma-nhan_vat/characters/kb/body.json'
json.dump(out, open(path,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
d = json.load(open(path, encoding='utf-8'))
tot=0; book=0; books=set()
print(f"{'slot':12} grp  M  F any  M-tot F-tot book%")
for s, v in d['slots'].items():
    vs=v['values']; m=sum(x['sex']=='male' for x in vs); f=sum(x['sex']=='female' for x in vs); a=sum(x['sex']=='any' for x in vs)
    b=sum(x['src']!=['general'] for x in vs); tot+=len(vs); book+=b
    for x in vs:
        for c in x['src']:
            if c!='general': books.add(cards[c])
    print(f"{s:12} {v['group']}  {m:3} {f:3} {a:3}  {m+a:4} {f+a:4}  {100*b//len(vs)}%")
print('total', tot, 'book-backed', book, f'{100*book/tot:.0f}%', 'books', len(books))
from collections import Counter
print(Counter(c for s in d['slots'].values() for x in s['values'] for c in x['src'] if c!='general' for c in [cards[c]]))
