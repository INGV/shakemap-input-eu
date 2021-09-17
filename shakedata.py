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
import inspect
import shutil
import functools
import tempfile


# COMSTANTS
USRNAME = "&username=spada"
ONEDAY = 3600 * 24
fdsn_client = 'EMSC'

# global logger
logger = None

def catch_all_and_print(f):
    # type: (Callable[..., Any]) -> Callable[..., Any]
    """
    A function wrapper for catching all exceptions and logging them
    Questo trucco del decorator è carino però perdo l'informazione sulla linea di codice che è andata il errore
    Ho solo il nome della funzione
    """
    @functools.wraps(f)
    def inner(*args, **kwargs):
        # type: (*Any, **Any) -> Any
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.critical("Unexpected error:: {}".format(str(e)))
            exc_type, exc_obj, exc_tb = sys.exc_info()
            this_function_name = inspect.currentframe().f_code.co_name
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            #logger.critical("DETAILS: {}, {}, {}, {}".format(exc_type, fname, f.__name__, exc_tb.tb_lineno))
            logger.critical("DETAILS: {}, {}, {}".format(exc_type, fname, f.__name__))
            sys.exit()
    return inner

def copyFile(src, dest):
    dir = os.path.dirname(dest)
    if not os.path.isdir(dir):
        os.makedirs(dir)
    shutil.copyfile(src, dest)


