import os.path
import subprocess
import requests
import json
import xml.etree.ElementTree as ET
from obspy import UTCDateTime, Catalog
from obspy.clients.fdsn.header import URL_MAPPINGS
from obspy.clients.fdsn import Client
import git
from pathlib import Path
import logging
import argparse
import sys
import inspect
import functools
from xmldiff import main
from  tempfile import NamedTemporaryFile

from datetime import datetime


# test

# COMSTANTS
#USRNAME = "&username=spada"
ONEDAY = 3600 * 24
fdsn_client = 'EMSC'
GIT_USERNAME = 'sergio'
TAB_SIZE = 2
INGV_BOUNDARIES_BASE_URL = "https://webservices.ingv.it/ingvws/boundaries"
# global logger
logger = None

# repository files
# this dictionary contains, for each file in the git repository
# the author and date of last modification
repository_files = {}

URL_MAPPINGS["EMSC"] = "https://www.seismicportal.eu"

class ShakeLibException(Exception):
    """
    Class to represent errors in the Fault class.
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

def _check_polygon(p):
    """
    Check if the verticies are specified top first.

    Args:
        p (list):
            A list of five lon/lat/depth lists.

    Raises:
        ValueError: incorrectly specified polygon.

    """
    n_points = len(p)
    if n_points % 2 == 0:
        raise ValueError('Number of points in polyon must be odd.')

    if p[0] != p[-1]:
        raise ValueError('First and last points in polygon must be '
                         'identical.')

    n_pairs = int((n_points - 1) / 2)
    for j in range(n_pairs):
        # -------------------------------------------------------------
        # Points are paired and in each pair the top is first, as in:
        #
        #      _.-P1-._
        #   P0'        'P2---P3
        #   |                  \
        #   P7---P6----P5-------P4
        #
        # Pairs: P0-P7, P1-P6, P2-P5, P3-P4
        # -------------------------------------------------------------
        top_depth = p[j][2]
        bot_depth = p[-(j + 2)][2]
        if top_depth >= bot_depth:
            raise ValueError(
                'Top points must be ordered before bottom points.')

def validate_json(d):
    """
    Check that the JSON format is acceptable. This is only for requirements
    that are common to both QuadRupture and EdgeRupture.

    Args:
        d (dict): Rupture JSON dictionary.
    """
    if d['type'] != 'FeatureCollection':
        raise Exception('JSON file is not a \"FeatureColleciton\".')

    if len(d['features']) != 1:
        raise Exception('JSON file should contain excactly one feature.')

    if 'reference' not in d['metadata'].keys():
        raise Exception('Json metadata field should contain '
                        '\"reference\" key.')

    f = d['features'][0]

    if f['type'] != 'Feature':
        raise Exception('Feature type should be \"Feature\".')

    geom = f['geometry']

    if (geom['type'] != 'MultiPolygon' and
            geom['type'] != 'Point'):
        raise Exception('Geometry type should be \"MultiPolygon\" '
                        'or \"Point\".')

    if 'coordinates' not in geom.keys():
        raise Exception('Geometry dictionary should contain \"coordinates\" '
                        'key.')

    polygons = geom['coordinates'][0]

    if geom['type'] == 'MultiPolygon':
        n_polygons = len(polygons)
        for i in range(n_polygons):
            _check_polygon(polygons[i])

def catch_all_and_print(f):
    # type: (Callable[..., Any]) -> Callable[..., Any]
    """
    A function wrapper for catching all exceptions and logging them
    Questo trucco del decorator è carino però si perde l'informazione sulla linea di codice che è andata in errore
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
    # Check for conflicting parameters: -k cannot be used with time parameters or minmag
    keep_provided = args.keep is not None
    days_ago_provided = args.days_ago is not None
    starttime_provided = args.starttime is not None
    endtime_provided = args.endtime is not None
    minmag_provided = args.minmag is not None

    if keep_provided and (days_ago_provided or starttime_provided or endtime_provided):
        sys.exit("Error: Cannot use -k/--keep (event IDs) together with time parameters (-d/--days_ago, -s/--starttime, -e/--endtime). When specifying event IDs, time ranges are not needed.")

    if keep_provided and minmag_provided:
        sys.exit("Error: Cannot use -k/--keep (event IDs) together with -m/--minmag. When specifying event IDs, magnitude filtering is not needed.")

    # Check for conflicting parameters: -d cannot be used with -s or -e
    if days_ago_provided and (starttime_provided or endtime_provided):
        sys.exit("Error: Cannot use -d/--days_ago together with -s/--starttime and/or -e/--endtime. Please use either -d OR (-s and/or -e).")

    # Set default minmag if not provided
    if args.minmag is None:
        args.minmag = 4.0
    else:
        args.minmag = float(args.minmag)

    # time to verify backward if input files from ESM have changed
    #args.chkbcktime = float(args.chkbcktime) * ONEDAY # in seconnds

    # Get current time for defaults
    now = UTCDateTime()
    today = UTCDateTime(now.strftime("%Y-%m-%d"))

    # Handle time calculation based on which parameters were provided
    if starttime_provided or endtime_provided:
        # Use explicit start/end times
        if args.starttime is not None:
            try:
                args.start_time = UTCDateTime(args.starttime).strftime("%Y-%m-%dT%H:%M:%S")
            except Exception as e:
                sys.exit(f"option --starttime is not valid time {args.starttime}. {str(e)}")
        else:
            # If only endtime provided, calculate starttime using default 1d
            days_value = 1.0
            try:
                end_time_obj = UTCDateTime(args.endtime)
                appo = end_time_obj - days_value * ONEDAY
                args.start_time = appo.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception as e:
                sys.exit(f"option --endtime is not valid time {args.endtime}. {str(e)}")

        if args.endtime is not None:
            try:
                args.end_time = UTCDateTime(args.endtime).strftime("%Y-%m-%dT%H:%M:%S")
            except Exception as e:
                sys.exit(f"option --endtime is not valid time {args.endtime}. {str(e)}")
        else:
            # Default endtime to now
            args.end_time = now.strftime("%Y-%m-%dT%H:%M:%S")

        # Set days for backward compatibility (use 1d as default)
        args.days = 1.0
    else:
        # Use days_ago logic (default behavior)
        # If no parameters provided, use default 1d
        if args.days_ago is None:
            args.days_ago = '1d'

        if args.days_ago == '15m':
            days_value = 1./24. * 0.25
        else:
            days_value = float(args.days_ago[:-1])

        # If using default 1d (and no explicit times), set to today 00:00:00 - 23:59:59
        if args.days_ago == '1d' and not endtime_provided:
            args.start_time = today.strftime("%Y-%m-%dT00:00:00")
            args.end_time = (today + ONEDAY - 1).strftime("%Y-%m-%dT23:59:59")
        else:
            # Calculate based on days_ago from now
            args.end_time = now.strftime("%Y-%m-%dT%H:%M:%S")
            appo = now - days_value * ONEDAY
            args.start_time = appo.strftime("%Y-%m-%dT%H:%M:%S")

        # Store days_value for backward compatibility
        args.days = days_value

    if not os.path.isdir(args.git_repo_dir):
        sys.exit(f"Directory: {args.git_repo_dir} does not exist!!!")

