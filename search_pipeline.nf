nextflow.enable.dsl=2

// Define a function to generate UUID
def generateUUID() {
    UUID.randomUUID().toString()
}

process filtool {
    label 'filtool'
    container "${params.apptainer_images.pulsarx}"
    errorStrategy 'ignore'

    input:
    tuple val(process_uuid), val(program_args), val(filtool_id), val(target_name), val(pipeline_id), val(hardware_id), val(pointing_id), val(beam_name), val(beam_id), val(coherent_dm), val(input_dp), val(input_dp_id), val(process_input_dp_id), val(output_dp)

    output:
    tuple path(output_dp), env(output_dp_id), val(beam_name), val(beam_id), val(coherent_dm), env(tsamp), env(tobs), env(nsamples), env(freq_start_mhz), env(freq_end_mhz), env(tstart), env(tstart_utc), env(nchans), env(nbits)


    script:
    """
    #!/bin/bash
    tmp_output_dp="${output_dp}"
    filtool_output_string=\${tmp_output_dp%_01.fil}
    filtool -t ${program_args.threads} --nbits ${program_args.nbits} --mean ${program_args.mean} --std ${program_args.std} --td ${program_args.time_decimation_factor} --fd ${program_args.freq_decimation_factor} --telescope ${program_args.telescope} -z ${program_args.rfi_filter} -o \$filtool_output_string -s ${target_name} -f ${input_dp} ${program_args.extra_args}

    # Get the metadata from the output file and store it in the environment variables
    while IFS='=' read -r key value
        do
            declare "\$key=\$value"
        done < <(python ${program_args.get_metadata} -f ${output_dp})

    # Generate a UUID for the output file
    output_dp_id=\$(uuidgen)

    """
}

process peasoup {
    label 'peasoup'
    container params.apptainer_images.peasoup
    errorStrategy 'ignore'

    input:
    tuple val(process_uuid), 
          val(program_args), 
          val(peasoup_id), 
          val(input_dp), 
          val(input_dp_id), 
          val(process_input_dp_id), 
          val(utc_start),
          val(beam_name),
          val(beam_id), 
          val(coherent_dm), 
          val(peasoup_orig_xml),
          val(output_dp), 
          val(pipeline_id), 
          val(hardware_id),
          val(target_name)
    
    output:
    tuple path(output_dp), env(output_dp_id)

    publishDir "/b/PROCESSING/02_SEARCH/${target_name}/${utc_start}/${beam_name}/${input_dp.baseName}/${program_args.fft_size}/${program_args.start_sample}", mode: 'copy'
    script:
    """
    # Write out dm_file.txt
    python -c "import numpy as np; dm_trials = np.arange(${program_args.dm_start}, ${program_args.dm_end}, ${program_args.dm_step}); f=open('dm_file.txt','w'); f.writelines(f'{dm}\\n' for dm in dm_trials); f.close()"

    # Accumulate optional arguments
    optional_args=""

    if [ "${program_args.birdie_list}" != "null" ]; then
        optional_args="\${optional_args} -z ${program_args.birdie_list}"
    fi

    if [ "${program_args.chan_mask}" != "null" ]; then
        optional_args="\${optional_args} -k ${program_args.chan_mask}"
    fi

    if [ "${program_args.nsamples}" != "null" ]; then
        optional_args="\${optional_args} --nsamples ${program_args.nsamples}"
    fi

    if [ "${program_args.extra_args}" != "null" ]; then
        optional_args="\${optional_args} ${program_args.extra_args}"
    fi
    output_dir="peasoup_results"
    mkdir -p \${output_dir}
    # Run peasoup
    peasoup -i ${input_dp} \
    --acc_start ${program_args.acc_start} \
    --acc_end ${program_args.acc_end} \
    --acc_pulse_width ${program_args.acc_pulse_width} \
    --acc_tol ${program_args.accel_tol} \
    --dm_pulse_width ${program_args.dm_pulse_width} \
    -m ${program_args.min_snr} \
    --ram_limit_gb ${program_args.ram_limit_gb} \
    --nharmonics ${program_args.nharmonics} \
    -t ${program_args.ngpus} \
    --limit ${program_args.total_cands_limit} \
    --fft_size ${program_args.fft_size} \
    --start_sample ${program_args.start_sample} \
    --cdm ${program_args.coherent_dm} \
    \${optional_args} \
    --dm_file dm_file.txt \
    -o \${output_dir}/
    # Generate a UUID for the output file
    output_dp_id=\$(uuidgen)
  
    # Generate a UUID for each search candidate to insert into the database. Dump this to a new XML file.
    python ${params.kafka.save_search_candidate_uuid} -i ${peasoup_orig_xml}

    """
}



