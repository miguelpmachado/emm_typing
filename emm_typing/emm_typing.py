#!/usr/bin/env python3

import os
import sys
import re
import argparse
import csv
import pkg_resources
from subprocess import call

try:
    from __init__ import __version__
except ImportError:
    from emm_typing import __version__

from Bio.Blast.Applications import NcbiblastnCommandline

EMM_VERSION = __version__


def emm_argument_parser():
    parser = argparse.ArgumentParser(
        description='Group A streptococci emm-typer, version %s' % EMM_VERSION)
    parser.add_argument('-f', '--fasta',
                        help='FASTA file to type.', nargs='+', required=True, type=argparse.FileType('r'))
    parser.add_argument('--db',
                        help='Database for trimmed emm types. (If using non-default). It must be blastn database. Only'
                             ' provide the file that do not end with ".n*" something (do not use for example'
                             ' /blast_db.sequences.fasta.nhr)', required=False)
    parser.add_argument('-o', '--outdir',
                        help='Output directory where to write all results.',
                        default='.')
    parser.add_argument('-v', '--version',
                        help='Show version and exit.',
                        action='version',
                        version=EMM_VERSION)
    args = parser.parse_args()

    args.fasta = [os.path.abspath(fasta.name) for fasta in args.fasta]
    args.outdir = os.path.abspath(args.outdir)
    if not os.path.isdir(args.outdir):
        os.makedirs(args.outdir)
    if args.db is not None:
        args.db = os.path.abspath(args.db)
        if not os.path.isfile(args.db):
            sys.exit('Blast DB was not found')
        files = [f for f in os.listdir(os.path.dirname(args.db)) if
                 not f.startswith('.') and os.path.isfile(os.path.join(os.path.dirname(args.db), f)) and
                 f.startswith(os.path.basename(args.db))]
        for file_found in files:
            if os.path.islink(os.path.join(args.outdir, file_found)):
                os.remove(os.path.join(args.outdir, file_found))
            os.symlink(os.path.join(os.path.dirname(args.db), file_found),
                       os.path.join(args.outdir, file_found))
    else:
        # Create DB symbolic link to outdir (avoid permission problems)
        args.db = pkg_resources.resource_filename(__name__, os.path.join('data', 'trimmed_emm_types.tfa'))
        files = [f for f in pkg_resources.resource_listdir(__name__, os.path.join('data', '')) if
                 not f.startswith('.') and
                 pkg_resources.resource_exists(__name__, os.path.join('data', f)) and
                 f.startswith(os.path.basename(args.db))]
        for file_found in files:
            if os.path.islink(os.path.join(args.outdir, file_found)):
                os.remove(os.path.join(args.outdir, file_found))
            print(os.path.isfile(os.path.abspath(pkg_resources.resource_filename(__name__, os.path.join('data', file_found)))))
            os.symlink(os.path.abspath(pkg_resources.resource_filename(__name__, os.path.join('data', file_found))),
                       os.path.join(args.outdir, file_found))
        args.db = os.path.join(args.outdir, 'trimmed_emm_types.tfa')

    # print(__name__)
    # # print(resource_filename(__name__))
    # print(os.path.isfile(__name__))
    # print(pkg_resources.resource_filename(__name__, 'data/trimmed_emm_types.tfa'))
    # print(pkg_resources.resource_filename(__name__, 'data/trimmed_emm_types.tfa'))
    # print(os.path.isfile(pkg_resources.resource_filename(__name__, 'data/trimmed_emm_types.tfa')))
    # print(os.path.isfile(os.path.join(pkg_resources.resource_filename(__name__, 'data/trimmed_emm_types.tfa'))))
    # # print(os.path.join(resource_filename(__name__,), 'data', 'trimmed_emm_types.tfa'))
    # # print(os.path.isfile(os.path.join(resource_filename(__name__,), 'data', 'trimmed_emm_types.tfa')))
    # print(args.db)
    # print(os.listdir(os.path.join(pkg_resources.resource_filename(__name__, 'data/'))))
    # print(os.listdir(pkg_resources.resource_filename(__name__, 'data/')))
    # # print(os.path.abspath(os.path.join(resource_filename(__name__,), 'data', 'trimmed_emm_types.tfa')))
    # print(os.path.realpath(__file__))
    # print(os.path.abspath(__file__))
    # print(sys.argv[0])
    # print(os.path.abspath(sys.argv[0]))
    # print(os.path.realpath(sys.argv[0]))

    return args


