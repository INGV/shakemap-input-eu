import os.path

import requests
import argparse
import json
import time
import xml.etree.ElementTree as ET
from obspy import UTCDateTime, Catalog
from obspy.clients.fdsn import Client
import git
from pathlib import Path
import logging
import argparse
import sys

# COMSTANTS
USRNAME = "&username=spada"
ONEDAY = 3600 * 24
fdsn_client = 'EMSC'
git_repository = '/home/sergio/projects/ingv/sismologia/shakemap-input-eu'

# global logger
logger = None


def create_logger(severity):
    log_name = Path(__file__).stem
    logger = logging.getLogger(log_name)

    numeric_level = getattr(logging, 'DEBUG', None)
    logger.setLevel(numeric_level)

    formatter = logging.Formatter(fmt='[%(asctime)s.%(msecs)03d] - %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    handler = logging.StreamHandler(sys.stdout)
    numeric_level = getattr(logging, severity, None)
    logger.setLevel(numeric_level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger



class MyParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('error: %s\n' % message)
        self.print_help()
        sys.exit(2)

def set_args():
    if args.days == '15m':
        args.days = 1./24. * 0.25
    else:
        args.days = float(args.days[:-1])

    args.minmag = float(args.minmag)

    # time to verify backward if input files from ESM have changed
    args.chkbcktime = float(args.chkbcktime) * ONEDAY # in seconnds

    # define the number of seconds in order to calculate the start_time
    # identify start and end times of the last month
    appo = UTCDateTime(args.end_time) - args.days * ONEDAY
    args.start_time =  appo.strftime("%Y-%m-%dT%H:%M:%S")
    #

    if not os.path.isdir(args.local_data_dir):
        sys.exit(f"Directory: {args.local_data_dir} does not exist!!!")

# extract ID from event string
def extract_id(string, fdsn_client):

    if fdsn_client == "USGS":
        tmp1, tmp2 = string.split("&")
        tmp3, event_id = tmp1.split("=")

    elif fdsn_client == "INGV":
        tmp1, tmp2 = string.split("?")
        tmp3, event_id = tmp2.split("=")

    elif fdsn_client == "IRIS":
        tmp1, tmp2 = string.split("?")
        tmp3, event_id = tmp2.split("=")

    elif fdsn_client == "EMSC":
        tmp1, tmp2 = string.split(":")
        tmp3, tmp4, event_id = tmp2.split("/")

    elif fdsn_client == "GFZ":
        event_id = string
    else:
        event_id = string

    return event_id


# routine to extract an obspy catalog and a list of events id from fdsn event ws
def find_events(
        fdsn_client,
        start_time="1900-01-01",
        end_time="2100-01-01",
        minmag=5.0,
        maxmag=9.9,
        latmin=-90,
        latmax=90,
        lonmin=-180,
        lonmax=180,
        mode='sing',
        orderby='time',
        verbose=True
):

    # mode = hist -> historical records of seismicity (eg. custom time window)
    # mode = sing -> discovery of a (hopefully) single event

    end_time = UTCDateTime(end_time)

    if mode == 'sing':
        delta_time = 7 # 7 seconds around event time on either side
        starttime = end_time - delta_time
        endtime = end_time + delta_time
    elif mode == 'hist':
        endtime = end_time
        starttime = UTCDateTime(start_time)
    else:
        logger.error("mode " + mode + " is not supported.")
        return False

    client = Client(fdsn_client)

    # another shitty dateline patch
    if lonmax > 180:
        # split in two requests
        try: cat1 = client.get_events(starttime=starttime, endtime=endtime, minmagnitude=minmag, maxmagnitude=maxmag, minlatitude=latmin, maxlatitude=latmax, minlongitude=lonmin, maxlongitude=180, orderby=orderby, limit=1000)
        except: cat1 = Catalog()
        try: cat2 = client.get_events(starttime=starttime, endtime=endtime, minmagnitude=minmag, maxmagnitude=maxmag, minlatitude=latmin, maxlatitude=latmax, minlongitude=-180, maxlongitude=-(360-lonmax), orderby=orderby, limit=1000)
        except: cat2 = Catalog()
        # combine the catalog object
        catalog = cat1 + cat2
    else:
        try:
            catalog = client.get_events(starttime=starttime, endtime=endtime, minmagnitude=minmag, maxmagnitude=maxmag, minlatitude=latmin, maxlatitude=latmax, minlongitude=lonmin, maxlongitude=lonmax, orderby=orderby, limit=1000)
        except:
            logger.error ("No events were found in the time window: [%s / %s]" % (starttime, endtime))
            quit()

#     tmp = str(cat[0].resource_id)
#     event_id = extract_id(tmp, fdsn_client)
    event_ids_list=[]
    for c in catalog:
        tmp = str(c.resource_id)
        event_ids_list.append(extract_id(tmp, fdsn_client))

    if verbose == True:

        for i, c in enumerate(catalog):
            ot = c.origins[0].time
            lat = c.origins[0].latitude
            lon = c.origins[0].longitude
            dep = c.origins[0].depth #/ 1000.
            mag = c.magnitudes[0].mag
            mag_type = c.magnitudes[0].magnitude_type
            logger.info("%s %s      %s   %s %s %s   %s (%s)" % (fdsn_client, event_ids_list[i], ot, lat, lon, dep, mag, mag_type))

    return catalog, event_ids_list

def log_summary_data():
    logger.info('EVENTS:')
    logger.info(args.event_ids)
    logger.info("STARTIME: %s   ENDTIME: %s" % (args.start_time, args.end_time))
    logger.info("MINMAG: %.1f" % (args.minmag))
    logger.info("ESM BCK VERIFICATION (days): %.2f" % (args.chkbcktime))
    logger.info("run at: %s" % (UTCDateTime().strftime("%Y-%m-%dT%H:%M:%S")))

def generate_events_xml_data():
    for eid in args.event_ids:
        generate_events_xml_data(eid)

def generate_events_xml_data(event_id):
    pass


if __name__ == '__main__':

    # define the default value of end_time to 'now'
    default_end_time = UTCDateTime().strftime("%Y-%m-%dT%H:%M:%S")
    #
    # default min magnitude
    default_minmag = 4.0
    #
    # default time backward to cross-check the input files of ESM
    default_chkbcktime = 1.0 # in days
    # check_time_bckwd = chkbcktime*ONEDAY # in seconnds

    parser = argparse.ArgumentParser()

    parser.add_argument("days",  help="set the number of days before end time (15m, 1d, 5d, 10d, 30d, 365d)", choices=['15m', '1d', '5d', '10d', '30d', '365d'])
    parser.add_argument("local_data_dir", help="provide the shakemap installation home dir (e.g., /Users/michelini/shakemap_profiles/world)")
    parser.add_argument("-e","--end_time", nargs="?", default=default_end_time, help="provide the end time  (e.g., 2020-10-23); [default is now]")
    parser.add_argument("-m","--minmag", nargs="?", default=default_minmag, help="provide the minimum magnitude (e.g.,4.5); [default is 4.0]")
    parser.add_argument("-b","--chkbcktime", nargs="?", default=default_chkbcktime, help="provide the number of days to check for ESM new input data [default is 1.0]")
    parser.add_argument("-l", "--log_severity",
                        type=str,
                        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
                        help="log severity level",
                        default="INFO")

    args = parser.parse_args()
    set_args()
    logger = create_logger(args.log_severity)

    repo = git.Repo(git_repository)
    repo.remotes.origin.pull()

    # my strategy is to have only one variabe shared by all functins, that is args
    args.catalog, args.event_ids = find_events(
        fdsn_client,
        start_time=args.start_time,
        end_time=args.end_time,
        minmag=args.minmag,
        latmin=27,
        latmax=81,
        lonmin=-32,
        lonmax=51,
        mode='hist',
        verbose=True
    )

    log_summary_data()
    generate_events_xml_data()