def DownloadData(url):
    # data
    try:
        r = requests.get(url)
        if r.status_code == 200:
            return r.content
        else:
            logger.info(f"\t\treturn: [{r.status_code}]".expandtabs(TAB_SIZE))
            return None
    except:
        logger.error (f"\t\tevent_dat problems with url: [{url}] status_dat forced to 204".expandtabs(TAB_SIZE))
        return None


def get_locstring(lat, lon, mode):
    """
    Query the INGV boundaries web service to get a location string
    for the given coordinates.

    Args:
        lat (str or float): Latitude.
        lon (str or float): Longitude.
        mode (str): 'region_name' or 'boundary'.

    Returns:
        str or None: The location string, or None if the request fails.
    """
    if mode == 'region_name':
        url = f"{INGV_BOUNDARIES_BASE_URL}/region_name/1/?lat={lat}&lon={lon}&limit=4000&format=json"
    elif mode == 'boundary':
        url = f"{INGV_BOUNDARIES_BASE_URL}/boundary/1/?lat={lat}&lon={lon}&boundary_type=flinn_engdahl_1996&includegeometry=false&limit=4000&format=json"
    else:
        logger.error(f"\t\tget_locstring: unknown mode '{mode}'".expandtabs(TAB_SIZE))
        return None

    logger.info(f"\t\trequest locstring ({mode}) on: {url}".expandtabs(TAB_SIZE))
    try:
        r = requests.get(url)
        if r.status_code == 200:
            resp = r.json()

            if mode == 'region_name':
                result = resp.get('data', {}).get('region_name', None)
            else:
                # Extract the first boundary_type and strip the suffix
                items = resp.get('data', [])
                if items:
                    raw = items[0].get('boundary_type', '')
                    # Remove the "(flinn_engdahl_1996)" suffix
                    result = raw.replace('(flinn_engdahl_1996)', '').strip()
                else:
                    result = None

            if result:
                logger.info(f"\t\tlocstring result: {result}".expandtabs(TAB_SIZE))
            else:
                logger.warning(f"\t\tlocstring: no result found in response".expandtabs(TAB_SIZE))
            return result
        else:
            logger.info(f"\t\tlocstring request returned: [{r.status_code}]".expandtabs(TAB_SIZE))
            return None
    except Exception as e:
        logger.error(f"\t\tlocstring request failed: {str(e)}".expandtabs(TAB_SIZE))
        return None


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

