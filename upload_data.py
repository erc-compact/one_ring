import numpy as np
import pandas as pd
import sys, glob, re
import argparse
import os
from dotenv import load_dotenv
from sqlalchemy.engine import URL
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy import MetaData, Table, insert, select, text, func
from datetime import datetime, timezone
import hashlib
import decimal
import your
import subprocess
import uuid
import json
#from natsort import natsorted
# Load environment variables from .env file
load_dotenv()

# Postgres username, password, and database name
DB_SERVER = os.getenv("DB_HOST")  # Insert your DB address if it's not on Panoply
DB_PORT = os.getenv("DB_PORT")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")  # Change this to your Panoply/Postgres password
DBNAME = 'compact'  # Database name

connection_url = URL.create(
    "mysql+mysqlconnector", 
    username=DB_USERNAME, 
    password=DB_PASSWORD, 
    host=DB_SERVER, 
    database=DBNAME,
    port=DB_PORT
)
# Set up the engine and base
engine = create_engine(connection_url, echo=False)
metadata_obj = MetaData()
metadata_obj.reflect(bind=engine)

def get_table(table_name):
    return metadata_obj.tables[table_name]



def print_table(table_name):
    '''
    Print all rows in a given table
    '''
    table = get_table(table_name)
    with engine.connect() as conn:
        stmt = select(table)
        result = conn.execute(stmt)
        for row in result:
            print(row)

def delete_all_rows(table_name):
    
    table = get_table(table_name)
    with engine.connect() as conn:
        stmt = table.delete()
        conn.execute(stmt)
        conn.commit()
        print(f"Deleted all rows from {table_name} table")