workflow {
    // Extract 'filtool' object from pipeline config JSON
    def filtool_prog = params.programs.find { it.program_name == 'filtool' }

    // Build a channel that emits one map per data product:
    // Each emitted value is a single Groovy map with all fields needed for the process.
   filtool_input = Channel.from( filtool_prog.data_products )
    .map { dp ->
        

        [
            process_uuid : generateUUID(),
            program_args : filtool_prog.arguments,
            program_id   : filtool_prog.program_id,
            target_name  : dp.target_name,
            pipeline_id  : params.pipeline_id,
            hardware_id  : dp.hardware_id,
            pointing_id  : dp.pointing_id,
            beam_name    : dp.beam_name,
            beam_id      : dp.beam_id,
            coherent_dm  : dp.coherent_dm,
            filenames    : dp.filenames,
            dp_id        : dp.dp_id.join(' '),
            processing_dp_id : dp.processing_dp_id.join(' '),
            output_dp    : "${dp.target_name}_${dp.beam_name}_${dp.coherent_dm}_01.fil"
        ]
    }

        
    
    // Run the filtool process on each emitted value in parallel
    filtool_output = filtool(filtool_input)

    // filtool_mapped emits one item per filtool result keyed by coherent_dm
    filtool_mapped = filtool_output.map { output_dp, output_dp_id, beam_name, beam_id, coherent_dm, tsamp, tobs, nsamples, freq_start_mhz, freq_end_mhz, tstart, tstart_utc, nchans, nbits ->
    [
        coherent_dm.toString(),
        [
            output_dp      : output_dp,
            output_dp_id   : output_dp_id,
            beam_name      : beam_name,
            beam_id        : beam_id,
            tsamp          : tsamp,
            tobs           : tobs,
            nsamples       : nsamples,
            freq_start_mhz : freq_start_mhz,
            freq_end_mhz   : freq_end_mhz,
            tstart         : tstart,
            tstart_utc     : tstart_utc,
            nchans         : nchans,
            nbits          : nbits
        ]
    ]
    }


    // Suppose peasoup_prog is a list of multiple entries all with coherent_dm=120.0
    def peasoup_prog = params.programs.findAll { it.program_name == 'peasoup' }

    // Emit multiple peasoup configs keyed by the same coherent_dm
    peasoup_input = Channel.from(peasoup_prog)
        .map { dp ->
            [ dp.arguments.coherent_dm.toString(), [
                program_args : dp.arguments,
                coherent_dm  : dp.arguments.coherent_dm,
                program_id   : dp.program_id
            ] ]
        }


    peasoup_input = filtool_mapped.combine(peasoup_input, by:0).map { coherent_dm, filtool_map, peasoup_map ->
        return [
            process_uuid     : generateUUID(),
            program_args     : peasoup_map.program_args,
            program_id       : peasoup_map.program_id,
            input_dp         : filtool_map.output_dp,
            input_dp_id      : filtool_map.output_dp_id,
            processing_dp_id : generateUUID(),
            utc_start        : filtool_map.tstart_utc,
            beam_name        : filtool_map.beam_name,
            beam_id          : filtool_map.beam_id,
            coherent_dm      : coherent_dm,
            peasoup_orig_xml : "peasoup_results/overview.xml",
            output_dp        : "output.xml",
            pipeline_id      : params.pipeline_id,
            hardware_id      : filtool_prog.data_products[0].hardware_id,
            target_name      : filtool_prog.data_products[0].target_name

        ]
    }
    peasoup(peasoup_input)

 
}

