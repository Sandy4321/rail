"""
Converts intron flanking sequences into bed format

Doesn't take into consideration sample label atm
"""
import os
import sys
import argparse
import site
import time

base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(base_path, "util"))

from collections import defaultdict
from operator import itemgetter
import counter


def addRead(refid,st,end,positions):
    for i in range(st,end):
        positions[refid][str(i)]+=1
    return positions

gpositions = defaultdict(counter.Counter)

for ln in sys.stdin:
    ln = ln.rstrip()
    toks = ln.split("\t")
    assert len(toks) >= 6
    
    pt,st,en,lab,seq5,seq3 = toks[0],int(toks[1]),int(toks[2]),toks[3],toks[4],toks[5]
    #refid = pt[:pt.rfind(';')][:]
    refid = pt
    gpositions = addRead(refid,st-len(seq5),st,gpositions)
    gpositions = addRead(refid,en,en+len(seq3),gpositions)

for d,c in gpositions.iteritems():
    glist = [(int(pos),freq) for pos,freq in c.items()]
    glist.sort(key=itemgetter(0))
    for G in glist:
        pos,freq = G
        print "%s\t%d\t%d\t%d"%(d,pos,pos+1,freq)