def clean_event_data(xmlstring):
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

    return ET.tostring(root, encoding='utf8')


def update_event_xml(data_event, event_id):
    """
    Optionally update the 'id' and 'locstring' attributes of the event XML
    based on the -u/--update-eventid and -r/--update-locstring flags.

    Args:
        data_event (bytes): The event XML data.
        event_id (str): The event ID used in the GET request.

    Returns:
        bytes: The (possibly modified) event XML data.
    """
    if not args.update_eventid and not args.update_locstring:
        return data_event

    tree = ET.ElementTree(ET.fromstring(data_event))
    root = tree.getroot()
    modified = False

    # Update 'id' attribute to match the event_id from the query
    if args.update_eventid:
        current_id = root.attrib.get('id', '')
        if current_id != event_id:
            logger.info(f"\t\tupdate-eventid: replacing id '{current_id}' with '{event_id}'".expandtabs(TAB_SIZE))
            root.attrib['id'] = event_id
            modified = True
        else:
            logger.info(f"\t\tupdate-eventid: id already matches '{event_id}', no change needed".expandtabs(TAB_SIZE))

    # Update 'locstring' attribute via INGV boundaries API (mode: region_name or boundary)
    if args.update_locstring:
        lat = root.attrib.get('lat', '')
        lon = root.attrib.get('lon', '')
        if lat and lon:
            locstring_value = get_locstring(lat, lon, args.update_locstring)
            if locstring_value is not None:
                current_locstring = root.attrib.get('locstring', '')
                if current_locstring != locstring_value:
                    logger.info(f"\t\tupdate-locstring ({args.update_locstring}): replacing locstring '{current_locstring}' with '{locstring_value}'".expandtabs(TAB_SIZE))
                    root.attrib['locstring'] = locstring_value
                    modified = True
                else:
                    logger.info(f"\t\tupdate-locstring ({args.update_locstring}): locstring already matches '{locstring_value}', no change needed".expandtabs(TAB_SIZE))
            else:
                logger.warning(f"\t\tupdate-locstring ({args.update_locstring}): could not retrieve locstring for lat={lat}, lon={lon}".expandtabs(TAB_SIZE))
        else:
            logger.warning(f"\t\tupdate-locstring: lat or lon missing from event XML".expandtabs(TAB_SIZE))

    if modified:
        return ET.tostring(root, encoding='utf8')
    return data_event


def diff(xmlstring, xml_file):
    f = NamedTemporaryFile(delete=False)
    f.write(xmlstring)
    path = f.name
    f.close()
    diff = main.diff_files(path, xml_file, {'ratio_mode': 'faster', 'fast_match': True} )
    os.unlink(path)

    if len(diff) == 0:
        return False
    if len(diff) == 1 and diff[0].name == 'created':
        return False
    return True

