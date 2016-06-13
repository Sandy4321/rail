#!/usr/bin/env python
"""
Rail-RNA-junction_fasta

Follows Rail-RNA-junction_config
Precedes Rail-RNA-junction_index

Reduce step in MapReduce pipelines that outputs FASTA line for a "reference"
obtained by concatenating exonic sequences framing each intron in a junction
configuration. 

Input (read from stdin)
----------------------------
Tab-delimited tuple columns:
1. Reference name (RNAME in SAM format) + 
    '+' or '-' indicating which strand is the sense strand
2. Comma-separated list of intron start positions in configuration
3. Comma-separated list of intron end positions in configuration
4. left_extend_size: by how many bases on the left side of an intron the
    reference should extend
5. right_extend_size: by how many bases on the right side of an intron the
    reference should extend
6. By how many bases on the left side of an intron the reference COULD extend,
    or NA if beginning of strand
7. By how many bases on the right side of an intron the reference COULD extend,
    or NA if end of strand

Input is partitioned by the first three fields.

Hadoop output (written to stdout)
----------------------------
Tab-delimited tuple columns:
1. '-' to enforce that all lines end up in the same partition
2. FASTA reference name including '>'. The following format is used:
    original RNAME + '+' or '-' indicating which strand is the sense strand
    + '\x1d' + start position of sequence + '\x1d' + comma-separated list of
    subsequence sizes framing introns + '\x1d' + comma-separated list of intron
    sizes + '\x1d + distance to previous intron or 'NA' if beginning of
    strand + '\x1d' + distance to next intron or 'NA' if end of strand.
3. Sequence
"""
import sys
import time
import os
import site
import argparse

if '--test' in sys.argv:
    print("No unit tests")
    #unittest.main(argv=[sys.argv[0]])
    sys.exit(0)

base_path = os.path.abspath(
                    os.path.dirname(os.path.dirname(os.path.dirname(
                        os.path.realpath(__file__)))
                    )
                )
utils_path = os.path.join(base_path, 'rna', 'utils')
site.addsitedir(utils_path)
site.addsitedir(base_path)

import bowtie
import bowtie_index
from dooplicity.tools import xstream

parser = argparse.ArgumentParser(description=__doc__, 
            formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument(\
    '--verbose', action='store_const', const=True, default=False,
    help='Print out extra debugging statements')
bowtie.add_args(parser)
args = parser.parse_args()

start_time = time.time()
input_line_count = 0
reference_index = bowtie_index.BowtieIndexReference(
                        os.path.expandvars(args.bowtie_idx)
                    )
for key, xpartition in xstream(sys.stdin, 3, skip_duplicates=True):
    '''For computing maximum left and right extend sizes for every key --
    that is, every junction combo (fields 1-3 of input).'''
    left_extend_size, right_extend_size = None, None
    left_size, right_size = None, None
    for value in xpartition:
        assert len(value) == 4
        input_line_count += 1
        left_extend_size = max(left_extend_size, int(value[-4]))
        right_extend_size = max(right_extend_size, int(value[-3]))
        try:
            left_size = max(left_size, int(value[-2]))
        except ValueError:
            left_size = 'NA'
        try:
            right_size = max(right_size, int(value[-1]))
        except ValueError:
            right_size = 'NA'
    rname = key[0]
    reverse_strand_string = rname[-1]
    rname = rname[:-1]
    junction_combo = \
            zip([int(pos) for pos in key[1].split(',')],
                    [int(end_pos) for end_pos in key[2].split(',')])
    reference_length = reference_index.length[rname]
    subseqs = []
    left_start = max(junction_combo[0][0] - left_extend_size, 1)
    # Add sequence before first junction
    subseqs.append(
            reference_index.get_stretch(rname, left_start - 1, 
                junction_combo[0][0] - left_start)
        )
    # Add sequences between junctions
    for i in xrange(1, len(junction_combo)):
        subseqs.append(
                reference_index.get_stretch(rname, 
                    junction_combo[i-1][1] - 1,
                    junction_combo[i][0]
                    - junction_combo[i-1][1]
                )
            )
    # Add final sequence
    subseqs.append(
            reference_index.get_stretch(rname,
                junction_combo[-1][1] - 1,
                min(right_extend_size, reference_length - 
                                    junction_combo[-1][1] + 1))
        )
    '''A given reference name in the index will be in the following format:
    original RNAME + '+' or '-' indicating which strand is the sense strand
    + '\x1d' + start position of sequence + '\x1d' + comma-separated list of
    subsequence sizes framing introns + '\x1d' + comma-separated list of
    intron sizes + '\x1d' + distance to previous intron or 'NA' if beginning of
    strand + '\x1d' + distance to next intron or 'NA' if end of strand.'''
    print ('-\t>' + rname + reverse_strand_string 
            + '\x1d' + str(left_start) + '\x1d'
            + ','.join([str(len(subseq)) for subseq in subseqs]) + '\x1d'
            + ','.join([str(intron_end_pos - intron_pos)
                        for intron_pos, intron_end_pos
                        in junction_combo])
            + '\x1d' + str(left_size) + '\x1d' + str(right_size)
            + '\t' + ''.join(subseqs)
        )

print >>sys.stderr, 'DONE with junction_fasta.py; in=%d; ' \
                    'time=%0.3f s' % (input_line_count,
                                        time.time() - start_time)
