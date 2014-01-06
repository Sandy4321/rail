#!/usr/bin/env python
"""
Rail-RNA-intron
Follows Rail-RNA-align
Precedes Rail-RNA-intron_post

Reduce step in MapReduce pipelines that infers intron/exon boundaries from 
spliced alignments output by Rail-RNA-align. Each worker operates on a set of
genome partitions, clustering alignments that overlap and associating clusters
with donor/acceptor motifs.

Input (read from stdin)
----------------------------
Tab-delimited columns:
1. Reference name (RNAME in SAM format) + ';' + partition number +  
    '+' or '-' indicating which strand is the sense strand
2. Sample label
3. Candidate intron start (inclusive) on forward strand (1-indexed)
4. Candidate intron end (exclusive) on forward strand (1-indexed)
5. Number of nucleotides between 5' end of candidate intron and 5' end of read
from which it was inferred, ASSUMING THE SENSE STRAND IS THE FORWARD STRAND.
That is, if the sense strand is the reverse strand, this is the distance
between the 5' end of the reverse-complemented read and the 5' end of the
reverse-complemented intron.
6. Number of nucleotides between 3' end of candidate intron and 3' end of read 
from which it was inferred, ASSUMING THE SENSE STRAND IS THE FORWARD STRAND.

Output (written to stdout)
----------------------------
Tab-delimited columns recording splice sites 
....
"""
import os
import sys
# Regular expressions are used to identify splice-site motifs
import re
import itertools
import argparse
import site
import numpy as np