'''
def diff_old(mode, xmlstring, xml_file):
    if mode == 'DETAIL_MODE':
        tree1 = ET.ElementTree(ET.fromstring(xmlstring))
        root1 = tree1.getroot()
        event1 = root1.attrib

        tree2 = ET.parse(xml_file)
        root2 = tree2.getroot()
        event2 = root2.attrib

        event1.pop('created')
        event2.pop('created')

        return event1 != event2
    else:
        return xmlstring != open(xml_file).read()
'''

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
        verbose=True,
        event_ids=None
):

    # mode = hist -> historical records of seismicity (eg. custom time window)
    # mode = sing -> discovery of a (hopefully) single event

    client = Client(fdsn_client)
    # If specific event IDs are provided, query directly by event ID
    if event_ids is not None:
        logger.info(f"\tGET events by ID: {client.base_url}. PARAMS: fdsn_client={fdsn_client}, event_ids={event_ids}".expandtabs(TAB_SIZE))
        catalog = Catalog()
        for event_id in event_ids:
            try:
                # Build the URL to show what's being requested
                # Try different formats for EMSC event IDs
                query_url = f"{client.base_url}/fdsnws/event/1/query?eventid={event_id}"
                logger.info(f"\t\tQuerying event ID: {event_id} - URL: {query_url}".expandtabs(TAB_SIZE))

                # Try with simple event ID first
                try:
                    event_cat = client.get_events(eventid=event_id)
                except Exception as e1:
                    # If that fails, try with QuakeML format for EMSC
                    logger.debug(f"\t\t\tSimple ID failed: {str(e1)}".expandtabs(TAB_SIZE))

                catalog += event_cat
            except Exception as e:
                logger.warning(f"\t\tFailed to retrieve event {event_id}: {str(e)}".expandtabs(TAB_SIZE))
                logger.info(f"\t\t\tAttempted URL: {query_url}".expandtabs(TAB_SIZE))

        if len(catalog) == 0:
            logger.info("No events were found for the provided event IDs")
            quit()
    else:
        # Original time-based query logic
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

        logger.info(f"\tGET: {client.base_url}. PARAMS: fdsn_client={fdsn_client}, start_time={start_time}, end_time={end_time}, minmag={minmag}, maxmag={maxmag}, latmin={latmin}, latmax={latmax}, lonmin={lonmin}, lonmax={lonmax}, mode={mode}, orderby={orderby}".expandtabs(TAB_SIZE))

        # another shitty dateline patch
        if lonmax > 180:
            # split in two requests
            try:
                cat1 = client.get_events(starttime=starttime, endtime=endtime, minmagnitude=minmag, maxmagnitude=maxmag, minlatitude=latmin, maxlatitude=latmax, minlongitude=lonmin, maxlongitude=180, orderby=orderby, limit=1000)
            except:
                cat1 = Catalog()

            try:
                cat2 = client.get_events(starttime=starttime, endtime=endtime, minmagnitude=minmag, maxmagnitude=maxmag, minlatitude=latmin, maxlatitude=latmax, minlongitude=-180, maxlongitude=-(360-lonmax), orderby=orderby, limit=1000)
            except:
                cat2 = Catalog()
            # combine the catalog object
            catalog = cat1 + cat2
        else:
            try:
                catalog = client.get_events(starttime=starttime, endtime=endtime, minmagnitude=minmag, maxmagnitude=maxmag, minlatitude=latmin, maxlatitude=latmax, minlongitude=lonmin, maxlongitude=lonmax, orderby=orderby, limit=1000)
            except:
                logger.info ("No events were found in the time window: [%s / %s]" % (starttime, endtime))
                quit()