def choose_best_match(lines):
    # Verify EMM <= 124
    # Length = 180
    # Pident = 100.0
    # For multiple bests, report in list
    matches = []
    unvalmatches = []
    for row in lines:
        contig = row[0]
        allele = row[1]
        pident = float(row[2])
        length = int(row[3])
        if allele.startswith("EMM"):
            alleleclean = re.match("^EMMG?(\d+)\.\d+$", allele).group(1)
            if not int(alleleclean) <= 124:
                # NOT a verified type
                if pident == 100 and length >= 180:
                    unvalmatches.append([contig, allele, pident, length])
            else:
                if pident == 100 and length >= 180:
                    newbest = [contig, allele, pident, length]
                    # matches.insert(0, newbest)
                    if len(matches) == 0:
                        # If no matches so far
                        matches.append(newbest)
                    else:
                        unvalmatches.append(newbest)
        else:
            if pident == 100 and length >= 180:
                matches.append([contig, allele, pident, length])

    if len(matches) > 0 or len(unvalmatches) > 0:
        return matches, unvalmatches
    else:
        return None, None


def main():
    args = emm_argument_parser()

    # Test isolate names
    for fasta in args.fasta:
        try:
            _ = re.match("^([\w_\-]+)\.(fasta|fa)$", os.path.basename(fasta)).group(1)
        except AttributeError as e:
            print(e)
            sys.exit("Could not understand isolatename for {} file.\n"
                     "Only a-z, A-Z, numbers, dash and underscore is allowed".format(os.path.basename(fasta)))

    # Sequentially BLAST all fastas against database
    for fasta in args.fasta:
        isolatename = re.match("^([\w_\-]+)\.(fasta|fa)$", os.path.basename(fasta)).group(1)
        assert isolatename

        blastn_cline = NcbiblastnCommandline(query=fasta, db=os.path.join(args.outdir, os.path.basename(args.db)),
                                             perc_identity=100, outfmt=6, max_target_seqs=10,
                                             out=os.path.join(args.outdir,
                                                              '{}_emm_results_blast.tab'.format(isolatename)))
        print(blastn_cline)
        call(blastn_cline(), shell=True)

    # Remove DB symbolic link
    files = [f for f in os.listdir(args.outdir) if
             not f.startswith('.') and os.path.islink(os.path.join(args.outdir, f)) and
             f.startswith(os.path.basename(args.db))]
    for file_found in files:
        os.remove(os.path.join(args.outdir, file_found))

    # Write all results to communal file (or alternatively, to stdout)
    with open(os.path.join(args.outdir, 'emm_results.tab'), 'w') as communalfile:
        header = ["Isolate", "contig", "emm-type", "pident", "length", "unvalidatedmatches"]
        communal = csv.writer(communalfile, delimiter="\t")
        communal.writerow(header)
        # communal.write("\t".join(header) + "\n")
        for fasta in args.fasta:
            isolatename = re.match("^([\w_\-]+)\.(fasta|fa)$", os.path.basename(fasta)).group(1)
            resfile = os.path.join(args.outdir, '{}_emm_results_blast.tab'.format(isolatename))
            with open(resfile, 'rU') as individual:
                ilines = csv.reader(individual, delimiter="\t")
                matches, unvalmatches = choose_best_match(ilines)

                if unvalmatches is not None:
                    unvalidatedmatches = [",".join([u[1] for u in unvalmatches])]
                else:
                    unvalidatedmatches = []

                if matches is not None:
                    matches = [matches[0]]
                else:
                    matches = []

                communal.writerow([isolatename] + matches + unvalidatedmatches)


if __name__ == '__main__':
    main()