def reset_primary_key_counter(table_name):

    with engine.connect() as conn:
        stmt = text(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
        conn.execute(stmt)
        conn.commit()
        print(f"Reset primary key counter for {table_name} table")

def insert_telescope_name(telescope_name, telescope_description=None, return_id=False):

    telescope_table = get_table("telescope")
    with engine.connect() as conn:
        stmt = select(telescope_table).where(telescope_table.c.name == telescope_name).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(telescope_table).values(name=telescope_name, description=telescope_description)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {telescope_name} to telescope table")
            if return_id:
                telescope_id = db_update.lastrowid
                return telescope_id
        else:
            print(f"{telescope_name} already exists in telescope table. Skipping...")
            if return_id:
                return result[0]

def insert_project_name(project_name, project_description=None, return_id=False):

    project_table = get_table("project")
    with engine.connect() as conn:
        stmt = select(project_table).where(project_table.c.name == project_name).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(project_table).values(name=project_name, description=project_description)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {project_name} to project table")
            if return_id:
                project_id = db_update.lastrowid
                return project_id
            
        else:
            print(f"{project_name} already exists in project table. Skipping...")
            if return_id:
                return result[0]

def insert_candidate_filter_name(candidate_filter_name, candidate_filter_description):

    cand_filter_table = get_table("candidate_filter")
    with engine.connect() as conn:
        stmt = select(cand_filter_table).where(cand_filter_table.c.name == candidate_filter_name).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(cand_filter_table).values(name=candidate_filter_name, description=candidate_filter_description)
            conn.execute(stmt)
            conn.commit()
            print(f"Added {candidate_filter_name} to candidate filter table")
        else:
            print(f"{candidate_filter_name} already exists in candidate filter table. Skipping...")


def insert_target_name(target_name, ra, dec, project_id, core_radius_arcmin_harris=None, core_radius_arcmin_baumgardt=None, half_mass_radius_arcmin_harris=None, half_mass_radius_arcmin_baumgardt=None, half_light_radius_arcmin_harris=None, half_light_radius_arcmin_baumgardt=None, description=None, return_id=False):
        
        '''
        Insert a new target into the target table if it doesn't already exist
        '''
    
        target_table = get_table("target")
        with engine.connect() as conn:
            stmt = select(target_table).where(target_table.c.target_name == target_name).where(target_table.c.ra == ra).where(target_table.c.dec == dec).where(target_table.c.project_id == project_id).limit(1)
            result = conn.execute(stmt).first()
            
            if result is None:
                stmt = insert(target_table).values(target_name=target_name, ra=ra, dec=dec, notes=description, project_id=project_id, core_radius_arcmin_harris=core_radius_arcmin_harris, core_radius_arcmin_baumgardt=core_radius_arcmin_baumgardt, half_mass_radius_arcmin_harris=half_mass_radius_arcmin_harris, half_mass_radius_arcmin_baumgardt=half_mass_radius_arcmin_baumgardt, half_light_radius_arcmin_harris=half_light_radius_arcmin_harris, half_light_radius_arcmin_baumgardt=half_light_radius_arcmin_baumgardt)
                db_update = conn.execute(stmt)
                conn.commit()
                print(f"Added {target_name} to target table")
                if return_id:
                    target_id = db_update.lastrowid
                    return target_id
            else:
                print(f"{target_name} already exists in target table. Skipping...")
                if return_id:
                    return result[0]

def insert_target_name_with_project_name(target_name, ra, dec, project_name, core_radius_arcmin_harris=None, core_radius_arcmin_baumgardt=None, half_mass_radius_arcmin_harris=None, half_mass_radius_arcmin_baumgardt=None, half_light_radius_arcmin_harris=None, half_light_radius_arcmin_baumgardt=None, description=None, return_id=False):
    
    '''
    Insert a new target into the target table if it doesn't already exist for the same project.
    A different ra and dec will trigger a new entry in the target table
    '''
   
    target_table = get_table("target")
    project_table = get_table("project")

    with engine.connect() as conn:
        #join target and project tables
        stmt = (select(target_table).join(project_table)
                .where(target_table.c.target_name == target_name)
                .where(target_table.c.ra == ra)
                .where(target_table.c.dec == dec)
                .where(project_table.c.name == project_name)
                .limit(1))
        result = conn.execute(stmt).first()
     
     
        if result is None:
            #get project id
            project_id = get_id_from_name("project", project_name)
            stmt = insert(target_table).values(target_name=target_name, ra=ra, dec=dec, notes=description, project_id=project_id, core_radius_arcmin_harris=core_radius_arcmin_harris, core_radius_arcmin_baumgardt=core_radius_arcmin_baumgardt, half_mass_radius_arcmin_harris=half_mass_radius_arcmin_harris, half_mass_radius_arcmin_baumgardt=half_mass_radius_arcmin_baumgardt, half_light_radius_arcmin_harris=half_light_radius_arcmin_harris, half_light_radius_arcmin_baumgardt=half_light_radius_arcmin_baumgardt)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {target_name} to target table")
            if return_id:
                target_id = db_update.lastrowid
                return target_id
        else:
            print(f"{target_name} already exists with the given coordinates in target table for project {project_name}. Skipping...")
            if return_id:
                return result[0]

def insert_pointing(utc_start_str, tobs, nchans, freq_band, target_id, freq_start_mhz, freq_end_mhz, tsamp_seconds, telescope_id, receiver_name=None, return_id=False):
    '''
    Insert a new pointing into the pointing table if it doesn't already exist.
    Every Pointing has a unique combination of target_id, utc_start, telescope_id, and freq_band
    Optionally return the pointing_id of the inserted or existing row when return_id is True.
    '''
    pointing_table = get_table("pointing")
    with engine.connect() as conn:
        utc_start = datetime.strptime(utc_start_str, '%Y-%m-%d-%H:%M:%S.%f')
        utc_start = utc_start.replace(microsecond=0)
        stmt = select(pointing_table).where(pointing_table.c.utc_start == utc_start).where(pointing_table.c.target_id == target_id).where(pointing_table.c.telescope_id == telescope_id).where(pointing_table.c.freq_band == freq_band).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(pointing_table).values(utc_start=utc_start, tobs=tobs, nchans_raw=nchans, freq_band=freq_band, target_id=target_id, freq_start_mhz=freq_start_mhz, freq_end_mhz=freq_end_mhz, tsamp_raw=tsamp_seconds, telescope_id=telescope_id, receiver=receiver_name)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added pointing for {target_id} observed at {utc_start} with telescope {telescope_id} to pointing table")
            if return_id:
                pointing_id = db_update.lastrowid
                return pointing_id
        else:
            print(f"Pointing for {target_id} at {utc_start} already exists in pointing table. Skipping...")
            if return_id:
                return result[0]



def insert_pointing_with_names(utc_start_str, tobs, nchans, freq_band, target_name, freq_start_mhz, freq_end_mhz, tsamp_seconds, telescope_name, receiver_name=None, return_id=False):
    '''
    Insert a new pointing into the pointing table if it doesn't already exist for the same target at the same UTC start time for the same project, telescope, and freq band.
    Optionally return the pointing_id of the inserted or existing row when return_id is True.
    '''

    pointing_table = get_table("pointing")
    target_table = get_table("target")
    telescope_table = get_table("telescope")
    
    utc_start = datetime.strptime(utc_start_str, '%Y-%m-%d-%H:%M:%S.%f')
    utc_start = utc_start.replace(microsecond=0)

    with engine.connect() as conn:
        stmt = (
            select(pointing_table.c.id)
            .join(target_table, target_table.c.id == pointing_table.c.target_id)
            .join(telescope_table, telescope_table.c.id == pointing_table.c.telescope_id)
            .where(target_table.c.target_name == target_name)
            .where(telescope_table.c.name == telescope_name)
            .where(pointing_table.c.utc_start == utc_start)
            .where(pointing_table.c.freq_band == freq_band)
            .limit(1)
        )

        result = conn.execute(stmt).first()

        if result is None:
            try:
                target_id = get_id_from_name("target", target_name, alternate_key='target_name')
            except:
                print(f"Target {target_name} does not exist in target table. Please add target first.")
                sys.exit()

            try:
                telescope_id = get_id_from_name("telescope", telescope_name)
            except:
                print(f"Telescope {telescope_name} does not exist in telescope table. Please add telescope first.")
                sys.exit()

            stmt = insert(pointing_table).values(
                utc_start=utc_start, tobs=tobs, nchan_raw=nchans, freq_band=freq_band,
                target_id=target_id, freq_start_mhz=freq_start_mhz, freq_end_mhz=freq_end_mhz,
                tsamp_raw=tsamp_seconds, telescope_id=telescope_id, receiver=receiver_name
            )
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added pointing for {target_name} observed at {utc_start} with telescope {telescope_name} to pointing table.")


            if return_id:
                pointing_id = db_update.lastrowid  # For MariaDB/MySQL, use lastrowid to get the last inserted 'id'
                return pointing_id
            
        else:
            print(f"Pointing for {target_name} at {utc_start} already exists in pointing table. Skipping...")
            if return_id:
                return result[0]  # Assuming the first column selected is the id


def get_id_from_name(table_name, name, alternate_key=None):
    '''
    Get the id for a given name in a given table
    '''
    table = get_table(table_name)  

    with engine.connect() as conn:
        if alternate_key is not None:
            # Check if alternate key is a valid column name in the table
            if alternate_key not in table.c:
                print(f"Alternate key {alternate_key} not found in table {table_name}")
                sys.exit()
            stmt = select(table).where(getattr(table.c, alternate_key) == name).limit(1)
        else:
            # Assuming 'name' is a column in the table, and you are searching for a record with this column equal to the 'name' value
            stmt = select(table).where(table.c.name == name).limit(1)
        
        try:
            result = conn.execute(stmt).first()
            return result[0]
        
        except:
            print(f"{name} does not exist in {table_name} table. Please add {name} first.")
            sys.exit()
        


def insert_beam_type(beam_type_name, description=None, return_id=False):
    '''
    Insert a new beam type into the beam_type table if it doesn't already exist
    '''
    beam_type_table = get_table("beam_type")

    with engine.connect() as conn:
        
        stmt = select(beam_type_table).where(beam_type_table.c.name == beam_type_name).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(beam_type_table).values(name=beam_type_name, description=description)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {beam_type_name} to beam_type table")
            if return_id:
                beam_type_id = db_update.lastrowid
                return beam_type_id
        else:
            print(f"{beam_type_name} already exists in beam_type table. Skipping...")
            if return_id:
                return result[0]

def get_pointing_id(target_name, utc_start_str, project_name, telescope_name, freq_band):
    '''
    Get the pointing id for a given target, project, telescope and utc_start
    '''
    
    pointing_table = get_table("pointing")
    target_table = get_table("target")
    project_table = get_table("project")
    telescope_table = get_table("telescope")
   
    
    utc_start = datetime.strptime(utc_start_str, '%Y-%m-%d-%H:%M:%S.%f')
    utc_start = utc_start.replace(microsecond=0)

    with engine.connect() as conn:
        #join target and project tables
        stmt = (
            select(pointing_table.c.id)
            .join(target_table, target_table.c.id == pointing_table.c.target_id)
            .join(project_table, project_table.c.id == target_table.c.project_id)
            .join(telescope_table, telescope_table.c.id == pointing_table.c.telescope_id)
            .where(target_table.c.target_name == target_name)
            .where(project_table.c.name == project_name)
            .where(telescope_table.c.name == telescope_name)
            .where(pointing_table.c.utc_start == utc_start)
            .where(pointing_table.c.freq_band == freq_band)
            .limit(1)
        )
        result = conn.execute(stmt).first()
        if result is None:
            return None
        else:
            return result[0]

def get_beam_id(beam_name, beam_ra_str, beam_dec_str, pointing_id, beam_type_id):
    '''
    Get the beam id for a given beam name, pointing id and beam type id
    '''
    beam_table = get_table("beam")
    with engine.connect() as conn:
        stmt = select(beam_table).where(beam_table.c.name == beam_name).where(beam_table.c.pointing_id == pointing_id).where(beam_table.c.beam_type_id == beam_type_id).where(beam_table.c.ra_str == beam_ra_str).where(beam_table.c.dec_str == beam_dec_str).limit(1)
        result = conn.execute(stmt).first()
        if result is None:
            return None
        else:
            return result[0]
    


def insert_beam(beam_name, beam_ra_str, beam_dec_str, pointing_id, beam_type_id, tsamp_seconds, is_coherent=1, return_id=False):
    '''
    Insert a new beam into the beams table if it doesn't already exist
    '''

    beam_table = get_table("beam")

    with engine.connect() as conn:
        stmt = select(beam_table.c.id).where(beam_table.c.name == beam_name).where(beam_table.c.pointing_id == pointing_id).where(beam_table.c.beam_type_id == beam_type_id).where(beam_table.c.is_coherent == is_coherent).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(beam_table).values(name=beam_name, ra_str=beam_ra_str, dec_str=beam_dec_str, pointing_id=pointing_id, beam_type_id=beam_type_id, tsamp=tsamp_seconds, is_coherent=is_coherent)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {beam_name} to beam table")
            if return_id:
                beam_id = db_update.lastrowid
                return beam_id
        else:
            print(f"{beam_name} already exists in beam table. Skipping...")
            if return_id:
                return result[0]  # Assuming the first column selected is the id


def insert_beam_without_pointing_id(beam_name, beam_ra_str, beam_dec_str, beam_type_name, utc_start_str, project_name, telescope_name, target_name, freq_band, tsamp_seconds, is_coherent=True, return_id=False):
    '''
    Insert a new beam into the beams table if it doesn't already exist.
    A combination of unique utc_start, project_name, telescope_name, freq_band, and target_name identifies a unique pointing.
    '''

    beam_table = get_table("beam")
    # Assuming get_pointing_id and get_id_from_name are utility functions that you've defined elsewhere
    utc_start = datetime.strptime(utc_start_str, '%Y-%m-%d-%H:%M:%S.%f')
    utc_start = utc_start.replace(microsecond=0)

    # Get Pointing ID
    pointing_id = get_pointing_id(target_name, utc_start_str, project_name, telescope_name, freq_band)

    # Get beam type ID
    beam_type_id = get_id_from_name("beam_type", beam_type_name)
  
    with engine.connect() as conn:
        stmt = select(beam_table.c.id).where(beam_table.c.name == beam_name).where(beam_table.c.pointing_id == pointing_id).where(beam_table.c.beam_type_id == beam_type_id).limit(1)
        result = conn.execute(stmt).first()
       
        if result is None:
            stmt = insert(beam_table).values(name=beam_name, ra_str=beam_ra_str, dec_str=beam_dec_str, pointing_id=pointing_id, beam_type_id=beam_type_id, tsamp=tsamp_seconds, is_coherent=is_coherent)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {beam_name} to beam table")
            if return_id:
                beam_id = db_update.lastrowid
                return beam_id
        else:
            print(f"{beam_name} already exists in beam table. Skipping...")
            if return_id:
                return result[0]  # Assuming the first column selected is the id


def insert_file_type(file_type_name, description=None, return_id=False):
    '''
    Insert a new file type into the file_types table if it doesn't already exist
    '''
    
    file_type_table = get_table("file_type")
    with engine.connect() as conn:
        
        stmt = select(file_type_table).where(file_type_table.c.name == file_type_name).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(file_type_table).values(name=file_type_name, description=description)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {file_type_name} to file_type table")
            if return_id:
                file_type_id = db_update.lastrowid
                return file_type_id
        else:
            print(f"{file_type_name} already exists in file_type table. Skipping...")
            if return_id:
                return result[0]

def insert_antenna(name, telescope_id, description=None, latitude_degrees=None, longitude_degrees=None, elevation_meters=None, return_id=False):
    '''
    Insert a new antenna into the antenna table if it doesn't already exist for the same telescope
    '''
    antenna_table = get_table("antenna")
    with engine.connect() as conn:
        stmt = (
                select(antenna_table)
                .where(antenna_table.c.name == name)
                .where(antenna_table.c.telescope_id == telescope_id)
                .limit(1)
            )
        result = conn.execute(stmt).first()
        if result is None:
            stmt = insert(antenna_table).values(name=name, description=description, telescope_id=telescope_id, latitude_degrees=latitude_degrees, longitude_degrees=longitude_degrees, elevation_meters=elevation_meters)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {name} to antenna table")
            if return_id:
                antenna_id = db_update.lastrowid
                return antenna_id
        else:
            print(f"{name} already exists in antenna table for telescope {telescope_name}. Skipping...")
            if return_id:
                return result[0]




def insert_antenna_with_names(name, telescope_name, description=None, latitude_degrees=None, longitude_degrees=None, elevation_meters=None, return_id=False):
    '''
    Insert a new antenna into the antenna table if it doesn't already exist for the same telescope
    '''
    
    antenna_table = get_table("antenna")
    telescope_table = get_table("telescope")
    with engine.connect() as conn:
            
            stmt = (
                select(antenna_table)
                .join(telescope_table, telescope_table.c.id == antenna_table.c.telescope_id)
                .where(antenna_table.c.name == name)
                .where(telescope_table.c.name == telescope_name)
                .limit(1)
            )
            result = conn.execute(stmt).first()
            
            if result is None:
                telescope_id = get_id_from_name("telescope", telescope_name)
                stmt = insert(antenna_table).values(name=name, description=description, telescope_id=telescope_id, latitude_degrees=latitude_degrees, longitude_degrees=longitude_degrees, elevation_meters=elevation_meters)
                db_update = conn.execute(stmt)
                conn.commit()
                print(f"Added {name} to antenna table")
                if return_id:
                    antenna_id = db_update.lastrowid
                    return antenna_id
            else:
                print(f"{name} already exists in antenna table for telescope {telescope_name}. Skipping...")
                if return_id:
                    return result[0]

def insert_hardware(hardware_name, job_scheduler=None, hardware_description=None, return_id=False):
    '''
    Insert a new hardware into the hardware table if it doesn't already exist
    '''
    
    hardware_table = get_table("hardware")
    with engine.connect() as conn:
        
        stmt = select(hardware_table).where(hardware_table.c.name == hardware_name).limit(1)
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(hardware_table).values(name=hardware_name, description=hardware_description, job_scheduler=job_scheduler)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {hardware_name} to hardware table")
            if return_id:
                hardware_id = db_update.lastrowid
                return hardware_id
        else:
            print(f"{hardware_name} already exists in hardware table. Skipping...")
            if return_id:
                return result[0]

def insert_pipeline(name, github_repo_name, github_commit_hash, github_branch, description=None, return_id = False):
    '''
    Insert a new pipeline into the pipeline table if it doesn't already exist
    '''
    
    pipeline_table = get_table("pipeline")
    with engine.connect() as conn:
        
        stmt = (select(pipeline_table)
        .where(pipeline_table.c.name == name)
        .where(pipeline_table.c.github_repo_name == github_repo_name)
        .where(pipeline_table.c.github_commit_hash == github_commit_hash)
        .where(pipeline_table.c.github_branch == github_branch)
         )
        result = conn.execute(stmt).first()
       
        if result is None:
            stmt = insert(pipeline_table).values(name=name, description=description, github_repo_name=github_repo_name, github_commit_hash=github_commit_hash, github_branch=github_branch)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {name} to pipeline table")
            if return_id:
                pipeline_id = db_update.lastrowid
                return pipeline_id
        else:
            print(f"{name} already exists in pipeline table. Skipping...")
            if return_id:
                return result[0]


def insert_pipeline_execution_order(pipeline_id, program_name, execution_order, peasoup_id=None, pulsarx_id=None, filtool_id=None, prepfold_id=None, circular_orbit_search_id=None, elliptical_orbit_search_id=None, rfifind_id=None):
    '''
    Insert a new pipeline execution order into the pipeline_execution_order table if it doesn't already exist
    '''
    
    pipeline_execution_order_table = get_table("pipeline_execution_order")
    with engine.connect() as conn:
        
        stmt = (select(pipeline_execution_order_table)
        .where(pipeline_execution_order_table.c.pipeline_id == pipeline_id)
        .where(pipeline_execution_order_table.c.program_name == program_name)
        .where(pipeline_execution_order_table.c.execution_order == execution_order)
        .where(pipeline_execution_order_table.c.peasoup_id == peasoup_id)
        .where(pipeline_execution_order_table.c.pulsarx_id == pulsarx_id)
        .where(pipeline_execution_order_table.c.filtool_id == filtool_id)
        .where(pipeline_execution_order_table.c.prepfold_id == prepfold_id)
        .where(pipeline_execution_order_table.c.circular_orbit_search_id == circular_orbit_search_id)
        .where(pipeline_execution_order_table.c.elliptical_orbit_search_id == elliptical_orbit_search_id)
        .where(pipeline_execution_order_table.c.rfifind_id == rfifind_id)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(pipeline_execution_order_table).values(pipeline_id=pipeline_id, program_name=program_name, execution_order=execution_order, peasoup_id=peasoup_id, pulsarx_id=pulsarx_id, filtool_id=filtool_id, prepfold_id=prepfold_id, circular_orbit_search_id=circular_orbit_search_id, elliptical_orbit_search_id=elliptical_orbit_search_id, rfifind_id=rfifind_id)
            conn.execute(stmt)
            conn.commit()
            print(f"Added {program_name} to pipeline_execution_order table")
        else:
            print(f"{program_name} already exists in pipeline_execution_order table. Skipping...")

def insert_peasoup(acc_start, acc_end, min_snr, ram_limit_gb, nharmonics, ngpus, total_cands_limit, fft_size, dm_file, container_image_name, container_image_version, container_type, container_image_id, accel_tol=1.11, birdie_list=None, chan_mask=None, extra_args=None, argument_hash=None, return_id=False):
    ''' Insert Peasoup parameters into the peasoup_params table if it doesn't already exist ''' 
    peasoup_table = get_table("peasoup")
    combined_args = f"{acc_start}{acc_end}{min_snr}{ram_limit_gb}{nharmonics}{ngpus}{total_cands_limit}{fft_size}{dm_file}{accel_tol}{birdie_list}{chan_mask}{extra_args}"
    # Generate SHA256 hash
    argument_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    
    with engine.connect() as conn:
            
        stmt = (
        select(peasoup_table)
        .where(peasoup_table.c.argument_hash == argument_hash)
        .where(peasoup_table.c.container_image_id == container_image_id)
        .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            
            stmt = insert(peasoup_table).values(acc_start=acc_start, acc_end=acc_end, min_snr=min_snr, ram_limit_gb=ram_limit_gb, nharmonics=nharmonics, ngpus=ngpus, total_cands_limit=total_cands_limit, fft_size=fft_size, dm_file=dm_file, accel_tol=accel_tol, birdie_list=birdie_list, chan_mask=chan_mask, extra_args=extra_args, container_image_name=container_image_name, container_image_version=container_image_version, container_type=container_type, container_image_id=container_image_id, argument_hash=argument_hash)
            db_update = conn.execute(stmt)
            conn.commit()
            peasoup_id = db_update.inserted_primary_key[0]
            print(f"Added Peasoup parameters to peasoup_params table")
            if return_id:
                return peasoup_id
            
            
        else:
            peasoup_id = result[0]
            print(f"Peasoup parameters already exist in peasoup_params table. Skipping...")
            if return_id:
                return peasoup_id
    

def insert_pulsarx(subbands_number, subint_length, clfd_q_value, fast_period_bins, slow_period_bins, rfi_filter, extra_args, threads, container_image_name, container_image_version, container_type, container_image_id, pipeline_github_commit_hash, execution_order, argument_hash=None, return_id=False):
    '''
    Insert PulsarX parameters into the pulsarx_params table if it doesn't already exist
    '''
    pulsarx_table = get_table("pulsarx")
    combined_args = f"{subbands_number}{subint_length}{clfd_q_value}{fast_period_bins}{slow_period_bins}{rfi_filter}{extra_args}{threads}"
    # Generate SHA256 hash
    argument_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    #Get pipeline id to add in execution order table
    pipeline_id = get_id_from_name("pipeline", pipeline_github_commit_hash, alternate_key='github_commit_hash')

    with engine.connect() as conn:
                
        stmt = (
        select(pulsarx_table)
        .where(pulsarx_table.c.argument_hash == argument_hash)
        .where(pulsarx_table.c.container_image_id == container_image_id)
        .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(pulsarx_table).values(subbands_number=subbands_number, subint_length=subint_length, clfd_q_value=clfd_q_value, fast_nbins=fast_period_bins, slow_nbins=slow_period_bins, rfi_filter=rfi_filter, extra_args=extra_args, threads=threads, container_image_name=container_image_name, container_image_version=container_image_version, container_type=container_type, container_image_id=container_image_id, argument_hash=argument_hash)
            db_update = conn.execute(stmt)
            conn.commit()
            pulsarx_id = db_update.inserted_primary_key[0]
            print(f"Added PulsarX parameters to pulsarx_params table")
            if return_id:
                return pulsarx_id
        else:
            pulsarx_id = result[0]
            print(f"PulsarX parameters already exist in pulsarx_params table. Skipping...")
            if return_id:
                return pulsarx_id
   
def insert_filtool(rfi_filter, telescope_name, threads, container_image, container_version, container_type, container_image_id, extra_args=None, return_id=False):
    '''
    Insert Filtool parameters into the filtool_params table if it doesn't already exist
    '''
    filtool_table = get_table("filtool")
    combined_args = f"{rfi_filter}{telescope_name}{threads}"
    # Generate SHA256 hash
    argument_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    #Get pipeline id to add in execution order table

    with engine.connect() as conn:
                    
        stmt = (
        select(filtool_table)
        .where(filtool_table.c.argument_hash == argument_hash)
        .where(filtool_table.c.container_image_id == container_image_id)
        .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(filtool_table).values(rfi_filter=rfi_filter, telescope_name=telescope_name, threads=threads, extra_args=extra_args, container_image_name=container_image, container_image_version=container_version, container_type=container_type, container_image_id=container_image_id, argument_hash=argument_hash)
            db_update = conn.execute(stmt)
            conn.commit()
            filtool_id = db_update.inserted_primary_key[0]
            print(f"Added Filtool parameters to filtool_params table")
            if return_id:
                return filtool_id
        else:
            filtool_id = result[0]
            print(f"Filtool parameters already exist in filtool_params table. Skipping...")
            if return_id:
                return filtool_id
    
def insert_prepfold(ncpus, rfifind_mask, extra_args, container_image, container_version, container_type, container_image_id, pipeline_github_commit_hash, execution_order, argument_hash=None, return_id=False):
    '''
    Insert Prepfold parameters into the prepfold_params table if it doesn't already exist
    '''
    prepfold_table = get_table("prepfold")
    combined_args = f"{ncpus}{extra_args}"
    # Generate SHA256 hash
    argument_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    #Get pipeline id to add in execution order table
    pipeline_id = get_id_from_name("pipeline", pipeline_github_commit_hash, alternate_key='github_commit_hash')

    with engine.connect() as conn:
                            
        stmt = (
        select(prepfold_table)
        .where(prepfold_table.c.argument_hash == argument_hash)
        .where(prepfold_table.c.container_image_id == container_image_id)
        .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(prepfold_table).values(ncpus=ncpus, rfifind_mask=rfifind_mask, extra_args=extra_args, container_image_name=container_image, container_image_version=container_version, container_type=container_type, container_image_id=container_image_id, argument_hash=argument_hash)
            db_update = conn.execute(stmt)
            conn.commit()
            prepfold_id = db_update.inserted_primary_key[0]
            print(f"Added Prepfold parameters to prepfold_params table")
            if return_id:
                return prepfold_id
        else:
            prepfold_id = result[0]
            print(f"Prepfold parameters already exist in prepfold_params table. Skipping...")
            if return_id:
                return prepfold_id
   
def insert_circular_orbit_search(min_porb_h, max_porb_h, min_pulsar_mass_m0, max_comp_mass_m0, min_orb_phase_rad, max_orb_phase_rad, coverage, mismatch, container_image_name, container_image_version, container_type, container_image_id, pipeline_github_commit_hash, execution_order, argument_hash=None, return_id=False):
    '''
    Insert Circular Orbit Search parameters into the circular_orbit_search_params table if it doesn't already exist
    '''
    circular_orbit_search_table = get_table("circular_orbit_search")
    combined_args = f"{min_porb_h}{max_porb_h}{min_pulsar_mass_m0}{max_comp_mass_m0}{min_orb_phase_rad}{max_orb_phase_rad}{coverage}{mismatch}"
    # Generate SHA256 hash
    argument_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    #Get pipeline id to add in execution order table
    pipeline_id = get_id_from_name("pipeline", pipeline_github_commit_hash, alternate_key='github_commit_hash')

    with engine.connect() as conn:
                                
        stmt = (
        select(circular_orbit_search_table)
        .where(circular_orbit_search_table.c.argument_hash == argument_hash)
        .where(circular_orbit_search_table.c.container_image_id == container_image_id)
        .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(circular_orbit_search_table).values(min_porb_h=min_porb_h, max_porb_h=max_porb_h, min_pulsar_mass_m0=min_pulsar_mass_m0, max_comp_mass_m0=max_comp_mass_m0, min_orb_phase_rad=min_orb_phase_rad, max_orb_phase_rad=max_orb_phase_rad, coverage=coverage, mismatch=mismatch, container_image_name=container_image_name, container_image_version=container_image_version, container_type=container_type, container_image_id=container_image_id, argument_hash=argument_hash)
            db_update = conn.execute(stmt)
            conn.commit()
            circular_orbit_search_id = db_update.inserted_primary_key[0]
            print(f"Added Circular Orbit Search parameters to circular_orbit_search_params table")
            if return_id:
                return circular_orbit_search_id
        else:
            circular_orbit_search_id = result[0]
            print(f"Circular Orbit Search parameters already exist in circular_orbit_search_params table. Skipping...")
            if return_id:
                return circular_orbit_search_id
    
def insert_elliptical_orbit_search(min_porb_h, max_porb_h, min_pulsar_mass_m0, max_comp_mass_m0, min_orb_phase_rad, max_orb_phase_rad, min_ecc, max_ecc, min_periastron_rad, max_periastron_rad, coverage, mismatch, container_image_name, container_image_version, container_type, container_image_id, pipeline_github_commit_hash, execution_order, argument_hash=None, return_id=False):
    '''
    Insert Elliptical Orbit Search parameters into the elliptical_orbit_search_params table if it doesn't already exist
    '''
    elliptical_orbit_search_table = get_table("elliptical_orbit_search")
    combined_args = f"{min_porb_h}{max_porb_h}{min_pulsar_mass_m0}{max_comp_mass_m0}{min_orb_phase_rad}{max_orb_phase_rad}{min_ecc}{max_ecc}{min_periastron_rad}{max_periastron_rad}{coverage}{mismatch}"
    # Generate SHA256 hash
    argument_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    #Get pipeline id to add in execution order table
    pipeline_id = get_id_from_name("pipeline", pipeline_github_commit_hash, alternate_key='github_commit_hash')

    with engine.connect() as conn:
                                    
        stmt = (
        select(elliptical_orbit_search_table)
        .where(elliptical_orbit_search_table.c.argument_hash == argument_hash)
        .where(elliptical_orbit_search_table.c.container_image_id == container_image_id)
        .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(elliptical_orbit_search_table).values(min_porb_h=min_porb_h, max_porb_h=max_porb_h, min_pulsar_mass_m0=min_pulsar_mass_m0, max_comp_mass_m0=max_comp_mass_m0, min_orb_phase_rad=min_orb_phase_rad, max_orb_phase_rad=max_orb_phase_rad, min_ecc=min_ecc, max_ecc=max_ecc, min_periastron_rad=min_periastron_rad, max_periastron_rad=max_periastron_rad, coverage=coverage, mismatch=mismatch, container_image_name=container_image_name, container_image_version=container_image_version, container_type=container_type, container_image_id=container_image_id, argument_hash=argument_hash)
            db_update = conn.execute(stmt)
            conn.commit()
            elliptical_orbit_search_id = db_update.inserted_primary_key[0]
            print(f"Added Elliptical Orbit Search parameters to elliptical_orbit_search_params table")
            if return_id:
                return elliptical_orbit_search_id
        else:
            elliptical_orbit_search_id = result[0]
            print(f"Elliptical Orbit Search parameters already exist in elliptical_orbit_search_params table. Skipping...")
            if return_id:
                return elliptical_orbit_search_id
    #Add elliptical orbit search to pipeline execution order table
    #insert_pipeline_execution_order(pipeline_id, "elliptical_orbit_search", execution_order, elliptical_orbit_search_id=elliptical_orbit_search_id)

def insert_rfifind(time, time_sigma, freq_sigma, chan_frac, int_frac, ncpus, extra_args, container_image_name, container_image_version, container_type, container_image_id, pipeline_github_commit_hash, execution_order, argument_hash=None, return_id=False):
    '''
    Insert RFIfind parameters into the rfifind_params table if it doesn't already exist
    '''
    rfifind_table = get_table("rfifind")
    combined_args = f"{time}{time_sigma}{freq_sigma}{chan_frac}{int_frac}{ncpus}{extra_args}"
    # Generate SHA256 hash
    argument_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    #Get pipeline id to add in execution order table
    pipeline_id = get_id_from_name("pipeline", pipeline_github_commit_hash, alternate_key='github_commit_hash')

    with engine.connect() as conn:
                                        
        stmt = (
        select(rfifind_table)
        .where(rfifind_table.c.argument_hash == argument_hash)
        .where(rfifind_table.c.container_image_id == container_image_id)
        .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            stmt = insert(rfifind_table).values(time=time, time_sigma=time_sigma, freq_sigma=freq_sigma, chan_frac=chan_frac, int_frac=int_frac, ncpus=ncpus, extra_args=extra_args, container_image_name=container_image_name, container_image_version=container_image_version, container_type=container_type, container_image_id=container_image_id, argument_hash=argument_hash)
            db_update = conn.execute(stmt)
            conn.commit()
            rfifind_id = db_update.inserted_primary_key[0]
            print(f"Added RFIfind parameters to rfifind_params table")
            if return_id:
                return rfifind_id
        else:
            rfifind_id = result[0]
            print(f"RFIfind parameters already exist in rfifind_params table. Skipping...")
            if return_id:
                return rfifind_id
    #Add rfifind to pipeline execution order table
    #insert_pipeline_execution_order(pipeline_id, "rfifind", execution_order, rfifind_id=rfifind_id)

    #insert_processing(2, "123456", "Hercules", "2021-01-30-11:54:02.05986", "SUBMITTED", 1, 3, 1, "Peasoup", "123456") 

def insert_processing(data_product_ids, pipeline_id, hardware_id, attempt_number, max_attempts, execution_order, program_name, argument_hash, submit_time=None, start_time=None, end_time=None, process_status='CREATED', return_id=False):
    '''
    Insert or update a processing entry in the processing table if it doesn't already exist for the same data product, pipeline, hardware, and argument hash.
    Now supports processing for multiple data_product_ids.
    '''
    processing_table = get_table("processing")
    pipeline_table = get_table("pipeline")
    hardware_table = get_table("hardware")
    program_table = get_table(program_name)
    foreign_column = f"{program_name}_id"
    data_product_table = get_table("data_product")
    processing_dp_table = get_table("processing_dp_inputs")
    
    with engine.connect() as conn:
        # Check if the process with the same argument hash on the given data_product (first in list) is running on any hardware
        stmt = (
            select(processing_table)
            .join(pipeline_table, pipeline_table.c.id == processing_table.c.pipeline_id)
            .join(hardware_table, hardware_table.c.id == processing_table.c.hardware_id)
            .join(program_table, program_table.c.id == getattr(processing_table.c, foreign_column))
            .join(processing_dp_table, processing_table.c.id == processing_dp_table.c.processing_id)
            .join(data_product_table, processing_dp_table.c.dp_id == data_product_table.c.id)
            .where(pipeline_table.c.github_commit_hash == pipeline_github_commit_hash)
            .where(program_table.c.argument_hash == argument_hash)
            .where(processing_table.c.program_name == program_name)
            .where(processing_dp_table.c.dp_id == data_product_ids[0])  # Only check the first data_product_id
            .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            # Insert new processing if it doesn't exist for the first data_product_id
            pipeline_id = get_id_from_name("pipeline", pipeline_github_commit_hash, alternate_key='github_commit_hash')
            hardware_id = get_id_from_name("hardware", hardware_name)
            program_id = get_id_from_name(program_name, argument_hash, alternate_key='argument_hash')
            new_id = uuid.uuid4()  # Generate a UUID
            binary_id = new_id.bytes  # Convert UUID to a 16-byte binary format
            
            
            insert_values = {
                "id": binary_id,
                "pipeline_id": pipeline_id,
                "hardware_id": hardware_id,
                "submit_time": submit_time,
                "process_status": process_status,
                "attempt_number": attempt_number,
                "max_attempts": max_attempts,
                "start_time": start_time,
                "end_time": end_time,
                "execution_order": execution_order,
                "program_name": program_name,
                foreign_column: program_id
            }
            stmt = insert(processing_table).values(**insert_values)
            db_update = conn.execute(stmt)
            processing_id = db_update.lastrowid
            conn.commit()
            print(f"Added processing to processing table")
            
            # Insert into processing_dp_inputs table for each data_product_id
            for data_product_id in data_product_ids:
                processing_dp_id = uuid.uuid4()  # Generate a UUID
                processing_dp_binary_id = processing_dp_id.bytes
                stmt = insert(processing_dp_table).values(id = processing_dp_binary_id, processing_id=processing_id, dp_id=data_product_id)
                conn.execute(stmt)
            conn.commit()
            
            if return_id:
                return processing_id
        else:
            processing_id = result[0]  # Assuming first column is the ID
            # Check if there's a status update
            if result.process_status != process_status or result.attempt_number != attempt_number:
                # Update processing status, start_time, end_time, and attempt_number
                stmt = (
                    processing_table.update()
                    .where(processing_table.c.id == processing_id)
                    .values(process_status=process_status, start_time=start_time, end_time=end_time, attempt_number=attempt_number)
                )
                conn.execute(stmt)
                conn.commit()
                print(f"Updated status of processing with id {processing_id} to {process_status}")
            else:
                print(f"Processing already exists in processing table. Skipping...")
            
            # Insert into processing_dp_inputs table for each data_product_id if not already linked. Extra Check
            for data_product_id in data_product_ids:
                # Check if the processing_id and data_product_id link already exists
                check_stmt = select(processing_dp_table).where(
                    processing_dp_table.c.processing_id == processing_id,
                    processing_dp_table.c.dp_id == data_product_id
                )
                link_exists = conn.execute(check_stmt).first()
                if not link_exists:
                    stmt = insert(processing_dp_table).values(processing_id=processing_id, dp_id=data_product_id)
                    conn.execute(stmt)
            conn.commit()
            if return_id:
                return processing_id




def insert_processing_old(data_product_ids, pipeline_github_commit_hash, hardware_name, submit_time, process_status, attempt_number, max_attempts, execution_order, program_name, argument_hash, start_time=None, end_time=None, return_id=False):
    '''
    Insert or update a processing entry in the processing table if it doesn't already exist for the same data product, pipeline, hardware, and argument hash.
    Now supports processing for multiple data_product_ids.
    '''
    processing_table = get_table("processing")
    pipeline_table = get_table("pipeline")
    hardware_table = get_table("hardware")
    program_table = get_table(program_name)
    foreign_column = f"{program_name}_id"
    data_product_table = get_table("data_product")
    processing_dp_table = get_table("processing_dp_inputs")
    
    with engine.connect() as conn:
        # Check if the process with the same argument hash on the given data_product (first in list) is running on any hardware
        stmt = (
            select(processing_table)
            .join(pipeline_table, pipeline_table.c.id == processing_table.c.pipeline_id)
            .join(hardware_table, hardware_table.c.id == processing_table.c.hardware_id)
            .join(program_table, program_table.c.id == getattr(processing_table.c, foreign_column))
            .join(processing_dp_table, processing_table.c.id == processing_dp_table.c.processing_id)
            .join(data_product_table, processing_dp_table.c.dp_id == data_product_table.c.id)
            .where(pipeline_table.c.github_commit_hash == pipeline_github_commit_hash)
            .where(program_table.c.argument_hash == argument_hash)
            .where(processing_table.c.program_name == program_name)
            .where(processing_dp_table.c.dp_id == data_product_ids[0])  # Only check the first data_product_id
            .limit(1)
        )
        result = conn.execute(stmt).first()
        
        if result is None:
            # Insert new processing if it doesn't exist for the first data_product_id
            pipeline_id = get_id_from_name("pipeline", pipeline_github_commit_hash, alternate_key='github_commit_hash')
            hardware_id = get_id_from_name("hardware", hardware_name)
            program_id = get_id_from_name(program_name, argument_hash, alternate_key='argument_hash')
            
            insert_values = {
                "pipeline_id": pipeline_id,
                "hardware_id": hardware_id,
                "submit_time": submit_time,
                "process_status": process_status,
                "attempt_number": attempt_number,
                "max_attempts": max_attempts,
                "start_time": start_time,
                "end_time": end_time,
                "execution_order": execution_order,
                "program_name": program_name,
                foreign_column: program_id
            }
            stmt = insert(processing_table).values(**insert_values)
            db_update = conn.execute(stmt)
            processing_id = db_update.lastrowid
            conn.commit()
            print(f"Added processing to processing table")
            
            # Insert into processing_dp_inputs table for each data_product_id
            for data_product_id in data_product_ids:
                stmt = insert(processing_dp_table).values(processing_id=processing_id, dp_id=data_product_id)
                conn.execute(stmt)
            conn.commit()
            
            if return_id:
                return processing_id
        else:
            processing_id = result[0]  # Assuming first column is the ID
            # Check if there's a status update
            if result.process_status != process_status or result.attempt_number != attempt_number:
                # Update processing status, start_time, end_time, and attempt_number
                stmt = (
                    processing_table.update()
                    .where(processing_table.c.id == processing_id)
                    .values(process_status=process_status, start_time=start_time, end_time=end_time, attempt_number=attempt_number)
                )
                conn.execute(stmt)
                conn.commit()
                print(f"Updated status of processing with id {processing_id} to {process_status}")
            else:
                print(f"Processing already exists in processing table. Skipping...")
            
            # Insert into processing_dp_inputs table for each data_product_id if not already linked. Extra Check
            for data_product_id in data_product_ids:
                # Check if the processing_id and data_product_id link already exists
                check_stmt = select(processing_dp_table).where(
                    processing_dp_table.c.processing_id == processing_id,
                    processing_dp_table.c.dp_id == data_product_id
                )
                link_exists = conn.execute(check_stmt).first()
                if not link_exists:
                    stmt = insert(processing_dp_table).values(processing_id=processing_id, dp_id=data_product_id)
                    conn.execute(stmt)
            conn.commit()
            if return_id:
                return processing_id
            
                                



def insert_data_product(beam_id, file_type_id, filename, filepath, available, locked, utc_start, tsamp_seconds, tobs_seconds, nsamples, freq_start_mhz, freq_end_mhz, hardware_id, nchans, nbits, hash_check=False, return_id=False, fft_size=None, tstart=None, filehash=None, metainfo=None, created_by_processing_id=None, modification_date=None):
    '''
    Inserts a new data product into the `data_product` table if it doesn't already exist.
    - Checks if a data product with the same filepath and filename exists or, if `hash_check` is True, checks by filehash.
    - Optionally, can return the UUID of the inserted or existing row when `return_id` is set to True.
    - Future Feature: Join with the beam table and check for the same beam_id before inserting.

    Parameters:
        - beam_id, file_type_id, etc.: Fields required for the data_product table.
        - hash_check (bool): If True, checks existence based on filehash instead of filepath and filename.
        - return_id (bool): If True, returns the UUID of the newly inserted or existing data product.

    Returns:
        - The UUID (str) of the inserted or existing data product if `return_id` is True. Otherwise, returns None.
    '''
    data_product_table = get_table("data_product")

    with engine.connect() as conn:
        if hash_check:
            # Check if a data product with the same filehash exists
            stmt = (
                select(data_product_table)
                .where(data_product_table.c.filehash == filehash)
                .limit(1)
            )
        else:
            # Check if a data product with the same filepath and filename exists
            full_path = filepath + filename  # Concatenate filepath and filename
            stmt = (
                select(data_product_table)
                .where(data_product_table.c.filepath + data_product_table.c.filename == full_path)
                .where(data_product_table.c.beam_id == beam_id)
                .where(data_product_table.c.hardware_id == hardware_id)
                .limit(1)
            )

        result = conn.execute(stmt).first()
        #result = conn.execute(stmt).fetchone()
        
        if result is None:

            new_id = uuid.uuid4()  # Generate a UUID
            binary_id = new_id.bytes  # Convert UUID to a 16-byte binary format
            
            stmt = insert(data_product_table).values(
                id = binary_id,
                beam_id=beam_id,
                file_type_id=file_type_id,
                filename=filename,
                filepath=filepath,
                filehash=filehash,
                available=available,
                modification_date=modification_date,
                metainfo=metainfo,
                locked=locked,
                utc_start=utc_start,
                tsamp=tsamp_seconds,
                tobs=tobs_seconds,
                nsamples=nsamples,
                freq_start_mhz=freq_start_mhz,
                freq_end_mhz=freq_end_mhz,
                created_by_processing_id=created_by_processing_id,
                hardware_id=hardware_id,
                fft_size=fft_size,
                tstart=tstart,
                nchans=nchans,
                nbits=nbits
            )
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added data product to data_product table")
            if return_id:
                data_product_id = str(new_id)
                return data_product_id
        else:
            print(f"Data product already exists in data_product table. Skipping...")
            if return_id:
                existing_uuid = uuid.UUID(bytes=bytes(result[0]))
                return str(existing_uuid)


def insert_search_candidate(pointing_id, beam_id, processing_id, spin_period, dm, snr, filename, filepath, nh, dp_id, candidate_id_in_file, pdot=None, pdotdot=None, pb=None, x=None, t0=None, omega=None, e=None, ddm_count_ratio=None, ddm_snr_ratio=None, nassoc=None, metadata_hash=None, candidate_filter_id=None, return_id=False):
    '''
    Insert a new search_candidate into search_candidate. No unique check as there will be millions of candidates.
    
    '''
    search_candidate_table = get_table("search_candidate")
    # combined_args = f"{pointing_id}{beam_id}{processing_id}{spin_period}{dm}{snr}{tstart}{nh}{dp_id}{candidate_id_in_file}{pdot}{pdotdot}{pb}{x}{t0}{omega}{e}"
    # # Generate SHA256 hash
    # metadata_hash = hashlib.sha256(combined_args.encode()).hexdigest()

    
    with engine.connect() as conn:
        stmt = insert(search_candidate_table).values(pointing_id=pointing_id, beam_id=beam_id, processing_id=processing_id, spin_period=spin_period, dm=dm, snr=snr, filename=filename, filepath=filepath, nh=nh, metadata_hash=metadata_hash, candidate_filter_id=candidate_filter_id, dp_id=dp_id, candidate_id_in_file=candidate_id_in_file, pdot=pdot, pdotdot=pdotdot, pb=pb, x=x, t0=t0, omega=omega, e=e, ddm_count_ratio=ddm_count_ratio, ddm_snr_ratio=ddm_snr_ratio, nassoc=nassoc)
        db_update = conn.execute(stmt)
        conn.commit()
        print(f"Added search candidate to search_candidate table")
        if return_id:
            return db_update.lastrowid

def insert_fold_candidate(pointing_id, beam_id, processing_id, spin_period, dm, pdot, pdotdot, fold_snr, filename, filepath, search_candidate_id, dp_id, metadata_hash=None, candidate_filter_id=None, return_id=False):
    '''
    Insert a new fold_candidate into fold_candidate. No unique check as there will be millions of candidates.
    '''
    fold_candidate_table = get_table("fold_candidate")
    # combined_args = f"{pointing_id}{beam_id}{processing_id}{spin_period}{dm}{pdot}{pdotdot}{fold_snr}{filename}{filepath}{search_candidate_id}{dp_id}"
    # # Generate SHA256 hash
    # metadata_hash = hashlib.sha256(combined_args.encode()).hexdigest()
    with engine.connect() as conn:
        stmt = insert(fold_candidate_table).values(pointing_id=pointing_id, beam_id=beam_id, processing_id=processing_id, spin_period=spin_period, dm=dm, pdot=pdot, pdotdot=pdotdot, fold_snr=fold_snr, filename=filename, filepath=filepath, search_candidate_id=search_candidate_id, metadata_hash=metadata_hash, dp_id=dp_id, candidate_filter_id=candidate_filter_id)
        db_update = conn.execute(stmt)
        conn.commit()
        print(f"Added fold candidate to fold_candidate table")
        if return_id:
            return db_update.lastrowid

def insert_user(username, fullname, email, password_hash, administrator=1, return_id=False):
    '''
    Insert a new user into the user table if it doesn't already exist
    '''
    user_table = get_table("user")
    with engine.connect() as conn:
        # Check if a user with the same username exists
        stmt = (
            select(user_table)
            .where(user_table.c.username == username)
            .limit(1)
        )
        result = conn.execute(stmt).first()
        if result is None:
            stmt = insert(user_table).values(username=username, fullname=fullname, email=email, password_hash=password_hash, administrator=administrator)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added {fullname} to user table")
            if return_id:
                user_id = db_update.lastrowid
                return user_id
        else:
            print(f"{fullname} already exists in user table. Skipping...")
            if return_id:
                return result[0]

def insert_user_labels(fold_candidate_id, user_id, rfi=None, noise=None, t1_cand=None, t2_cand=None, known_pulsar=None, nb_psr=None, is_harmonic=None, is_confirmed_pulsar=None, pulsar_name=None, return_id=False):
    '''
    Insert a new user label into the user_labels table.
    '''
    user_labels_table = get_table("user_labels")
    with engine.connect() as conn:
        #Add user labels to user_labels table        
        stmt = insert(user_labels_table).values(fold_candidate_id=fold_candidate_id, user_id=user_id, rfi=rfi, noise=noise, t1_cand=t1_cand, t2_cand=t2_cand, known_pulsar=known_pulsar, nb_psr=nb_psr, is_harmonic=is_harmonic, is_confirmed_pulsar=is_confirmed_pulsar, pulsar_name=pulsar_name)
        db_update = conn.execute(stmt)
        conn.commit()
        print(f"Added user label to user_labels table")
        if return_id:
            return db_update.lastrowid

def insert_beam_antenna(antenna_name, beam_id, description=None, return_id=False):
    '''
    Insert a new beam_antenna into the beam_antenna table if it doesn't already exist
    '''
    beam_antenna_table = get_table("beam_antenna")
    antenna_table = get_table("antenna")

    with engine.connect() as conn:
        # Check if a beam_antenna with the same antenna_id and beam_id exists
        stmt = (
            select(beam_antenna_table)
            .join(antenna_table, antenna_table.c.id == beam_antenna_table.c.antenna_id)
            .where(antenna_table.c.name == antenna_name)
            .where(beam_antenna_table.c.beam_id == beam_id)
            .limit(1)
        )
        result = conn.execute(stmt).first()
        if result is None:
            antenna_id = get_id_from_name("antenna", antenna_name)
            stmt = insert(beam_antenna_table).values(antenna_id=antenna_id, beam_id=beam_id, description=description)
            db_update = conn.execute(stmt)
            conn.commit()
            print(f"Added beam_id {beam_id} with antenna_name {antenna_name} to beam_antenna table")
            if return_id:
                return db_update.lastrowid
        else:
            print(f"Beam_id {beam_id} with antenna_name {antenna_name} already exists in beam_antenna table. Skipping...")
            if return_id:
                return result[0]

 # A combination of unique utc_start, project_name, telescope_name, freq_band and target_name identifies a unique pointing.


# def setup_argparse():
#     """Setup the command line arguments for the script"""
#     parser = argparse.ArgumentParser(description='Upload Data to Database and write keys to file')
#     parser.add_argument('--project_name', type=str, help='Project Name', required=True)
#     parser.add_argument('--telescope_name', type=str, help='Telescope Name', required=True)
#     #parser.add_argument('--freq_band', type=str, help='Frequency Band', required=True)
#     parser.add_argument('--target_name', type=str, help='Target Name', required=True)
#     parser.add_argument('--beam_name', type=str, help='Beam Name', required=True)
#     parser.add_argument('--beam_type_name', type=str, help='Beam Type', required=True)
#     parser.add_argument('--is_coherent', type=int, choices=[0, 1], default=1, help='Beam Type. Accepts 0 or 1. Defaults to 1.')
#     #parser.add_argument('--file_type_name', type=str, help='File Type', required=True)
#     parser.add_argument('--raw_data', type=str, help='Raw Data Directory', required=True)
#     parser.add_argument('--obs_header', type=str, help='Observation header file', required=True)
#     parser.add_argument('--hardware_name', type=str, help='Hardware name', required=True)

#     return parser

    
def parse_meertime_obs_header(file_path):
    """
    Parses the meertime obs.header file and returns a dictionary with the key-value pairs.
    
    :param file_path: Path to the obs.header file.
    :return: Dictionary containing the parsed key-value pairs.
    """
    obs_dict = {}
    with open(file_path, 'r') as file:
        for line in file:
            # Splitting each line by the first occurrence of whitespace to separate key and value
            key, value = line.strip().split(maxsplit=1)
            # For values that are lists of items (e.g., ANTENNAE, CBF_INPUTS), convert them into Python lists
            if ',' in value:
                value = value.split(',')
            obs_dict[key] = value
    return obs_dict


def get_tobs_and_metadata(data):
    """
    Calculate the total observation time of a list of files and extract metadata from the first file.

    Parameters:
    - data: A list of file paths.

    Returns:
    - The total observation time calculated from the first and last file in the list.
    - The lowest and highest frequency of the observation.
    """
    # Load the first and last file headers only, assuming uniformity across files for tsamp and nspectra.
    first_header = your.Your(data[0]).your_header
    last_header = your.Your(data[-1]).your_header
    central_freq = first_header.center_freq
   

    # Calculate total observation time.
    # (number of files - 1) * (number of spectra in a file * time per sample) + (spectra in last file * time per sample)
    tobs = (len(data) - 1) * first_header.nspectra * first_header.tsamp + last_header.nspectra * last_header.tsamp
    lowest_freq = central_freq - first_header.bw/2
    highest_freq = central_freq + first_header.bw/2
    return tobs, lowest_freq, highest_freq

def get_metadata_of_all_files(data):
    """
    Extract metadata from all files in the list.

    Parameters:
    - data: A list of file paths.

    Returns:
    - A list of dictionaries containing metadata for each file.
    """
    metadata = []
    for file in data:
        header = your.Your(file).your_header
        central_freq = header.center_freq
        bandwidth = header.bw
        lowest_freq = central_freq - bandwidth/2
        highest_freq = central_freq + bandwidth/2

        metadata.append({
            "filename": os.path.basename(header.filename),
            "filepath": os.path.dirname(header.filename),
            "tstart_utc": header.tstart_utc.replace("T", " "),
            "tsamp": header.tsamp,
            "tobs": header.tsamp * header.nspectra,
            "nsamples": header.nspectra,
            "freq_start_mhz": lowest_freq,
            "freq_end_mhz": highest_freq,
            "nchans": header.nchans,
            "nbits": header.nbits,
            "tstart": header.tstart
        })
    return metadata

def get_meerkat_freq_band(freq):
    """
    Determine the MeerKAT frequency band based on the given frequency.

    The central frequencies for the MeerKAT bands are as follows:
    - LBAND: 1284 Hz (L-band)
    - SBAND: 2187.50 Hz (S0 filter of S-band)
    - UHF: 816 Hz (Ultra High Frequency)

    Parameters:
    - freq: Frequency in Hz to determine its corresponding MeerKAT frequency band.

    Returns:
    - A string indicating the frequency band ('LBAND', 'SBAND', or 'UHF').
    """
    if freq > 2000:
        return "SBAND"
    elif freq > 1000:
        return "LBAND"
    else:
        return "UHF"
 

def parse_and_format_datetime(datetime_str):
    """
    Parse the given datetime string and return a formatted string representation.

    Parameters:
    - datetime_str: The datetime string to parse.

    Returns:
    - A string representation of the datetime, with fractional seconds.
    """
    # Check for the presence of fractional seconds and append '.0' if absent
    has_fractional_seconds = '.' in datetime_str
    if has_fractional_seconds:
        return datetime_str
    else:
        datetime_str += '.0'
        return datetime_str
    

def parse_nextflow_config(file_path):
    config = {}
    with open(file_path, 'r') as file:
        for line in file:
            # Strip leading/trailing whitespace
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('//'):
                continue
            # Split line into key and value at the first '='
            if '=' in line:
                key, value = line.split('=', 1)
                # Trim whitespace and remove surrounding quotes from value
                key = key.strip()
                value = value.strip().strip('"')
                # Store in config dictionary
                config[key] = value
    return config


def get_repo_details():
    try:
        # Get the remote repository URL
        remote_url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"], 
            universal_newlines=True
        ).strip()

        # Extract the repo name from the URL
        repo_name = remote_url.split('/')[-1].replace('.git', '')

        # Get the current branch name
        branch_name = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
            universal_newlines=True
        ).strip()

        # Get the last commit ID
        last_commit_id = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], 
            universal_newlines=True
        ).strip()

        
        return repo_name, branch_name, last_commit_id
        
    except subprocess.CalledProcessError as e:
        print("An error occurred while trying to retrieve repository details")
        return None


def parse_nextflow_flat_config_from_file(file_path):
    config = {}
    with open(file_path, 'r') as file:
        for line in file:
            # Split each line by the first '=' to separate the key and value
            if "=" in line:
                key, value = line.split("=", 1)
                # Trim whitespace and remove surrounding quotes from the value if present
                key = key.strip()
                value = value.strip().strip("'\"")
                config[key] = value
    return config



def dump_program_data_products_json(pipeline_id, hardware_id, beam_id, programs, output_filename='raw_dp_with_ids.json'):
    """
    Generates a JSON file organizing data products for multiple programs along with pipeline and hardware id.
    
    Parameters:
    - pipeline_id (int): The unique identifier for the pipeline.
    - hardware_id (int): The unique identifier for the hardware.
    - beam_id (int): The unique identifier for the beam.
    - programs (list of dicts): List of program configurations. Each dictionary should have:
        - program_name (str): The name of the program (e.g., "filtool", "peasoup").
        - program_id (int): The unique identifier for the program.
        - output_file_id (int): Output file type ID for the program.
        - data_products (list of tuples): Each tuple contains a data product ID and its associated filename.
    - output_filename (str, optional): The name of the output JSON file. Default is 'raw_dp_with_ids.json'.
    
    The generated JSON structure will be:
    {
        "pipeline_id": <pipeline_id>,
        "hardware_id": <hardware_id>,
        "beam_id": <beam_id>,
        "programs": [
            {
                "program_name": <program_name>,
                "program_id": <program_id>,
                "output_file_id": <output_file_id>,
                "data_products": [
                    {"dp_id": <data_product_id>, "filename": <filename>},
                    ...
                ]
            },
            ...
        ]
    }
    
    Example Usage:
    dump_program_data_products_json(1, 2, 3, [
        {"program_name": "filtool", "program_id": 100, "output_file_id": 200, "data_products": [("dp1", "file1.fil"), ("dp2", "file2.fil")]},
        {"program_name": "peasoup", "program_id": 101, "output_file_id": 201, "data_products": [("dp3", "file3.ps"), ("dp4", "file4.ps")]}
    ])
    """
    
    json_data = {
        'pipeline_id': pipeline_id,
        'hardware_id': hardware_id,
        'beam_id': beam_id,
        'programs': [
            {
                'program_name': program['program_name'],
                'program_id': program['program_id'],
                'output_file_id': program['output_file_id'],
                'data_products': [
                    {'dp_id': dp_id, 'filename': filename} for dp_id, filename in program['data_products']
                ]
            } for program in programs
        ]
    }
    
    with open(output_filename, 'w') as f:
        json.dump(json_data, f, indent=4)
    
    print(f"Data products JSON file created: {output_filename}")


def initialize_configs(file_path):
    """
    Parses the config file and extracts relevant parameters.
    """
    nextflow_config = parse_nextflow_flat_config_from_file(file_path)
    params = {
        'project_name': nextflow_config['params.project'],
        'pipeline_name': nextflow_config['params.pipeline_name'],
        'telescope_name': nextflow_config['params.telescope'],
        'target_name': nextflow_config['params.target'],
        'beam_name': nextflow_config['params.beam'],
        'beam_type': nextflow_config['params.beam_type'],
        'is_coherent_flag': nextflow_config['params.is_beam_coherent'],
        'data_header': nextflow_config['params.obs_header'],
        'raw_data': nextflow_config['params.raw_data'],
        'hardware_name': nextflow_config['params.hardware']
    }
    return params

def insert_basic_records(params):
    """
    Inserts basic records into the database and returns their IDs.
    """
    project_id = insert_project_name(params['project_name'], return_id=True)
    telescope_id = insert_telescope_name(params['telescope_name'], return_id=True)
    hardware_id = insert_hardware(params['hardware_name'], return_id=True)
    return project_id, telescope_id, hardware_id

def setup_programs(telescope_name, docker_image_hashes):
    """
    Setup program configurations.
    """
    filtool = {
        'program_name': 'filtool',
        'rfi_filter': nextflow_config['params.filtool.rfi_filter'],
        'threads': nextflow_config['params.filtool.threads'],
        'image_name': os.path.basename(nextflow_config['params.fold_singularity_image']),
        'hash': docker_image_hashes.loc[docker_image_hashes['Image'] == 'pulsarx', 'SHA256'].values[0],
        'version': docker_image_hashes.loc[docker_image_hashes['Image'] == 'pulsarx', 'Version'].values[0],
        'container_type': "singularity"
    }
    peasoup = {
        'program_name': 'peasoup',
        'acc_start': nextflow_config['params.peasoup.acc_start'],
        'acc_end': nextflow_config['params.peasoup.acc_end'],
        'min_snr': nextflow_config['params.peasoup.min_snr'],
        'ram_limit_gb': nextflow_config['params.peasoup.ram_limit_gb'],
        'nh': nextflow_config['params.peasoup.nh'],
        'ngpus': nextflow_config['params.peasoup.ngpus'],
        'total_cands_limit': nextflow_config['params.peasoup.total_cands_limit'],
        'fft_size': nextflow_config['params.peasoup.fft_size'],
        'dm_file': nextflow_config['params.peasoup.dm_file'],
        'image_name': os.path.basename(nextflow_config['params.search_singularity_image']),
        'hash': docker_image_hashes.loc[docker_image_hashes['Image'] == 'peasoup', 'SHA256'].values[0],
        'version': docker_image_hashes.loc[docker_image_hashes['Image'] == 'peasoup', 'Version'].values[0],
        'container_type': "singularity"
    }
    return filtool, peasoup


def parse_config_and_initialize(file_path):
    """
    Parses configuration file and extracts parameters.
    """
    nextflow_config = parse_nextflow_flat_config_from_file(file_path)
    config = {
        'project_name': nextflow_config['params.project'],
        'pipeline_name': nextflow_config['params.pipeline_name'],
        'telescope_name': nextflow_config['params.telescope'],
        'target_name': nextflow_config['params.target'],
        'beam_name': nextflow_config['params.beam'],
        'beam_type': nextflow_config['params.beam_type'],
        'is_coherent_flag': nextflow_config['params.is_beam_coherent'],
        'data_header': nextflow_config['params.obs_header'],
        'raw_data': nextflow_config['params.raw_data'],
        'hardware_name': nextflow_config['params.hardware']
    }
    return config

def extract_observation_details(data_header):
    """
    Extracts detailed observation parameters from the header of meertime observations. This is the coordinates for the boresight!
    """
    obs_header = parse_meertime_obs_header(data_header)
    header_config = {
        'ra': obs_header['TIED_BEAM_RA'],
        'dec': obs_header['TIED_BEAM_DEC'],
        'utc_start_str': obs_header['UTC_START'],
        'antenna_list': obs_header['ANTENNAE'],
        'nchans': obs_header['SEARCH_OUTNCHAN'],
        'tsamp': float(obs_header['SEARCH_OUTTSAMP']) * 1e-6,
        'central_freq': round(float(obs_header['FREQ']), 2),
        'receiver': obs_header['RECEIVER']
    }
    return header_config

def insert_observational_records(params, obs_details, project_id, telescope_id):
    """
    Inserts observational records into the database and returns their IDs. This is survey dependent and needs to be modified for other surveys.
    """
    target_id = insert_target_name(params['target_name'], obs_details['ra'], obs_details['dec'], project_id, return_id=True)
    data = glob.glob(params['raw_data'])
    tobs, lowest_freq, highest_freq = get_tobs_and_metadata(data)

    if params['telescope_name'].lower() == "meerkat":
        freq_band = get_meerkat_freq_band(obs_details['central_freq'])
    else:
        freq_band = "UNKNOWN"

    pointing_id = insert_pointing(
        parse_and_format_datetime(obs_details['utc_start_str']),
        tobs,  
        obs_details['nchans'],
        freq_band,
        target_id,
        lowest_freq,
        highest_freq,
        obs_details['tsamp'],
        telescope_id,
        obs_details['receiver'],
        return_id=True
    )
    beam_type_id = insert_beam_type(params['beam_type'], return_id=True)
    beam_id = insert_beam(params['beam_name'], obs_details['ra'], obs_details['dec'], pointing_id, beam_type_id, obs_details['tsamp'], is_coherent=params['is_coherent_flag'], return_id=True)
    #Get file extension name and remove dot
    file_type_extension = os.path.splitext(data[0])[1][1:]  
    file_type_id = insert_file_type(file_type_extension, return_id=True)

    return target_id, pointing_id, beam_id, beam_type_id, file_type_id

def setup_programs(config, docker_image_hashes):
    """
    Configures program parameters.
    """
    return [
        {
            'program_name': 'filtool',
            'program_id': config['filtool_id'],
            'output_file_id': config['filtool_output_file_type_id'],
            'data_products': config['raw_data_with_id']
        },
        {
            'program_name': 'peasoup',
            'program_id': config['peasoup_id'],
            'output_file_id': config['peasoup_output_file_type_id'],
            'data_products': config['raw_data_with_id']
        }
    ]

def insert_data_products(data_products, beam_id, file_type_id, hardware_id):
    """
    Inserts multiple data products into the database and collects their IDs along with file paths.

    Parameters:
    - data_products (list): List of dictionaries containing data product metadata.
    - beam_id (int): ID of the beam associated with these data products.
    - file_type_id (int): ID of the file type for these data products.
    - hardware_id (int): ID of the hardware used to collect these data products.

    Returns:
    - list of lists: Each inner list contains the data product ID and the concatenated file path and filename.
    """
    raw_data_with_id = []
    data_available_flag = 1  # Assuming these are static flags as per your previous setup
    file_locked_flag = 0

    for dp in data_products:
        dp_id = insert_data_product(
            beam_id, file_type_id, dp['filename'], dp['filepath'],
            data_available_flag, file_locked_flag, dp['tstart_utc'], dp['tsamp'],
            dp['tobs'], dp['nsamples'], dp['freq_start_mhz'], dp['freq_end_mhz'],
            hardware_id, dp['nchans'], dp['nbits'], tstart=dp['tstart'], return_id=True
        )
        # Storing the data product ID along with its filepath and filename
        raw_data_with_id.append([dp_id, os.path.join(dp['filepath'], dp['filename'])])

    return raw_data_with_id


def main():
    #Run this first before upload_data.py
    #nextflow config -profile nt -flat -sort > data_config.cfg
    file_path = 'data_config.cfg'
    params = parse_config_and_initialize(file_path)
    project_id, telescope_id, hardware_id = insert_basic_records(params)
    obs_details = extract_observation_details(params['data_header'])
    print(params)
    print(obs_details)
  

    # Retrieve repo and other metadata
    repo_name, branch_name, last_commit_id = get_repo_details()
    pipeline_id = insert_pipeline(params['pipeline_name'], repo_name, last_commit_id, branch_name, description='Time Domain Full length Accel Search using Peasoup', return_id=True)
    
   
    # Insert target and pointing data
    target_id, pointing_id, beam_id, beam_type_id, file_type_id = insert_observational_records(params, obs_details, project_id, telescope_id)

    
    
    # Get additional metadata for files and types
    data_products = get_metadata_of_all_files(sorted(glob.glob(params['raw_data'])))
    

    # Data product insertion
    raw_data_with_id = insert_data_products(data_products, beam_id, file_type_id, hardware_id)
    print(raw_data_with_id)
    sys.exit()
    
    # Read docker image hashes
    docker_image_hashes = pd.read_csv('docker_image_digests.csv')
    programs_config = setup_programs({
        'filtool_id': 100,  # Example ID
        'peasoup_id': 101,  # Example ID
        'filtool_output_file_type_id': 200,  # Example output file type ID
        'peasoup_output_file_type_id': 201,  # Example output file type ID
        'raw_data_with_id': raw_data_with_id
    }, docker_image_hashes)

    # Dump JSON with the updated function that handles multiple programs
    dump_program_data_products_json(pipeline_id, hardware_id, beam_id, programs_config)

if __name__ == "__main__":
    main()




# def main():
#     #Run this first before upload_data.py
#     #nextflow config -profile nt -flat -sort > data_config.cfg
    
    
#     file_path = 'data_config.cfg'
#     nextflow_config = parse_nextflow_flat_config_from_file(file_path)
    
#     project_name = nextflow_config['params.project']
#     pipeline_name = nextflow_config['params.pipeline_name']
#     telescope_name = nextflow_config['params.telescope']
#     target_name = nextflow_config['params.target']
#     beam_name = nextflow_config['params.beam']
#     beam_type = nextflow_config['params.beam_type']
#     is_coherent_flag = nextflow_config['params.is_beam_coherent']
#     data_header = nextflow_config['params.obs_header']
#     raw_data = nextflow_config['params.raw_data']
#     hardware_name = nextflow_config['params.hardware']
#     repo_name, branch_name, last_commit_id = get_repo_details()
#     project_id = insert_project_name(project_name, return_id=True)
#     telescope_id = insert_telescope_name(telescope_name, return_id=True)
#     obs_header = parse_meertime_obs_header(data_header)
#     ra = obs_header['TIED_BEAM_RA']
#     dec = obs_header['TIED_BEAM_DEC']
#     utc_start_str = obs_header['UTC_START']
#     antenna_list = obs_header['ANTENNAE']
#     utc_start = parse_and_format_datetime(utc_start_str)
#     nchans = obs_header['SEARCH_OUTNCHAN']
#     tsamp = float(obs_header['SEARCH_OUTTSAMP']) * 1e-6
#     central_freq = round(float(obs_header['FREQ']), 2)
#     receiver = obs_header['RECEIVER'] CHECKED!
#     data = sorted(glob.glob(raw_data))
#     dp_metadata = get_metadata_of_all_files(data)
#     tobs, lowest_freq, highest_freq = get_tobs_and_metadata(data)
#     if telescope_name.lower() == "meerkat":
#         freq_band = get_meerkat_freq_band(central_freq)
#     else:
#         freq_band = "UNKNOWN"
    

#     docker_image_hashes = pd.read_csv('docker_image_digests.csv')
   
#     target_id = insert_target_name(target_name, ra, dec, project_id, return_id=True)
#     pointing_id = insert_pointing(utc_start, tobs, nchans, freq_band, target_id, lowest_freq, highest_freq, tsamp, telescope_id, receiver, return_id=True)
#     beam_type_id = insert_beam_type(beam_type, return_id=True)
#     beam_id = insert_beam(beam_name, ra, dec, pointing_id, beam_type_id, tsamp, is_coherent=is_coherent_flag, return_id=True)
#     hardware_id = insert_hardware(hardware_name, return_id=True)
#     #get extension of first file
#     file_type_extension = os.path.splitext(data[0])[1][1:]
#     file_type_id = insert_file_type(file_type_extension, return_id=True)


    
#     data_available_flag = 1
#     file_locked_flag = 0
    
    
#     #Add all data_products to the database
#     raw_data_with_id = []
#     for dp in dp_metadata:
#        dp_id = insert_data_product(beam_id, file_type_id, dp['filename'], dp['filepath'], data_available_flag, file_locked_flag, dp['tstart_utc'], dp['tsamp'], dp['tobs'], dp['nsamples'], dp['freq_start_mhz'], dp['freq_end_mhz'], hardware_id, dp['nchans'], dp['nbits'], tstart = dp['tstart'], return_id=True)
#        raw_data_with_id.append([dp_id, dp['filepath'] + '/' + dp['filename']])
    

#     pipeline_id = insert_pipeline(pipeline_name, repo_name, last_commit_id, branch_name, description='Time Domain Full length Accel Search using Peasoup', return_id=True)
#     #Filtool parameters
#     filtool_rfi_filter = nextflow_config['params.filtool.rfi_filter']
#     filtool_threads = nextflow_config['params.filtool.threads']
#     filtool_output_filename = f'{target_name}_{freq_band}_{utc_start}_{beam_name}'
#     filtool_source_name = target_name
#     filtool_image_name = os.path.basename(nextflow_config['params.fold_singularity_image'])
#     filtool_extra_args = None
#     filtool_hash = docker_image_hashes.loc[docker_image_hashes['Image'] == 'pulsarx', 'SHA256'].values[0]
#     filtool_version = docker_image_hashes.loc[docker_image_hashes['Image'] == 'pulsarx', 'Version'].values[0]
#     container_type = "singularity"
#     filtool_id = insert_filtool(filtool_rfi_filter, telescope_name, filtool_threads, filtool_image_name, filtool_version, container_type, filtool_hash, return_id=True, extra_args=filtool_extra_args)
#     first_program = 'filtool'
#     output_file_type_name = 'fil'
#     filtool_output_file_type_id = insert_file_type(output_file_type_name, return_id=True)
    
#     #Peasoup parameters
#     peasoup_acc_start = nextflow_config['params.peasoup.acc_start']
#     peasoup_acc_end = nextflow_config['params.peasoup.acc_end']
#     peasoup_min_snr = nextflow_config['params.peasoup.min_snr']
#     peasoup_ram_limit_gb = nextflow_config['params.peasoup.ram_limit_gb']
#     peasoup_nh = nextflow_config['params.peasoup.nh']
#     peasoup_ngpus = nextflow_config['params.peasoup.ngpus']
#     peasoup_total_cands_limit = nextflow_config['params.peasoup.total_cands_limit']
#     peasoup_fft_size = nextflow_config['params.peasoup.fft_size']
#     peasoup_dm_file = nextflow_config['params.peasoup.dm_file']
#     peasoup_image_name = os.path.basename(nextflow_config['params.search_singularity_image'])
#     peasoup_extra_args = None
#     peasoup_hash = docker_image_hashes.loc[docker_image_hashes['Image'] == 'peasoup', 'SHA256'].values[0]
#     peasoup_version = docker_image_hashes.loc[docker_image_hashes['Image'] == 'peasoup', 'Version'].values[0]
    
#     peasoup_accel_tol = nextflow_config['params.peasoup.accel_tol']
#     peasoup_birdie_list = nextflow_config['params.peasoup.birdie_list']
#     peasoup_chan_mask = nextflow_config['params.peasoup.chan_mask']
#     print(peasoup_birdie_list, peasoup_chan_mask)
#     peasoup_id = insert_peasoup(peasoup_acc_start, peasoup_acc_end, peasoup_min_snr, peasoup_ram_limit_gb, \
#                                 peasoup_nh, peasoup_ngpus, peasoup_total_cands_limit, peasoup_fft_size, \
#                                 peasoup_dm_file, peasoup_image_name, peasoup_version, container_type, \
#                                 peasoup_hash, peasoup_accel_tol, return_id=True) 
    
#     output_file_type_name = 'xml'
#     peasoup_output_file_type_id = insert_file_type(output_file_type_name, return_id=True)


#     dump_program_data_products_json(pipeline_id, hardware_id, beam_id, first_program, filtool_id, filtool_output_file_type_id, raw_data_with_id)
   
    