#     tmp = str(cat[0].resource_id)
#     event_id = extract_id(tmp, fdsn_client)
    event_ids_list=[]
    for c in catalog:
        tmp = str(c.resource_id)
        event_ids_list.append(extract_id(tmp, fdsn_client))

    if verbose == True:

        logger.info(f'DETAILED LIST OF EVENTS:')
        for i, c in enumerate(catalog):
            ot = c.origins[0].time
            lat = c.origins[0].latitude
            lon = c.origins[0].longitude
            dep = c.origins[0].depth #/ 1000.
            mag = c.magnitudes[0].mag
            mag_type = c.magnitudes[0].magnitude_type
            logger.info(f"\t\t{fdsn_client} {event_ids_list[i]}      {ot}   {lat} {lon} {dep}   {mag} ({mag_type})".expandtabs(TAB_SIZE))
    else:
        logger.info(f'\t\tLIST OF EVENTS: {event_ids_list}'.expandtabs(TAB_SIZE))

    return catalog, event_ids_list

def log_summary_data():
    logger.info(f'SUMMARY DATA:')
    logger.info(f"\tSTARTIME: {args.start_time}   ENDTIME: {args.end_time}".expandtabs(TAB_SIZE))
    logger.info(f"\tMINMAG: {args.minmag:.1f}".expandtabs(TAB_SIZE))
    #logger.info("ESM BCK VERIFICATION (days): %.2f" % (args.chkbcktime))
    #logger.info("\trun at: %s" % (UTCDateTime().strftime("%Y-%m-%dT%H:%M:%S")))

@catch_all_and_print
def git_pull():
    logger.info(f"Executing pull from {args.git_repo_dir}")
    repo = git.Repo(args.git_repo_dir+'/.git')
    repo.remotes.origin.pull()

@catch_all_and_print
def git_push():
    repo = git.Repo(args.git_repo_dir+'/.git')
    #repo.git.add('--all')
    # repo.git.add('data')
    # logger.info(f"Executing commit")
    # repo.index.commit("Some XML data updated")

    # Check if there are commits to push
    origin = repo.remote(name='origin_ssh')
    local_commit = repo.head.commit

    try:
        # Get remote commit
        origin.fetch()
        remote_commit = repo.commit('origin_ssh/main')

        # Check if local is ahead of remote
        commits_ahead = list(repo.iter_commits(f'{remote_commit}..{local_commit}'))

        if commits_ahead:
            logger.info(f"Executing push to {args.git_repo_dir} ({len(commits_ahead)} commit(s) to push)")
            origin.push()
        else:
            logger.info(f"Nothing to push to {args.git_repo_dir}")
    except Exception as e:
        # If there's an error checking (e.g., no remote branch yet), just push
        logger.info(f"Executing push to {args.git_repo_dir}")
        origin.push()

@catch_all_and_print
def git_commit(FileFullPath, msg):
    repo = git.Repo(args.git_repo_dir+'/.git')
    repo.git.add(FileFullPath)
    #repo.git.add('data')
    #logger.info(f"Executing commit")
    repo.index.commit(msg)

def generate_events_xml_data():
    totalEvents = len(args.event_ids)
    spaces = len(str(totalEvents))
    for index, eid in enumerate(args.event_ids):
        logger.info(f'{index+1:{spaces}d}/{totalEvents} - DOING EVENT: {eid}')
        # if eid == '20201030_0000082':
        generate_event_xml_data(eid)

