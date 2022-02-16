import os.path
import requests
import json
import xml.etree.ElementTree as ET
from obspy import UTCDateTime, Catalog
from obspy.clients.fdsn import Client
import git
from pathlib import Path
import logging
import argparse
import sys
import inspect
import functools
from pydriller import Repository
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
# global logger
logger = None

# repository files
# this dictionary contains, for each file in the git repository
# the author and date of last modification
repository_files = {}

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
    if args.days == '15m':
        args.days = 1./24. * 0.25
    else:
        args.days = float(args.days[:-1])

    args.minmag = float(args.minmag)

    # time to verify backward if input files from ESM have changed
    #args.chkbcktime = float(args.chkbcktime) * ONEDAY # in seconnds

    # define the number of seconds in order to calculate the start_time
    # identify start and end times of the last month
    try:
        appo = UTCDateTime(args.end_time) - args.days * ONEDAY
    except Exception as e:
        sys.exit(f"option --end_time is not valid time {args.end_time}. {str(e)}")

    args.start_time =  appo.strftime("%Y-%m-%dT%H:%M:%S")
    #

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
    logger.info(f"\tMINMAG: {args.minmag}.1f".expandtabs(TAB_SIZE))
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
    origin = repo.remote(name='origin_ssh')
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

    # ESM SHAKE DATA
    FILE_NAME_DAT = f"{str(event_id)}_B_ESM_dat.xml"
    FILE_FULL_NAME_DAT = os.path.join(EVENT_DIR, FILE_NAME_DAT)

    result, author = check_repository_file(FILE_NAME_DAT)
    if result:
        url_ESM_dat = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event_dat" % (str(event_id), fdsn_client)
        logger.info(f"\trequest _dat.xml on: {url_ESM_dat}".expandtabs(TAB_SIZE))
        data = DownloadData(url_ESM_dat)
        if data:
            saveIfChanged(data, FILE_FULL_NAME_DAT, event_id)
    else:
        logger.warning(f"\tfile {FILE_NAME_DAT} skipped because modified by the external user: {author}".expandtabs(TAB_SIZE))

    # ===================================
    # EVENT DATA
    # ===================================
    data_event = None
    # DOWNLOAD ESM EVENT
    url_ESM_event = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event" % (str(event_id), fdsn_client)
    logger.info(f"\trequest event.xml on: {url_ESM_event}".expandtabs(TAB_SIZE))
    data = DownloadData(url_ESM_event)
    if data:
        data_event = clean_event_data(data)
    else:
        # DOWNLOAD RRSM EVENT
        url_RRSM_event = "http://www.orfeus-eu.org/odcws/rrsm/1/shakemap?eventid=%s&type=event" % (str(event_id))
        logger.info(f"\trequest event.xml on: {url_RRSM_event}".expandtabs(TAB_SIZE))
        data = DownloadData(url_RRSM_event)
        if data:
            data_event = clean_event_data(data)

    if data_event:
        FNAME_EV = os.path.join(EVENT_DIR, "event.xml")
        saveIfChanged(data_event, FNAME_EV, event_id)
    # ===================================


    # RRSM SHAKE DATA
    FILE_NAME_DAT = f"{str(event_id)}_A_RRSM_dat.xml"
    FILE_FULL_NAME_DAT = os.path.join(EVENT_DIR, FILE_NAME_DAT)

    result, author = check_repository_file(FILE_NAME_DAT)
    if result:
        url_RRSM_dat = "http://www.orfeus-eu.org/odcws/rrsm/1/shakemap?eventid=%s" % (str(event_id))
        logger.info(f"\trequest _dat.xml on: {url_RRSM_dat}".expandtabs(TAB_SIZE))
        data = DownloadData(url_RRSM_dat)
        if data:
            saveIfChanged(data, FILE_FULL_NAME_DAT, event_id)
    else:
        logger.warning(f"file {FILE_NAME_DAT} skipped because modified by the external user: {author}".expandtabs(TAB_SIZE))


    # FAULT (ESM?)
    url_str_fault = "https://esm-db.eu/esmws/shakemap/1/query?eventid=%s&catalog=%s&format=event_fault" % (str(event_id), fdsn_client)
    logger.info(f"\trequest _fault.xml on: {url_str_fault}".expandtabs(TAB_SIZE))
    data = DownloadData(url_str_fault)
    if data:
        jdict = text_to_json(data, new_format=False)
        FNAME_RUPT = os.path.join(EVENT_DIR, "rupture.json")
        writeFile(json.dumps(jdict).encode(), FNAME_RUPT)

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
        if diff(data, FileFullPath):
            with open (FileFullPath, mode='wb') as f:
                f.write(data)
            msg = f"Update event={event_id}"
            logger.info(f"\tcommit: {msg}".expandtabs(TAB_SIZE))
            git_commit(FileFullPath, msg)
    else:
        writeFile(data, FileFullPath)
        msg = f"Add event={event_id}"
        logger.info(f"\tcommit: {msg}".expandtabs(TAB_SIZE))
        git_commit(FileFullPath, msg)


def writeFile(data, FileFullPath):
    dir = os.path.dirname(FileFullPath)
    if not os.path.isdir(dir):
        os.makedirs(dir)
    with open(FileFullPath, mode='wb') as f:
        f.write(data)

# set the dictionary of the repository files with the author and date of last modification
def get_repository_files_info():
    rm = Repository(args.git_repo_dir+'/.git')
    for commit in rm.traverse_commits():
        for f in commit.modified_files:
            repository_files[f.filename] = {
                'author': commit.author.name,
                'date': commit.author_date.date()
            }

'''
returns true if the file do not exist on the repository or the author of its last modification is GIT_USERNAME
'''
def check_repository_file(file_name):
    if file_name not in repository_files:
        return True, None

    if repository_files[file_name]['author'] == GIT_USERNAME:
        return True, GIT_USERNAME

    return False, repository_files[file_name]['author']


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

    parser.add_argument("days",  help="set the number of days before end time (15m, 1d, 5d, 10d, 30d, 365d)", choices=['15m', '1d', '5d', '10d', '30d', '365d'])
    parser.add_argument("git_repo_dir", help="provide the shakemap installation home dir (e.g., /Users/michelini/shakemap_profiles/world)")
    parser.add_argument("-e","--end_time", nargs="?", default=default_end_time, help="provide the end time  (e.g., 2020-10-23); [default is now]")
    parser.add_argument("-m","--minmag", nargs="?", default=default_minmag, help="provide the minimum magnitude (e.g.,4.5); [default is 4.0]")
    #parser.add_argument("-b","--chkbcktime", nargs="?", default=default_chkbcktime, help="provide the number of days to check for ESM new input data [default is 1.0]")
    parser.add_argument("-v","--verbose", action='store_true')
    parser.add_argument("-l", "--log_severity",
                        type=str,
                        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
                        help="log severity level",
                        default="INFO")

    args = parser.parse_args()
    set_args()
    logger = create_logger(args.log_severity)

    git_pull()
    get_repository_files_info()

    log_summary_data()
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
        verbose=args.verbose
    )

    generate_events_xml_data()
    git_push()