def create_logger(severity):
    log_name = Path(__file__).stem
    _logger = logging.getLogger(log_name)

    numeric_level = getattr(logging, 'DEBUG', None)
    _logger.setLevel(numeric_level)

    formatter = logging.Formatter(fmt='[%(asctime)s.%(msecs)03d] - %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    handler = logging.StreamHandler(sys.stdout)
    numeric_level = getattr(logging, severity, None)
    _logger.setLevel(numeric_level)
    handler.setFormatter(formatter)
    _logger.addHandler(handler)

    return _logger



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

    if not os.path.isdir(args.git_repo_dir):
        sys.exit(f"Directory: {args.git_repo_dir} does not exist!!!")

def get_IMs(url_str_dat, url_str_ev, ev, FNAME_DAT, FNAME_EV):
    # data
    logger.info("request event_dat ws: %s" % (url_str_dat))
    try:
        r = requests.get(url_str_dat)
        if r.status_code == 200:
            with open(FNAME_DAT, mode='wb') as f:
                f.write(r.content)
        else:
            logger.error(f"event_dat problems with url: [{url_str_dat}] statuscode: [{r.status_code}]")
    except:
        logger.error (f"event_dat problems with url: [{url_str_dat}] status_dat forced to 204")
        pass

    # event
    logger.info (f"request event ws: [{url_str_ev}]")
    try:
        r = requests.get(url_str_ev)
        if r.status_code == 200:
            clean_eventxml(r.content, FNAME_EV)
        else:
            logger.error(f"event problems with url: [{url_str_dat}] statuscode: [{r.status_code}]")
    except:
        logger.error("event problems with url: [{url_str_dat}] status_ev forced to 204")



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


def clean_eventxml(xmlstring, filename):
    netid = "IV"
    network = "INGV-ONT"
    #
    tree = ET.ElementTree(ET.fromstring(xmlstring))
    root = tree.getroot()
    event = root.attrib
    # define the new attributesv
    event['netid'] = netid
    event['network'] = network
    event['time'] = "%04d-%02d-%02dT%02d:%02d:%02dZ" % (int(event['year']), int(event['month']), int(event['day']),
                                        int(event['hour']),int(event['minute']),int(event['second']))
    # drop not needed values
    for k in ['year', 'month', 'day', 'hour', 'minute', 'second']:
        if k in event:
            del event[k]

    tree.write(filename, xml_declaration=True, encoding="UTF-8")

def diff(eventfile1, eventfile2):
    tree1 = ET.parse(eventfile1)
    root1 = tree1.getroot()
    event1 = root1.attrib

    tree2 = ET.parse(eventfile2)
    root2 = tree2.getroot()
    event2 = root2.attrib

    event1.pop('created')
    event2.pop('created')

    return event1 != event2


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

@catch_all_and_print
def git_pull():
    repo = git.Repo(args.git_repo_dir+'/.git')
    repo.remotes.origin.pull()

@catch_all_and_print
def git_push():
    repo = git.Repo(args.git_repo_dir+'/.git')
    repo.git.add('--all')
    repo.index.commit("Some XML data updated")
    origin = repo.remote(name='origin')
    origin.push()

def generate_events_xml_data():
    for eid in args.event_ids:
        generate_event_xml_data(eid)

def generate_event_xml_data(event_id):
    logger.info("DOING EVENT: %s" % (event_id))
    EVENT_DIR = os.path.join(args.git_repo_dir, 'data', event_id[:6], event_id, 'current')

    temp_event_file = tempfile.NamedTemporaryFile(prefix='shake_event')

    # ESM
    url_str_dat = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event_dat" % (str(event_id), fdsn_client)
    url_str_ev = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event" % (str(event_id), fdsn_client)
    temp_dat_file = tempfile.NamedTemporaryFile(prefix='shake_dat_ESM')
    get_IMs(url_str_dat, url_str_ev, event_id, temp_dat_file, temp_event_file)
    FNAME_DAT = os.path.join(EVENT_DIR, f"{str(event_id)}_B_ESM_dat.xml")
    diff_replacement(FNAME_DAT, temp_dat_file)
    temp_dat_file.close()

    # RRSM
    url_str_dat = "http://www.orfeus-eu.org/odcws/rrsm/1/shakemap?eventid=%s" % (str(event_id))
    url_str_ev = "http://www.orfeus-eu.org/odcws/rrsm/1/shakemap?eventid=%s&type=event" % (str(event_id))
    temp_dat_file = tempfile.NamedTemporaryFile(prefix='shake_dat_RRSM')
    get_IMs(url_str_dat, url_str_ev, event_id, temp_dat_file, temp_event_file)
    temp_dat_file.seek(0, os.SEEK_END)
    if temp_dat_file.tell() > 0:
    #if os.stat(temp_dat_file.name).st_size > 0:
        FNAME_DAT = os.path.join(EVENT_DIR, f"{str(event_id)}_A_RRSM_dat.xml")
        copyFile(temp_dat_file, FNAME_DAT)
    temp_dat_file.close()

    # EVENT
    FNAME_EV = os.path.join(EVENT_DIR, "event.xml")
    diff_replacement(FNAME_EV, temp_event_file)
    temp_event_file.close()

    # FAULT
    # url_str_fault = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event_fault" % (str(event_id), fdsn_client)
    # temp_fault_file = tempfile.NamedTemporaryFile(prefix='shake_FAULT_')
    # get_IMs(url_str_dat, url_str_ev, event_id, temp_fault_file, None)
    # if os.stat(temp_fault_file.name).st_size > 0:
    #     pass

    '''
        # prepare for _fault
        fname_fault = "event_fault.txt"
        rupture = "rupture.json"
        FNAME_FAULT = os.path.join(INPUTEVENTDIR,fname_fault)
        FNAME_RUPT = os.path.join(INPUTEVENTDIR,rupture)
        #
    
        url_str_fault = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event_fault" % (str(ev), CATALOG)
        print ("request to ESM fault ws: %s" % (url_str_fault))
        try:
            r = requests.get(url_str_fault)
            status_fault = r.status_code
        except:
            print ("ESM event_fault problems: status_fault forced to 204")
            status_fault = 204
            pass
    
        #     print "status:", status
        if status_fault == 200:
            with open(FNAME_FAULT, mode='wb') as localfile:
                localfile.write(r.content)
            jdict = text_to_json(FNAME_FAULT, new_format=False)
            with open(FNAME_RUPT,'w') as f:
                json.dump(jdict,f)
            stringa = "mv %s %s.sav" % (FNAME_FAULT, FNAME_FAULT)
            os.system(stringa)
        return status_dat, status_ev, status_fault
    '''


def diff_replacement(currFile, new_file):
    # new_file.seek(0, os.SEEK_END)
    # if new_file.tell() > 0:
    if os.stat(new_file.name).st_size > 0:
        if os.path.isfile(currFile):
            if diff(new_file, currFile):
                shutil.copyfile(new_file, currFile)
        else:
            copyFile(new_file, currFile)

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
    parser.add_argument("git_repo_dir", help="provide the shakemap installation home dir (e.g., /Users/michelini/shakemap_profiles/world)")
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

    git_pull()

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

    git_push()







