import xml.etree.ElementTree as ET
import sys, os, subprocess
import argparse
import pandas as pd
import numpy as np
import logging
import time
import shlex
import threading
from multiprocessing import Pool, cpu_count
import re
import json

###############################################################################
# Logging Setup
###############################################################################

def setup_logging(verbose=False):
    """
    Set up logging configuration. DEBUG level if verbose, else INFO.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

###############################################################################
# Output Streaming with 10s Buffer
###############################################################################

def buffered_stream_output(pipe, logger, log_level=logging.INFO, flush_interval=1.0):
    """
    Reads lines from 'pipe' and logs them every 'flush_interval' seconds.
    All lines are flushed at the end, ensuring none are skipped.
    """
    buffer = []
    last_flush = time.time()

    try:
        for line in iter(pipe.readline, ''):
            # Some commands produce empty lines occasionally; don't skip them
            buffer.append(line)

            # Flush if we've exceeded the interval
            if (time.time() - last_flush) >= flush_interval:
                for msg in buffer:
                    logger.log(log_level, msg.rstrip('\n'))
                buffer.clear()
                last_flush = time.time()

        # Final flush in case anything’s left
        for msg in buffer:
            logger.log(log_level, msg.rstrip('\n'))
        buffer.clear()

    finally:
        pipe.close()

###############################################################################
# Immediate Stream Output
###############################################################################

def immediate_stream_output(pipe, logger, log_level=logging.INFO):
    try:
        for line in iter(pipe.readline, ''):
            logger.log(log_level, line.rstrip('\n'))
    finally:
        pipe.close()

###############################################################################
# Pre-Select Candidates based on JSON Configuration
###############################################################################

def apply_folding_configuration(df: pd.DataFrame, config_file: str) -> pd.DataFrame:
    """
    Filter candidates from the dataframe based on the folding configuration
    specified in the JSON config file.

    The configuration file is expected to have the following structure:
    {
        "first_run": [
            {
                "spin_period": {"min": X, "max": Y},
                "dm": {"min": X, "max": Y},
                "fft_snr": {"min": X, "max": Y},
                "nh": {"min": X, "max": Y},
                "acc": {"min": X, "max": Y},
                "total_cands_limit": N
            },
            ...
        ]
    }

    For each filter, rows in `df` are selected if:
      - period is between spin_period.min and spin_period.max,
      - dm is between dm.min and dm.max,
      - snr is between fft_snr.min and fft_snr.max,
      - nh is between nh.min and nh.max,
      - acc is between acc.min and acc.max.

    Only up to total_cands_limit rows are selected per filter.
    The filtered candidates from all filters are then concatenated and duplicates dropped.

    Args:
        df: DataFrame containing candidate data.
        config_file: Path to JSON configuration file.
    
    Returns:
        A DataFrame with pre-selected candidates.
    """
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Assuming one group key; e.g., "first_run"
    group_key = list(config.keys())[0]
    filters = config[group_key]

    
    filtered_dfs = []
    for filter_def in filters:
        # Apply filter conditions
        sel = df.loc[
            (df['period'].between(filter_def['spin_period']['min'], filter_def['spin_period']['max'])) &
            (df['dm'].between(filter_def['dm']['min'], filter_def['dm']['max'])) &
            (df['snr'].between(filter_def['fft_snr']['min'], filter_def['fft_snr']['max'])) &
            (df['nh'].between(filter_def['nh']['min'], filter_def['nh']['max'])) &
            (df['acc'].between(filter_def['acc']['min'], filter_def['acc']['max']))
        ]
        logging.info(f"Filter {filter_def} selected {len(sel)} candidates.")
        # Limit to the desired number of candidates
        limit = filter_def.get('total_cands_limit', None)
        if limit is not None and len(sel) > limit:
            logging.info(f"Filter {filter_def} returned more candidates than the limit {limit}. Truncating to {limit} for folding.")
            sel = sel.head(limit)
        
        
        filtered_dfs.append(sel)
    
    if filtered_dfs:
        # Concatenate and drop duplicate candidates (assuming cand_id_in_file is unique)
        df_filtered = pd.concat(filtered_dfs)
        logging.info(f"Total candidates after Concatenation: {len(df_filtered)}")
        df_filtered = df_filtered.drop_duplicates(subset='cand_id_in_file')
        df_filtered = df_filtered.sort_values(by='cand_id_in_file')
        logging.info(f"Total candidates after dropping duplicates: {len(df_filtered)}")
        return df_filtered
    else:
        return df





###############################################################################
# PulsarX Candidate File
###############################################################################

def generate_pulsarX_cand_file(cand_mod_frequencies, cand_dms, cand_accs, cand_snrs):
    cand_file_path = 'pulsarx.candfile'
    with open(cand_file_path, 'w') as f:
        f.write("#id DM accel F0 F1 F2 S/N\n")
        for i in range(len(cand_mod_frequencies)):
            f.write("%d %f %f %f 0 0 %f\n" % (i, cand_dms[i], cand_accs[i], cand_mod_frequencies[i], cand_snrs[i]))

    return cand_file_path

###############################################################################
# Period Correction for PulsarX
###############################################################################

def period_correction_for_pulsarx(p0, pdot, no_of_samples, tsamp, fft_size):
    return p0 - pdot * float(fft_size - no_of_samples) * tsamp / 2

def period_correction_for_prepfold(p0, pdot, tsamp, fft_size):
    return p0 - pdot * float(fft_size) * tsamp / 2

def a_to_pdot(P_s, acc_ms2):
    LIGHT_SPEED = 2.99792458e8
    return P_s * acc_ms2 / LIGHT_SPEED

###############################################################################
# Folding with Presto
###############################################################################

def run_prepfold(args):
    """
    args is a tuple:
      (row, filterbank_file, tsamp, fft_size, source_name_prefix, rfifind_mask, extra_args)
    """
    row, filterbank_file, tsamp, fft_size, source_name_prefix, rfifind_mask, extra_args = args
    fold_period, pdot, cand_id, dm = row
    output_filename = source_name_prefix + '_Peasoup_fold_candidate_id_' + str(int(cand_id) + 1)

    cmd = "prepfold -fixchi -noxwin -topo"

    # Slow search if period > 0.1s
    if fold_period > 0.1:
        cmd += " -slow"

    if rfifind_mask:
        cmd += f" -mask {rfifind_mask}"

    # Add the fundamental folding parameters
    cmd += " -p %.16f -dm %.2f -pd %.16f -o %s %s" % (fold_period, dm, pdot, output_filename, filterbank_file)

    # Append extra_args if provided
    if extra_args:
        cmd += f" {extra_args}"

    try:
        logging.debug(f"Running Presto command: {cmd}")
        subprocess.check_output(cmd, shell=True)
        return (True, cand_id)
    except subprocess.CalledProcessError as e:
        return (False, cand_id, str(e))

def fold_with_presto(df, filterbank_file, tsamp, fft_size, source_name_prefix,
                     prepfold_threads, rfifind_mask=None, extra_args=None):
    num_cores = min(prepfold_threads, len(df))

    period = df['period'].values
    acc = df['acc'].values
    pdot = a_to_pdot(period, acc)
    fold_period = period_correction_for_prepfold(period, pdot, tsamp, fft_size)

    merged_data = np.column_stack((fold_period, pdot, df['cand_id_in_file'].values, df['dm'].values))
    args_list = [
        (row, filterbank_file, tsamp, fft_size, source_name_prefix, rfifind_mask, extra_args)
        for row in merged_data
    ]

    pool = Pool(num_cores)
    results = pool.map(run_prepfold, args_list)
    pool.close()
    pool.join()

    for result in results:
        if not result[0]:  # If success is False
            logging.error(f"Error with candidate ID {result[1]}: {result[2]}")

###############################################################################
# Folding with PulsarX
###############################################################################

def fold_with_pulsarx(
    df, segment_start_sample, segment_nsamples, pepoch,
    total_nsamples, input_filenames, source_name_prefix,
    nbins_high, nbins_low, subint_length, nsubband, utc_beam,
    beam_name, pulsarx_threads, TEMPLATE, clfd_q_value,
    rfi_filter, cmask=None, start_fraction=None, end_fraction=None,
    extra_args=None, output_rootname=None, coherent_dm=0.0
):
    """
    Fold candidates with pulsarx (psrfold_fil). 
    'pepoch', 'start_fraction', and 'end_fraction' are either user-provided or derived.
    """

    cand_dms = df['dm'].values
    cand_accs = df['acc'].values
    cand_period = df['period'].values
    cand_freq = 1 / cand_period
    cand_snrs = df['snr'].values

    pulsarx_predictor = generate_pulsarX_cand_file(cand_freq, cand_dms, cand_accs, cand_snrs)

    nbins_string = "-b {} --nbinplan 0.01 {}".format(nbins_low, nbins_high)
    
    if output_rootname is None:
        output_rootname = utc_beam

    if 'ifbf' in beam_name:
        beam_tag = "--incoherent"
    elif 'cfbf' in beam_name:
        beam_tag = "-i {}".format(int(beam_name.strip("cfbf")))
    else:
        #pulsarx does not take strings as beam names
        numeric_part = re.search(r'\d+$', beam_name).group()
        beam_tag = "-i {}".format(numeric_part)
      
    zap_string = ""
    if cmask is not None:
        cmask = cmask.strip()
        if cmask:
            try:
                zap_string = " ".join(["--rfi zap {} {}".format(*i.split(":")) for i in cmask.split(",")])
            except Exception as error:
                raise Exception(f"Unable to parse channel mask: {error}")

    if rfi_filter:
        additional_flags = f"--rfi {rfi_filter}"
    else:
        additional_flags = ""

    # Build the base command
    script = (
        "psrfold_fil2 -v --render --output_width --cdm {} -t {} --candfile {} -n {} {} {} --template {} "
        "--clfd {} -L {} -f {} {} -o {} --srcname {} --pepoch {} --frac {} {} {}"
    ).format(
        coherent_dm,
        pulsarx_threads,
        pulsarx_predictor,
        nsubband,
        nbins_string,
        beam_tag,
        TEMPLATE,
        clfd_q_value,
        subint_length,
        input_filenames,
        zap_string,
        output_rootname,
        source_name_prefix,
        pepoch,
        start_fraction,
        end_fraction,
        additional_flags
    )

    # Append extra_args if provided
    if extra_args:
        script += f" {extra_args}"

    logging.debug(f"Running PulsarX command: {script}")
    
    
    process = subprocess.Popen(
        shlex.split(script),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # line-buffered
    )

    # Two threads, one for stdout (INFO level), one for stderr (WARNING level)
    stdout_thread = threading.Thread(
        target=buffered_stream_output,
        args=(process.stdout, logging.getLogger(), logging.INFO, 10.0),
        daemon=True
    )
    stderr_thread = threading.Thread(
        target=buffered_stream_output,
        args=(process.stderr, logging.getLogger(), logging.WARNING, 10.0),
        daemon=True
    )

    stdout_thread.start()
    stderr_thread.start()

    stdout_thread.join()
    stderr_thread.join()

    return_code = process.wait()

    if return_code != 0:
        logging.error(f"psrfold_fil2 returned non-zero exit status {return_code}")
        sys.exit(1)

###############################################################################
# Main
###############################################################################

def main():
    parser = argparse.ArgumentParser(description='Fold all candidates from Peasoup xml file')
    parser.add_argument('-o', '--output_path', help='Output path to save results',
                        default=os.getcwd(), type=str)
    parser.add_argument('-r', '--output_rootname', help='Output rootname for each candidate',
                        default=None, type=str)
    parser.add_argument('-i', '--input_file', help='Name of the input xml file',
                        type=str)
    parser.add_argument('-m', '--mask_file', help='Mask file for prepfold', type=str)
    parser.add_argument('-t', '--fold_technique', help='Technique to use for folding (presto or pulsarx)',
                        type=str, default='pulsarx')
    parser.add_argument('-u', '--nbins_high', help='Upper profile bin limit for slow-spinning pulsars',
                        type=int, default=128)
    parser.add_argument('-l', '--nbins_low', help='Lower profile bin limit for fast-spinning pulsars',
                        type=int, default=64)
    parser.add_argument('-sub', '--subint_length', help='Subint length (s). Default is tobs/64',
                        type=int, default=None)
    parser.add_argument('-nsub', '--nsubband', help='Number of subbands',
                        type=int, default=64)
    parser.add_argument('-clfd', '--clfd_q_value', help='CLFD Q value',
                        type=float, default=2.0)
    parser.add_argument('-rfi', '--rfi_filter', help='RFI filter value',
                        type=str, default=None)
    parser.add_argument('-b', '--beam_name', help='Beam name string',
                        type=str, default='cfbf00000')
    parser.add_argument('-utc', '--utc_beam', help='UTC beam name string',
                        type=str, default='2024-01-01-00:00:00')
    parser.add_argument('-c', '--chan_mask', help='Peasoup Channel mask file to be passed onto pulsarx',
                        type=str, default='')
    parser.add_argument('-threads', '--pulsarx_threads', help='Number of threads to be used for pulsarx',
                        type=int, default=24)
    parser.add_argument('-pthreads', '--presto_threads', help='Number of threads to be used for prepfold',
                        type=int, default=12)
    parser.add_argument('-p', '--pulsarx_fold_template', help='Fold template pulsarx',
                        type=str, default='meerkat_fold.template')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose (DEBUG) logging')
    parser.add_argument('-f', '--filterbank_publish_dir', help='Optional Path to filterbank publish directory. If None, use dir in XML file',
                        type=str, default=None)
    parser.add_argument('--config_file', type=str, help="Path to JSON configuration file to pre-select candidates to fold.", default=None)
    parser.add_argument('--filtered_candidates_file', type=str, default="filtered_df_for_folding.csv",
                    help="Path to CSV file for pre-selected candidates for folding.")
    # New arguments for pepoch, start_frac, end_frac overrides, and extra arguments
    parser.add_argument('--pepoch_override', type=float, default=None,
                        help='Override Pepoch value. If not provided, read from XML.')
    parser.add_argument('--start_frac', type=float, default=None,
                        help='Override start fraction [0..1]. If not provided, computed from XML data.')
    parser.add_argument('--end_frac', type=float, default=None,
                        help='Override end fraction [0..1]. If not provided, computed from XML data.')
    parser.add_argument('--extra_args', type=str, default=None,
                        help='Extra arguments to pass to prepfold or psrfold_fil.')
    parser.add_argument('--cdm', type=float, default=0.0,
                        help='Coherent DM to use for folding. Default is 0.0.')

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    if not args.input_file:
        logging.error("You need to provide an XML file to read.")
        sys.exit(1)

    xml_file = args.input_file
    tree = ET.parse(xml_file)
    root = tree.getroot()

    header_params = root[1]
    search_params = root[2]
    segment_params = root[3]
    candidates = root[7]

    # Read from XML
    prepfold_threads = args.presto_threads
    filterbank_file = str(search_params.find("infilename").text)
    tsamp = float(header_params.find("tsamp").text)
    fft_size = int(search_params.find("size").text)
    total_nsamples = int(root.find("header_parameters/nsamples").text)
    source_name_prefix = str(header_params.find("source_name").text).strip()

    segment_start_sample = int(segment_params.find('segment_start_sample').text)
    segment_nsamples = int(segment_params.find('segment_nsamples').text)
    xml_segment_pepoch = float(segment_params.find('segment_pepoch').text)

    # Decide which pepoch to use
    if args.pepoch_override is not None:
        segment_pepoch = args.pepoch_override
        logging.info(f"Using user-provided pepoch = {segment_pepoch}")
    else:
        segment_pepoch = xml_segment_pepoch
        logging.info(f"Using pepoch from XML = {segment_pepoch}")

    # If user hasn't supplied explicit start_frac / end_frac, compute from XML data
    if args.start_frac is not None:
        user_start_fraction = args.start_frac
        logging.info(f"Using user-provided start_frac = {user_start_fraction}")
    else:
        user_start_fraction = round(segment_start_sample / total_nsamples, 3)
        logging.info(f"Using start_frac derived from XML = {user_start_fraction}")

    if args.end_frac is not None:
        user_end_fraction = args.end_frac
        logging.info(f"Using user-provided end_frac = {user_end_fraction}")
    else:
        user_end_fraction = round((segment_start_sample + segment_nsamples) / total_nsamples, 3)
        logging.info(f"Using end_frac derived from XML = {user_end_fraction}")

    effective_tobs = tsamp * segment_nsamples

    ignored_entries = [
        'candidate', 'opt_period', 'folded_snr', 'byte_offset', 'is_adjacent',
        'is_physical', 'ddm_count_ratio', 'ddm_snr_ratio'
    ]
    rows = []
    for candidate in candidates:
        cand_dict = {}
        for cand_entry in candidate.iter():
            if cand_entry.tag not in ignored_entries:
                cand_dict[cand_entry.tag] = cand_entry.text
        cand_dict['cand_id_in_file'] = candidate.attrib.get("id")
        rows.append(cand_dict)

    df = pd.DataFrame(rows)
    if args.filterbank_publish_dir:
        filterbank_publish_dir = args.filterbank_publish_dir
    else:
        filterbank_publish_dir = os.path.dirname(filterbank_file)
    
    publish_filterbank_file = os.path.join(filterbank_publish_dir, os.path.basename(filterbank_file))
    df['filterbank_file'] = publish_filterbank_file
    df = df.astype({"snr": float, "dm": float, "period": float, "nh": int, "acc": float, "nassoc": int, "cand_id_in_file": int})

    # If a config file is provided, filter the dataframe accordingly
    if args.config_file:
        logging.info(f"XML file contains {len(df)} candidates before filtering.")
        logging.info(f"Applying folding configuration from {args.config_file}")
        df = apply_folding_configuration(df, args.config_file)
        logging.info(f"After filtering, {len(df)} candidates remain for folding.")
    else:
        logging.info(f"No configuration file provided, folding all {len(df)} candidates.")
    
    
    #Dump the candidates selected for folding to a CSV
    logging.info(f"Dumping the selected candidates to filtered_df_for_folding.csv")
    df.to_csv(args.filtered_candidates_file, index=False, float_format='%.18f')

    
    PulsarX_Template = args.pulsarx_fold_template

    if args.fold_technique == 'presto':
        logging.info("Folding with Presto...")
        fold_with_presto(
            df,
            filterbank_file,
            tsamp,
            fft_size,
            source_name_prefix,
            prepfold_threads,
            rfifind_mask=args.mask_file,
            extra_args=args.extra_args
        )
    else:
        logging.info("Folding with PulsarX...")
        if args.subint_length is None:
            subint_length = int(effective_tobs / 64)
        else:
            subint_length = args.subint_length

        fold_with_pulsarx(
            df,
            segment_start_sample,
            segment_nsamples,
            segment_pepoch,
            total_nsamples,
            filterbank_file,
            source_name_prefix,
            args.nbins_high,
            args.nbins_low,
            subint_length,
            args.nsubband,
            args.utc_beam,
            args.beam_name,
            args.pulsarx_threads,
            PulsarX_Template,
            args.clfd_q_value,
            args.rfi_filter,
            cmask=args.chan_mask,
            start_fraction=user_start_fraction,
            end_fraction=user_end_fraction,
            extra_args=args.extra_args,
            output_rootname=args.output_rootname,
            coherent_dm=args.cdm
        )

if __name__ == "__main__":
    main()