def generate_event_xml_data(event_id):
    EVENT_DIR = os.path.join(args.git_repo_dir, 'data', event_id[:6], event_id, 'current')

    # Track if any data was successfully downloaded
    any_data_downloaded = False

    # ESM SHAKE DATA
    FILE_NAME_DAT = f"{str(event_id)}_B_ESM_dat.xml"
    FILE_FULL_NAME_DAT = os.path.join(EVENT_DIR, FILE_NAME_DAT)

    relative_path = os.path.relpath(FILE_FULL_NAME_DAT, args.git_repo_dir)
    result, author = check_repository_file(relative_path)

    if result:
        url_ESM_dat = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event_dat" % (str(event_id), fdsn_client)
        logger.info(f"\trequest \"_dat.xml\" on: {url_ESM_dat}".expandtabs(TAB_SIZE))
        data = DownloadData(url_ESM_dat)
        if data:
            saveIfChanged(data, FILE_FULL_NAME_DAT, event_id)
            any_data_downloaded = True
    else:
        logger.warning(f"\tfile {FILE_NAME_DAT} skipped because modified by the external user: {author}".expandtabs(TAB_SIZE))

    # ===================================
    # EVENT DATA
    # ===================================
    data_event = None
    # DOWNLOAD ESM EVENT
    url_ESM_event = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event" % (str(event_id), fdsn_client)
    logger.info(f"\trequest \"event.xml\" on: {url_ESM_event}".expandtabs(TAB_SIZE))
    data = DownloadData(url_ESM_event)
    if data:
        data_event = clean_event_data(data)
        any_data_downloaded = True
    else:
        # DOWNLOAD RRSM EVENT
        url_RRSM_event = "http://www.orfeus-eu.org/odcws/rrsm/1/shakemap?eventid=%s&type=event" % (str(event_id))
        logger.info(f"\trequest \"event.xml\" on: {url_RRSM_event}".expandtabs(TAB_SIZE))
        data = DownloadData(url_RRSM_event)
        if data:
            data_event = clean_event_data(data)
            any_data_downloaded = True

    if data_event:
        # Apply optional updates (-u and/or -r) to the event XML before saving
        data_event = update_event_xml(data_event, event_id)
        FNAME_EV = os.path.join(EVENT_DIR, "event.xml")
        relative_path = os.path.relpath(FNAME_EV, args.git_repo_dir)
        result, author = check_repository_file(relative_path)

        if result:
            saveIfChanged(data_event, FNAME_EV, event_id)
        else:
            logger.warning(f"event.xml skipped because modified by the external user: {author}".expandtabs(TAB_SIZE))

    # ===================================


    # RRSM SHAKE DATA
    FILE_NAME_DAT = f"{str(event_id)}_A_RRSM_dat.xml"
    FILE_FULL_NAME_DAT = os.path.join(EVENT_DIR, FILE_NAME_DAT)

    relative_path = os.path.relpath(FILE_FULL_NAME_DAT, args.git_repo_dir)
    result, author = check_repository_file(relative_path)
    if result:
        url_RRSM_dat = "http://www.orfeus-eu.org/odcws/rrsm/1/shakemap?eventid=%s" % (str(event_id))
        logger.info(f"\trequest \"_dat.xml\" on: {url_RRSM_dat}".expandtabs(TAB_SIZE))
        data = DownloadData(url_RRSM_dat)
        if data:
            saveIfChanged(data, FILE_FULL_NAME_DAT, event_id)
            any_data_downloaded = True
    else:
        logger.warning(f"file {FILE_NAME_DAT} skipped because modified by the external user: {author}".expandtabs(TAB_SIZE))


    # FAULT (ESM?) - Only process if at least one data source was successful
    if any_data_downloaded:
        url_str_fault = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event_fault" % (str(event_id), fdsn_client)
        logger.info(f"\trequest \"_fault.xml\" on: {url_str_fault}".expandtabs(TAB_SIZE))
        data = DownloadData(url_str_fault)
        if data:
            jdict = text_to_json(data, new_format=False)
            FNAME_RUPT = os.path.join(EVENT_DIR, "rupture.json")
            relative_path = os.path.relpath(FNAME_RUPT, args.git_repo_dir)
            result, author = check_repository_file(relative_path)

            if result:
                # Convert JSON to bytes and use saveIfChanged to handle git commit
                saveIfChanged(json.dumps(jdict).encode(), FNAME_RUPT, event_id)
            else:
                logger.warning(f"\trupture.json skipped because modified by the external user: {author}".expandtabs(TAB_SIZE))
    else:
        logger.info(f"\tSkipping fault data request - no event data was successfully downloaded".expandtabs(TAB_SIZE))

