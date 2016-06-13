"""
Rail-RNA-assign_splits

Follows Rail-RNA-count-inputs
Precedes Rail-RNA-preprocess

Counts up total number of reads across files on the _local_ filesystem and
assigns how they should be divided among workers.

Input (read from stdin)
----------------------------
Tab-separated fields:
---If URL is local:
1. #!splitload
2. number of read(s) (pairs) in sample; number of pairs if paired-end and
    number of reads if single-end
3 ... next-to-last. same as manifest line
4. Phred format (Sanger or Phred64)

---Otherwise:
manifest line---
(for single-end reads)
<URL>(tab)<Optional MD5>(tab)<Sample label>

(for paired-end reads)
<URL 1>(tab)<Optional MD5 1>(tab)<URL 2>(tab)<Optional MD5 2>(tab)
<Sample label>

Hadoop output (written to stdout)
----------------------------
Tab-separated fields:
---If URL is local:
1. #!splitload
2. \x1d-separated list of 0-based indexes of reads at which to start
    each new file
3. \x1d-separated list of numbers of reads to include in gzipped files
4. \x1d-separated list of manifest lines whose tabs are replaced by \x1es
5. Phred format (Sanger or Phred64)

---Otherwise:
same as manifest line
"""

import os
import site
import sys
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

from alignment_handlers import running_sum, pairwise
import math
import time
from dooplicity.ansibles import Url
from dooplicity.tools import register_cleanup, make_temp_dir
import filemover
import tempdel

# Print file's docstring if -h is invoked
parser = argparse.ArgumentParser(description=__doc__, 
            formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument(
        '-p', '--num-processes', type=int, required=False, default=1,
        help=('Number of subprocesses that will be opened at once in '
              'future steps')
    )
parser.add_argument(\
    '--out', metavar='URL', type=str, required=False, default=None,
    help='URL to which output should be written. Default is current '
         'working directory')
parser.add_argument(
    '--filename', type=str, required=False, default='split.manifest',
    help='Output manifest filename'
    )

# Add scratch command-line parameter
tempdel.add_args(parser)

args = parser.parse_args(sys.argv[1:])

start_time = time.time()
input_line_count, output_line_count = 0, 0
output_url = Url(args.out) if args.out is not None else Url(os.getcwd())
if output_url.is_local:
    # Set up destination directory
    try: os.makedirs(output_url.to_url())
    except: pass
    output_path = os.path.join(args.out, args.filename)
else:
    mover = filemover.FileMover(args=args)
    # Set up temporary destination
    import tempfile
    from dooplicity.tools import make_temp_dir
    temp_dir_path = make_temp_dir(tempdel.silentexpandvars(args.scratch))
    register_cleanup(tempdel.remove_temporary_directories, [temp_dir_path])
    output_path = os.path.join(temp_dir_path, args.filename)
samples = {}
saved = []
for input_line_count, line in enumerate(sys.stdin):
    tokens = line.strip().split('\t')
    token_count = len(tokens)
    if not (token_count > 4 and tokens[0] == '#!splitload'):
        saved.append('\t'.join(tokens[1:]))
        continue
    assert token_count in [6, 8], (
            'Line "{}" of input has {} fields, but 6 or 8 are expected.'
        ).format(line, token_count)
    if token_count == 6:
        samples[(tokens[2], None)] = (int(tokens[1]),) + tuple(tokens[2:-1])
    else:
        # token_count is 8
        samples[(tokens[2], tokens[4])] = (int(tokens[1])*2,) \
                                            + tuple(tokens[2:-1])
    phred_format = tokens[-1]
input_line_count += 1
critical_sample_values = [
            (critical_value, True) for critical_value in 
            running_sum([sample_data[0] for sample_data in samples.values()])
        ]
lines_assigned = [[]]
try:
    total_reads = critical_sample_values[-1][0]
except IndexError:
    # No splitload lines
    pass
else:
    reads_per_file = int(math.ceil(float(total_reads) / args.num_processes))
    critical_read_values = [(0, False)]
    candidate_critical_value = critical_read_values[-1][0] + reads_per_file
    while candidate_critical_value < total_reads:
        critical_read_values.append((candidate_critical_value, False))
        candidate_critical_value = critical_read_values[-1][0] + reads_per_file
    critical_values = sorted(
            list(critical_read_values + critical_sample_values),
            key=lambda crit: crit[0]
        )
    sample_iter = iter(samples.keys())
    try:
        current_sample = sample_iter.next()
    except StopIteration:
        pass
    else:
        reads_assigned, sample_index = 0, 0
        for critical_pair in pairwise(critical_values):
            if critical_pair[0][-1]:
                try:
                    current_sample = sample_iter.next()
                except StopIteration:
                    break
                sample_index = 0
            span = critical_pair[1][0] - critical_pair[0][0]
            if not span:
                continue
            lines_assigned[-1].append((current_sample, samples[current_sample][-1],
                                        sample_index, span))
            sample_index += span
            reads_assigned += span
            if not (reads_assigned % reads_per_file):
                lines_assigned.append([])
with open(output_path, 'w') as output_stream:
    for line_tuples in lines_assigned:
        if not line_tuples: continue
        print >>output_stream, '\t'.join(('#!splitload', '\x1d'.join(
                        str(line_tuple[-2]) for line_tuple in line_tuples
                    ), 
                    '\x1d'.join(
                        str(line_tuple[-1]) for line_tuple in line_tuples
                    ),
                    '\x1d'.join(
                            '\x1e'.join(samples[line_tuple[0]][1:])
                            for line_tuple in line_tuples
                        ),
                    phred_format
                    ))
    for line in saved:
        print >>output_stream, line.strip()
if not output_url.is_local:
    mover.put(output_path, output_url.plus(args.filename))
    os.remove(output_path)

sys.stdout.flush()
print >>sys.stderr, 'DONE with assign_splits.py; in/out=%d/%d; ' \
        'time=%0.3f s' % (input_line_count, output_line_count,
                            time.time() - start_time)
