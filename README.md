

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [1. Introduction](#1-introduction)
  - [1.1 Files in the project](#11-files-in-the-project)
- [2. Installation](#2-installation)
  - [2.1 Python](#21-python)
- [2.2 shakedata.py](#22-shakedatapy)
- [3 Example of use](#3-example-of-use)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# 1. Introduction #

The scope of the project is to maintain a remote shake data repository updated, searching, at time interval,  for new shake data available on the net. 

When a file is discovered to be changed on the remote repository by external users, it is skipped.

  

## 1.1 Files in the project ##

The following files are maintained in the archive:

| file | description |
| ------ | ------ |
| /shakedata.py | the main (and unique) script of the project |
| README.md | This readme file you are reading |

# 2. Installation #

clone the project

```
git clone https://<token>@github.com/INGV/shakemap-input-eu
```

## 2.1 Python ##

You need Python 3.7.0 installed.

You also need to install pip on your linux system:


    sudo apt-get install python-pip

If pip is already installed, upgrade it:

```
pip install --upgrade pip
```

You also need to install some python modules:


```
pip install PyDriller
pip install numpy
pip install Pillow
pip install obspy
pip install requests
```



# 2.2 shakedata.py

The script does the following actions:

- Execute a pull from git repository, whose address is provided by a mandatory option

- Search for all event from ESMC, filtering with the launch options. For each event found do the following actions 

  - set the full name of the three files that contain the data to search for, that is: 
    1. `event data file`: `data/<first six chars of event id>/<event id>/current/event.xml`
    2. `ESM shake file`: `data/<first six chars of event id>/<event id>/current/data/<event id>_B_ESM_dat.xml`
    3. `RRSM shake file`:  `data/<first six chars of event id>/<event id>/current/data/<event id>_A_RRSM_dat.xml`
  - For each one of the files 2. and 3. (shape files), check if it exists on remote repository and, if yes, if the last change on repository have been made from an external user. If yes the search for data relative to that event is not done.
  - search the event data from ESM first and if not found search fro RRSM. if the file is found save it to local file `event data file`. If event data are found from both sites, that from  RRSM will be taken
  - search for shake data from ESM and, if found, save it to local file `ESM shake file`
  - search for shake data from RRSM and, if found, save it to local file `RRSM shake file`

- execute push into remote repository

  


# 3 Example of use #

Run the script with --help option to show the launch syntax

```
python shakedata.py --help
```



The first two mandatory positional arguments are:

1. time before the end_time to search for the event data. Provided value must be one of: `15m, 1d, 5d, 10d, 30d, 365d`
2. repository URL

The other parameter are optional:

- --end_time default value is current time
- --minmag Minimal magnitude for searched events. Default value is `4.0`
- --log_severity Log severity level. One of `DEBUG, INFO, WARN, ERROR, CRITICAL`. Default value is `INFO`
- --verbose If true the summary detail of the events found is logged at the start of the process



With the following launch, the script will search for events between  2020-10-30 and 2020-10-31 and magnitude from 4.0 on.

```
python shakedata.py  1d /data/projects/ingv/sismologia/shakemap-input-eu --end_time 2020-10-31
```