def text_to_json(data, new_format=True):
    """
    Read in old or new ShakeMap 3 textfile rupture format and convert to
    GeoJSON.

    This will handle ShakeMap3.5-style fault text files, which can have the
    following format:
     - # at the top indicates a reference.
     - Lines beginning with a > indicate the end of one segment and the
       beginning of another.
     - Coordinates are specified in lat,lon,depth order.
     - Coordinates can be separated by commas or spaces.
     - Vertices can be specified in top-edge or bottom-edge first order.

    Args:
        file (str):
            Path to rupture file OR file-like object in GMT
            psxy format, where:

                * Rupture vertices are space/comma separated lat, lon, depth
                  triplets on a single line.
                * Rupture groups are separated by lines containing ">"
                * Rupture groups must be closed.
                * Verticies within a rupture group must start along the top
                  edge and move in the strike direction then move to the bottom
                  edge and move back in the opposite direction.

        new_format (bool):
            Indicates whether text rupture format is
            "old" (lat, lon, depth) or "new" (lon, lat, depth) style.

    Returns:
        dict: GeoJSON rupture dictionary.

    """

    reference = ''
    polygons = []
    polygon = []

    data = data.decode("utf-8")
    for line in data.splitlines():
        if not len(line.strip()):
            continue

        if line.strip().startswith('#'):
            # Get reference string
            reference += line.strip().replace('#', '')
            continue

        if line.strip().startswith('>'):
            if not len(polygon):
                continue
            polygons.append(polygon)
            polygon = []
            continue

        # first try to split on whitespace
        parts = line.split()
        if len(parts) == 1:
            if new_format:
                raise ShakeLibException(
                    'Rupture  [%s] has unspecified delimiters.' % line)
            parts = line.split(',')
            if len(parts) == 1:
                raise ShakeLibException(
                    'Rupture [%s] has unspecified delimiters.' % line)

        if len(parts) != 3:
            msg = 'Rupture [%s] is not in lat, lon, depth format.'
            if new_format:
                'Rupture [%s] is not in lon, lat, depth format.'
            raise ShakeLibException(msg % line)

        parts = [float(p) for p in parts]
        if not new_format:
            old_parts = parts.copy()
            parts[0] = old_parts[1]
            parts[1] = old_parts[0]
        polygon.append(parts)

    if len(polygon):
        polygons.append(polygon)

    # Try to fix polygons
    original_polygons = polygons.copy()
    fixed = []
    n_polygons = len(polygons)
    for i in range(n_polygons):
        n_verts = len(polygons[i])
        success = False
        for j in range(n_verts - 1):
            try:
                _check_polygon(polygons[i])
                success = True
                break
            except ValueError:
                polygons[i] = _rotate_polygon(polygons[i])
        if success:
            fixed.append(True)
        else:
            fixed.append(False)

    if not all(fixed):
        polygons = original_polygons

    json_dict = {
        "type": "FeatureCollection",
        "metadata": {
            'reference': reference
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "rupture type": "rupture extent"
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [polygons]
                }
            }
        ]
    }
    validate_json(json_dict)

    return json_dict

def saveIfChanged(data, FileFullPath, event_id):
    if os.path.isfile(FileFullPath):
        # Check if file is JSON - use simple byte comparison instead of XML diff
        if FileFullPath.endswith('.json'):
            # For JSON files, compare content directly
            with open(FileFullPath, 'rb') as f:
                existing_data = f.read()
            has_changed = (data != existing_data)
        else:
            # For XML files, use xmldiff
            has_changed = diff(data, FileFullPath)

        if has_changed:
            with open (FileFullPath, mode='wb') as f:
                f.write(data)
            msg = f"Update event={event_id}"
            logger.info(f"\t\tcommit: {msg}".expandtabs(TAB_SIZE))
            git_commit(FileFullPath, msg)
    else:
        writeFile(data, FileFullPath)
        msg = f"Add event={event_id}"
        logger.info(f"\t\tcommit: {msg}".expandtabs(TAB_SIZE))
        git_commit(FileFullPath, msg)


def writeFile(data, FileFullPath):
    dir = os.path.dirname(FileFullPath)
    if not os.path.isdir(dir):
        os.makedirs(dir)
    with open(FileFullPath, mode='wb') as f:
        f.write(data)

# set the dictionary of the repository files with the author and date of last modification
def get_repository_files_info(path):
    return {}


