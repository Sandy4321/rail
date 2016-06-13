#!/usr/bin/env python
"""
Rail-RNA-junction_index
Follows Rail-RNA-junction_fasta
Precedes Rail-RNA-realign

Reduce step in MapReduce pipelines that builds a new Bowtie index from the
FASTA output by RailRNA-junction_fasta.

Input (read from stdin)
----------------------------
Tab-delimited tuple columns:
1. '-' to enforce that all lines end up in the same partition
2. FASTA reference name including '>'. The following format is used:
    original RNAME + '+' or '-' indicating which strand is the sense strand
    + '\x1d' + start position of sequence + '\x1d' + comma-separated list of
    subsequence sizes framing introns + '\x1d' + comma-separated list of intron
    sizes + '\x1d' + base-36-encoded integer A such that A & sample index != 0
    iff sample contains junction combo
3. Sequence

Input is partitioned by the first column and sorted on the second column to
ensure that exactly the same FASTA file is indexed every time.

Hadoop output (written to stdout)
----------------------------
None.

Other output (written to directory specified by command-line parameter --out)
----------------------------
Bowtie index files for realignment only to regions framing introns of kept
unmapped reads from Rail-RNA-align.

A given reference name in the index is in the following format:    
    original RNAME + '+' or '-' indicating which strand is the sense
    strand + '\x1d' + start position of sequence + '\x1d' + comma-separated
    list of subsequence sizes framing introns + '\x1d' + comma-separated
    list of junction sizes.
"""
import os
import sys
import site
import subprocess
import argparse
import tarfile
import threading

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
from dooplicity.ansibles import Url
from dooplicity.tools import register_cleanup, make_temp_dir
import filemover
import tempdel

# Print file's docstring if -h is invoked
parser = argparse.ArgumentParser(description=__doc__, 
            formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument(\
    '--out', metavar='URL', type=str, required=False,
    default='None',
    help='Bowtie index files are written to this URL. DEFAULT IS CURRENT '
         'WORKING DIRECTORY.')
parser.add_argument(\
    '--basename', type=str, required=False,
    default='junction',
    help='Basename for index to be written')
parser.add_argument(\
    '--keep-alive', action='store_const', const=True, default=False,
    help='Prints reporter:status:alive messages to stderr to keep EMR '
         'task alive')

filemover.add_args(parser)
bowtie.add_args(parser)
tempdel.add_args(parser)
args = parser.parse_args()

import time
start_time = time.time()

output_filename, output_stream, output_url = [None]*3
output_url = Url(args.out) if args.out is not None \
    else Url(os.getcwd())
# Set up temporary destination
import tempfile
temp_dir_path = make_temp_dir(tempdel.silentexpandvars(args.scratch))
# For deleting temporary directory, even on unexpected exit
register_cleanup(tempdel.remove_temporary_directories, [temp_dir_path])
# Set up temporary destination
try: os.makedirs(os.path.join(temp_dir_path, 'index'))
except: pass
# Write to temporary directory, and later upload to URL
index_basename = os.path.join(temp_dir_path, 'index/' + args.basename)
fasta_file = os.path.join(temp_dir_path, 'temp.fa')
print >>sys.stderr, 'Opened %s for writing....' % fasta_file
with open(fasta_file, 'w') as fasta_stream:
    input_line_count = 0
    for line in sys.stdin:
        if args.keep_alive and not (input_line_count % 1000):
            print >>sys.stderr, 'reporter:status:alive'
        tokens = line.rstrip().split('\t')
        if len(tokens) == 2 and tokens[1] == 'dummy':
            # dummy line
            continue
        assert len(tokens) == 3
        rname, seq = tokens[1:]
        '''A given reference name in the index will be in the following
        format:
        original RNAME + '+' or '-' indicating which strand is the
        sense strand + '\x1d' + start position of sequence + '\x1d' +
        comma-separated list of subsequence sizes framing introns + '\x1d'
        + comma-separated list of intron sizes.'''
        print >>fasta_stream, rname
        fasta_stream.write(
                '\n'.join([seq[i:i+80] for i 
                            in xrange(0, len(seq), 80)]) + '\n'
            )
        input_line_count += 1
    if not input_line_count:
        '''There were no input FASTA files. Write one bum line so the
        pipeline doesn't fail.'''
        print >>fasta_stream, '>bum\nNA'
        print >>sys.stderr, ('Wrote bum index because no transcripts were '
                             'passed.')

# Build index
print >>sys.stderr, 'Running bowtie2-build....'

if args.keep_alive:
    class BowtieBuildThread(threading.Thread):
        """ Wrapper class for bowtie-build that permits polling for completion.
        """
        def __init__(self, command_list):
            super(BowtieBuildThread, self).__init__()
            self.command_list = command_list
            self.bowtie_build_process = None
        def run(self):
            self.bowtie_build_process = subprocess.Popen(self.command_list,
                                            stdout=sys.stderr).wait()
    bowtie_build_thread = BowtieBuildThread([args.bowtie2_build_exe,
                                                fasta_file,
                                                index_basename])
    bowtie_build_thread.start()
    while bowtie_build_thread.is_alive():
        print >>sys.stderr, 'reporter:status:alive'
        sys.stderr.flush()
        time.sleep(5)
    if bowtie_build_thread.bowtie_build_process:
        raise RuntimeError('Bowtie index construction failed w/ exitlevel %d.'
                                % bowtie_build_thread.bowtie_build_process)
else:
    bowtie_build_process = subprocess.Popen(
                                [args.bowtie2_build_exe,
                                    fasta_file,
                                    index_basename],
                                stderr=sys.stderr,
                                stdout=sys.stderr
                            )
    bowtie_build_process.wait()
    if bowtie_build_process.returncode:
        raise RuntimeError('Bowtie index construction failed w/ exitlevel %d.'
                                % bowtie_build_process.returncode)

# Compress index files
print >>sys.stderr, 'Compressing isofrag index...'
junction_index_filename = args.basename + '.tar.gz'
junction_index_path = os.path.join(temp_dir_path, junction_index_filename)
index_path = os.path.join(temp_dir_path, 'index')
tar = tarfile.TarFile.gzopen(junction_index_path, mode='w', compresslevel=3)
for index_file in os.listdir(index_path):
    tar.add(os.path.join(index_path, index_file), arcname=index_file)
tar.close()
# Upload compressed index
print >>sys.stderr, 'Uploading or copying compressed index...'
mover = filemover.FileMover(args=args)
mover.put(junction_index_path, output_url.plus(junction_index_filename))

print >>sys.stderr, 'DONE with junction_index.py; in=%d; time=%0.3f s' \
                        % (input_line_count, time.time() - start_time)