base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for directory_name in ['fasta', 'interval']:
    site.addsitedir(os.path.join(base_path, directory_name)

import partition
import fasta

# Initialize lists of donor/acceptor motifs in order of descending priority
_forward_strand_motifs = [('GT', 'AG'), ('GC', 'AG'), ('AT', 'AC')]
_reverse_strand_motifs = [('CT', 'AC'), ('CT', 'GC'), ('GT', 'AT')]

def intron_clusters_in_partition(candidate_introns, partition_start, 
	partition_end, cluster_radius=5, verbose=False):
	""" Clusters candidate introns from a strand in a genomic partition.

		Each candidate intron is specified by its start position start_position
		and its end position end_position (exclusive) and is associated with a
		count read_count of the number of reads supporting the candidate.
		The algorithm iterates through a dynamic lineup of candidates. The
		lineup is initially the list of candidates in order of descending
		read_count. A cluster is formed by associating a given candidate C
		under examination with candidates {C_i} of the same size that lie
		within cluster_radius bases of C. The {C_i} are then removed from the
		lineup, and the next candidate is examined. The algorithm also filters
		out every cluster whose leftmost intron is not wholly within
		[partition_start, partition_end).
		
		candidate_introns: A dictionary. Each key is a tuple
			(start_position, end_position) and its corresponding value is a
			list (of length read_count), each of whose items is a tuple
			(sample_label, five_prime_displacement, three_prime_displacement)
			associated with a read supporting the candidate. Here,
			five_prime_displacement is the displacement of the 5' end of
            the candidate from the 5' end of the read, while
            three_prime_displacement is the displacement of the 3' end of
            the candidate from the 3' end of the read
		partition_start: Start position (inclusive) of partition.
		partition_end: End position (exclusive) of partition.
		cluster_radius: Distance from a candidate intron under examination
			within which to search for candidate introns in the same cluster.
			See above for a detailed description.
		verbose: True iff counts of possible splice junctions, clusters, and
			filtered clusters should be written to stderr.

		Return value: A list of lists, each of which corresponds to a cluster
		of candidate introns. Each item in a cluster is a tuple
		(start_position, end_position, sample_label, five_prime_displacement,
			three_prime_displacement), which corresponds to a read
		supporting a candidate intron spanning [start_position, end_position)
		in the cluster.
	"""
	'''Construct list of candidate introns sorted in order of descending
	read_count.'''
	candidate_intron_list = [(len(sample_labels), 
								end_position - start_position, end_position)
								for (start_position, end_position),
								sample_labels in candidate_introns.items()]
	candidate_intron_list.sort()
	# Construct set of candidate introns for fast searching
	candidate_intron_set = set()
	for _, intron_size, end_position in candidate_intron_list:
		candidate_intron_set.add((intron_size, end_position))
	candidate_intron_count = len(candidate_intron_set)
	# Initialize set for storing candidate introns already clustered
	clustered_introns = set()
	intron_clusters = []
	total_cluster_count = 0
	filtered_cluster_count = 0
	for _, intron_size, end_position in candidate_intron_list:
		if (intron_size, end_position) not in clustered_introns:
			total_cluster_count += 1
			clustered_introns.add((intron_size, end_position))
			intron_cluster = [(intron_size, end_position)]
			for an_end_position in xrange(end_position - cluster_radius,
											end_position + cluster_radius + 1):
				if (intron_size, an_end_position) in candidate_intron_set \
					and (intron_size,
							an_end_position) not in clustered_introns:
					'''If a nearby candidate hasn't been clustered, absorb it
					into the current cluster.'''
					intron_cluster.append((intron_size, an_end_position))
					clustered_introns.add((intron_size, an_end_position))
			if start_position <= min([an_end_position 
					for _, an_end_position in intron_cluster]) < end_position:
				'''Add a cluster iff its leftmost element lies in
				[start_position, end_position)'''
				intron_clusters.append(intron_cluster)
			else:
				filtered_cluster_count += 1
			assert len(clustered_introns) <= candidate_intron_counts
			if len(clustered_introns) == candidate_intron_count:
				if verbose:
					print >> sys.stderr, '%d possible splice junctions '
						'were clustered down to %d; then %d clusters were ' 
						'filtered out.' % (candidate_intron_count, 
							total_cluster_count, filtered_cluster_count)
				# Collect reads supporting cluster
				reads_for_intron_clusters = []
				for intron_cluster in intron_clusters:
					reads_for_intron_cluster = []
					for an_intron_size, an_end_position in intron_cluster:
						a_start_position = an_end_position - an_intron_size
						intron_cluster_reads.append((a_start_position, 
							an_end_position) \
							+ candidate_introns[(a_start_position,
													an_end_position)])
					reads_for_intron_clusters.append(reads_for_intron_cluster)
				return reads_for_intron_clusters
	raise RuntimeError('For loop should never be completed.')

def ranked_splice_sites_from_cluster(fasta_object, intron_cluster,
	rname, motifs, verbose=False):
	""" Ranks possible splice sites for a cluster using donor/acceptor motifs.

		Consider the following cluster of three candidate introns for which the
		sense strand is the forward strand, used here as an illustrative
		example.

					 5'													3'
		I1		     	============================================
		I2	  	   		  ============================================
		I3	      		    =========================================
		Reference		GCGGGTAATAG................................AGAATA

		Call the length of the full reference strand reference_length. Consider 
		the minimum and maximum start positions (inclusive) S_min and S_max of 
		the candidate introns. Above, I1 sets S_min and I3 sets S_max. Consider 
		also the minimum and maximum end positions (exclusive) E_min and E_max
		of the candidate introns. Above, I1 sets E_min and I2 sets E_max. The
		algo scans for splice-site motifs GT..AG, GC..AG, and AT..AC on the
		corresponding intervals
		[S_min, min(S_max + 2, reference_length))
		..
		[min(E_min - 2, 0), E_max) . (These splice-site motifs assume the
		sense strand is the forward strand. If instead the sense strand is the
		reverse strand, the motifs are CT..AC, CT..GC, and GT..AT.) Splice
		sites are then ranked according to motif:
						sense strand = +		sense strand = -
				1. 			GT..AG 					CT..AC
				2. 			GC..AG 					CT..GC
				3. 			AT..AC 					GT..AT
		(References: 
			-Turunen JJ, Niemela EH, Verma B, Frilander MJ. The significant
			other: splicing by the minor spliceosome. Wiley Interdiscip Rev
			RNA. 2013 Jan-Feb;4(1):61-76. doi: 10.1002/wrna.1141.

			-http://onlinelibrary.wiley.com/doi/10.1002/wrna.1141/full)
		If more than one possible motif (pair) of the same rank is found, the
		tie is broken as follows. The means and standard deviations of the
		start and end positions of the candidate introns are computed. Then the
		z-score of the start motif position is added to the z-score of the end
		end motif position, and the motif pairs are ranked in order of
		ascending z-score. If no motifs are found, the return value of this
		function is an empty list. So above, ranked first would be a GT..AG,
		which is spanned by I3, and second would be a GC..AG, spanned by
		[I1's start position, I3's end position].

		ALL INPUT COORDINATES ARE ASSUMED TO BE 1-INDEXED.

		fasta_object: object of class fasta.fasta corresponding to FASTA
            reference; used to find splice-site motifs.
        intron_cluster: a list of lists, each of which corresponds to a cluster
			of candidate introns. Each item in a cluster is a tuple
			(start_position, end_position, sample_label, 
				five_prime_displacement, three_prime_displacement), which
			corresponds to a read supporting a candidate intron spanning
			[start_position, end_position) in the cluster.
		rname: SAM-format RNAME indicating the chromosome.
		motifs: List of motif tuples (donor motif, acceptor motif) in order of
			descending rank. Example tuple: ('GT', 'AG').
		verbose: If True, writes to stderr when no splice sites are identified
			for a cluster.

		Return value: List of tuples representing possible final introns in
			order of ascending rank. Each tuple is of the form
			(start position, end position, summed z-score,
				left motif, right motif). Example: [(142451, 143128, 2.8324,
					'GT', 'AG'), (142449, 143128, 3.1124, 'GC', 'AG')].
	"""
		start_positions, end_positions, _, _, _ = zip(*intron_cluster)
		reference_length = fasta_object.length(rname)
		min_start_position = min(start_positions)
		max_start_position = min(max(start_positions) + 2, reference_length)
		min_end_position = min(min(end_positions) - 2, 1)
		max_end_position = max(end_positions)
		left_sequence = fasta_object.fetch_sequence(rname, min_start_position,
			max_start_position - 1).upper()
		right_sequence = fasta_object.fetch_sequence(rname, min_end_position,
			max_end_position - 1).upper()
		assert max_end_position >= min_end_position and \
			max_start_position >= max_end_position
		# For computing z-scores
		mean_start_position = np.mean(start_positions)
		mean_end_position = np.mean(end_positions)
		# Maxes below avoid future ZeroDivisionError exceptions
		stdev_start_position = max(np.stdev(start_positions), 1e-6)
		stdev_end_position = max(np.stdev(end_positions), 1e-6)
		# Initialize list for storing ranked intron start/end positions
		ranked_introns = []
		for motif in motifs:
			z_scores_and_positions = []
			'''Use regex lookahead to identify possibly overlapping motifs.
			Each *_offset record offset from beginning of left_sequence or
			right_sequence.'''
			left_motif_offsets = [a_match.start() for a_match in 
									re.finditer(r'(?=(%s))' % motif[0],
													left_sequence)]
			right_motif_offsets = [a_match.start() for a_match in 
									re.finditer(r'(?=(%s))' % motif[1],
													right_sequence)]
			'''Find all possible combinations of left and right offsets for a
			given motif (pair).'''
			motif_pairs = \
				itertools.product(*[left_motif_offsets, right_motif_offsets])
			for left_motif_offset, right_motif_offset in motif_pairs:
				left_motif_start_position = min_start_position \
					+ left_motif_offset
				right_motif_end_position = min_end_position \
					+ right_motif_offset + 2
				z_score_sum = abs(left_motif_start_position 
					- mean_start_position) / float(stdev_start_position) \
					+ abs(right_motif_end_position - mean_end_position) / \
					float(stdev_end_position)
				z_scores_and_positions.append((left_motif_start_position,
												right_motif_end_position,
												z_score_sum))
			z_scores_and_positions.sort(lambda _, _, z_score_sum: z_score_sum)
			ranked_introns += (z_scores_and_positions + motif)
		if len(ranked_introns) == 0 and verbose:
			print >>sys.stderr, \
				'Warning: Cluster with %d candidate introns ' \
				'had no splice site' % len(intron_cluster)
		return ranked_introns

def go(reference_fasta, input_stream=sys.stdin, output_stream=sys.stdout,
	bin_size=10000, cluster_radius=5, per_site=False, per_span=True,
	output_bed=True, intron_partition_overlap=20, verbose=False):
	fasta_object = fasta.fasta(reference_fasta)
	input_line_count = 0
	junction_number = 0
	handle_partition = False
	last_partition_id = None
	candidate_introns = {}
	while True:
		line = input_stream.readline()
		if line:
			input_line_count += 1
			tokens = line.rstrip().split('\t')
			assert len(tokens) == 6
			(partition_id, sample_label, pos, end_pos, five_prime_displacement,
				three_prime_displacement) = tokens
			(pos, end_pos, five_prime_displacement,
				three_prime_displacement) = (int(pos), int(end_pos),
												int(five_prime_displacement),
												int(three_prime_displacement))
			assert end_pos > pos
			rname, partition_start, partition_end = \
				partition.parse(partition_id[:-1], bin_size)
			reverse_strand_string = partition_id[-1]
			reverse_strand = True if reverse_strand_string == '-' else False
			assert pos > partition_start - intron_partition_overlap and \
				pos < partition_end + intron_partition_overlap, \
				'Intron start %d is not in partition [%d, %d), partition id=' \
				% (pos, partition_start, partition_end, partition_id)
			if last_partition_id is not None and \
				last_partition_id != partition_id:
				handle_partition = True
		else:
			# If there's no next line, handle the final partition
			handle_partition = True
		if handle_partition:
			intron_clusters = intron_clusters_in_partition(candidate_introns,
				last_partition_start, last_partition_end, 
				cluster_radius=cluster_radius,
				verbose=verbose)
			cluster_splice_sites = []
			if last_reverse_strand:
				for intron_cluster in intron_clusters:
					# Pick top-ranked intron
					cluster_splice_sites.append(
						ranked_splice_sites_from_cluster(
							fasta_object, intron_cluster, last_rname,
							_reverse_strand_motifs, verbose=verbose
						)[0]
					)
			else:
				for intron_cluster in intron_clusters:
					cluster_splice_sites.append(
						ranked_splice_sites_from_cluster(
							fasta_object, intron_cluster, last_rname,
							_forward_strand_motifs, verbose=verbose
						)[0]
					)
			if per_span:
				for i, (start_position, end_position, z_score_sum, left_motif,
					right_motif) in enumerate(cluster_splice_sites):
					for _, _, sample_label, _, _ in intron_clusters[i]:
						print >>output_stream, 'span\t%s\t%d\t%d\t%s\t%s\t%s' \
							% (last_rname, start_position, end_position, 
								left_motif, right_motif, sample_label)
			if per_site:
				for i, (start_position, end_position, z_score_sum, left_motif,
					right_motif) in enumerate(cluster_splice_sites): 
					sample_label_counts = defaultdict(int)
					for _, _, sample_label, _, _ in intron_clusters[i]:
						sample_label_counts[sample_label] += 1
					for sample_label in sample_label_counts:
						print >>output_stream, \
							'site\t%s\t%d\t%d\t%s\t%s\t%s\t%s' \
							% (last_rname, start_position, end_position, 
								left_motif, right_motif, sample_label, 
								sample_label_counts[sample_label])
			if output_bed:
				'''The output bed mimics TopHat's junctions.bed. See TopHat
				documentation for more information.'''
				for i, (start_position, end_position, z_score_sum, left_motif,
					right_motif) in enumerate(cluster_splice_sites):
					'''Identify longest overhangs on either side of splice
					junction.'''
					left_overhang, right_overhang = 0
					for (candidate_start_position, candidate_end_position,
							_, five_prime_displacement,
							three_prime_displacement) in intron_clusters[i]:
						left_overhang = max(start_position \
										- candidate_start_position \
										+ five_prime_displacement, 
												left_overhang)
						right_overhang = max(candidate_end_position \
										 	 - end_position \
										 	 + three_prime_displacement,
										 	 	right_overhang)
					junction_number += 1
					'''Print line of bed file; where a first column 'junction'
					is inserted so it can be distinguished from other types of
					output lines.'''
					left_pos = start_position - left_overhang
					right_pos = end_position + right_overhang
					print >>output_stream, \
						'junction\t%s\t%d\t%d\tJUNC%08d\t%d\t%s\t%d\t%d\t' \
						'255,0,0\t2\t%d,%d\t0,%d' \
						% (last_rname, left_pos, right_pos, junction_number,
							len(intron_clusters[i]),
							last_reverse_strand_string, left_pos, right_pos,
							left_overhang, right_overhang, end_position)
			candidate_introns = {}
			handle_partition = False
		if line:
			candidate_introns[(pos, end_pos)] = (sample_label,
				five_prime_displacement, three_prime_displacement)
			(last_partition_id, last_partition_start, last_partition_end, 
				last_rname, last_reverse_strand, last_reverse_strand_string) \
			= (partition_id, partition_start, partition_end, rname, 
				reverse_strand)
		else: break

# "Main"
if not args.test:
	go(args.refseq,
		bin_size=args.partition_length,
		cluster_radius=args.cluster_radius,
		per_site=args.per_site,
		per_span=args.per_span,
		output_bed=args.output_bed,
		intron_partition_overlap=args.intron_partition_overlap,
		verbose=args.verbose)

		sys.stdin, sys.stdout, args.verbose, args.refseq)
else:
	# Test units
    del sys.argv[1:] # Don't choke on extra command-line parameters
    import unittest