def get_git_last_author(repo_path, file_path):
    """
    Returns the last author who modified the file, or None if file does not exist in Git history.
    """
    try:
        output = subprocess.check_output(
            ["git", "-C", repo_path, "log", "-1", "--pretty=format:%an", file_path],
            stderr=subprocess.DEVNULL
        )
        author = output.decode().strip()
        return author if author else None

    except subprocess.CalledProcessError:
        # File not tracked by Git or no commits touching it
        return None


def check_repository_file(file_name):
    """
    Returns (True, None) if the file can be safely created or overwritten.
    Returns (True, username) if the last author is the same as GIT_USERNAME.
    Returns (False, 'other-author') if the file was last modified by someone else.
    """

    repo_path = args.git_repo_dir

    # Full file path inside repository
    file_path = os.path.join(repo_path, file_name)

    # If the file does not exist at all → safe
    if not os.path.exists(file_path):
        return True, None

    # Ask Git for the last author
    author = get_git_last_author(repo_path, file_name)

    # If Git does not know the file → safe
    if author is None:
        return True, None

    # If last author is you → safe
    if author == GIT_USERNAME:
        return True, GIT_USERNAME

    # Otherwise block overwrite
    return False, author


if __name__ == '__main__':

    # define the default value of end_time to 'now'
    default_end_time = UTCDateTime().strftime("%Y-%m-%dT%H:%M:%S")
    #
    # default min magnitude
    default_minmag = 4.0
    #
    # default time backward to cross-check the input files of ESM
    #default_chkbcktime = 1.0 # in days

    parser = argparse.ArgumentParser()

    parser.add_argument("-o", "--output", dest="git_repo_dir", required=True, help="provide the shakemap installation home dir (e.g., /Users/michelini/shakemap_profiles/world)")
    parser.add_argument("-d", "--days_ago", default=None, help="set the number of days before end time (15m, 1d, 5d, 10d, 30d, 365d); [default is 1d: today 00:00 to 23:59]; cannot be used with -k/--keep", choices=['15m', '1d', '5d', '10d', '30d', '365d'])
    parser.add_argument("-s", "--starttime", default=None, help="provide the start time (e.g., 2020-10-23T00:00:00); cannot be used with -d/--days_ago or -k/--keep")
    parser.add_argument("-e", "--endtime", default=None, help="provide the end time (e.g., 2020-10-23T23:59:59); [default is now]; cannot be used with -d/--days_ago or -k/--keep")
    parser.add_argument("-m", "--minmag", nargs="?", default=None, help="provide the minimum magnitude (e.g.,4.5); [default is 4.0]; cannot be used with -k/--keep")
    #parser.add_argument("-b","--chkbcktime", nargs="?", default=default_chkbcktime, help="provide the number of days to check for ESM new input data [default is 1.0]")
    parser.add_argument("-k", "--keep", nargs="?", default=None, help="comma-separated list of event IDs to process (e.g., 20251120_0000107,20251118_0000302); cannot be used with time parameters (-d, -s, -e) or -m/--minmag; if not provided, all events in time range will be processed")
    parser.add_argument("-u", "--update-eventid", action='store_true', default=False, help="if set, updates the 'id' attribute in event.xml to match the event ID used in the query")
    parser.add_argument("-r", "--update-locstring", default=None, choices=['region_name', 'boundary'], help="updates the 'locstring' attribute in event.xml: 'region_name' uses INGV region_name API, 'boundary' uses INGV Flinn-Engdahl boundary API")
    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-l", "--log_severity",
                        type=str,
                        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
                        help="log severity level",
                        default="INFO")

    args = parser.parse_args()    
    set_args()
    logger = create_logger(args.log_severity)
    
    git_pull()
    get_repository_files_info(args.git_repo_dir)

    log_summary_data()
    # my strategy is to have only one variabe shared by all functins, that is args

    # Parse event IDs from --keep option if provided
    keep_ids = None
    if args.keep is not None:
        keep_ids = [eid.strip() for eid in args.keep.split(',')]
        logger.info(f'QUERYING SPECIFIC EVENTS: {keep_ids}')

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
        verbose=args.verbose,
        event_ids=keep_ids
    )

    generate_events_xml_data()
    git_push()
