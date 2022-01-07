<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [1. Introduction](#1-introduction)
  - [1.1 Files in the project](#11-files-in-the-project)
- [2. Installation](#2-installation)
  - [2.1 Python](#21-python)
- [2.2 ee2db.py](#22-ee2dbpy)
  - [Delete events](#delete-events)
- [3 Test the script](#3-test-the-script)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# 1. Introduction #

The scope of the project is to maintain a remote shake data repository updated, searching, at time interval,  for new shake data available on the net. 

When a file is discovered to be changed on the remote repository by external users, it is skipped.

  

## 1.1 Files in the project ##

The following files are maintained in the archive:

| file | description |
| ------ | ------ |
| /shakedata.py | the main (and unique) script of the project |
| /requirements.txt | needed python modules |
| README.md | This readme file you are reading |


# 2. Installation #
## 2.1 Python ##

You need Python 3.6+ installed.
We assume, in the rest of this document, that python command points to python 3.6+

- You also need to install pip on your linux system:


    sudo apt-get install python-pip

- You also need to install some python modules:


```
pip install --no-cache-dir -r requirements.txt
```



# 2.2 shakedata.py

The script does the following actions:

- Execute a pull from git repository, whose address is provided by a mandatory option

- Search for all event from ESMC, filtering with the launch options. For each event found do the following actions 

  - set the full name of the three files that contain the data to search for, that is: 
    1. `event data file`: `data/<first six chars of event id>/<event id>/current/event.xml`
    2. `ESM shake file`: `data/<first six chars of event id>/<event id>/current/data/<event id>_B_ESM_dat.xml`
    3. `RRSM shake file`:  `data/<first six chars of event id>/<event id>/current/data/<event id>_A_RRSM_dat.xml`
  - For each one of these files, check if it exists on remote repository and, if yes, if the last change on repository have been made from an external user. If yes the search for data relative to that event is not done
  - search for event data from ESM and RRSM sites ad, if found, save it to local file `event data file`. If event data are found from both sites, that from  RRSM will be taken
  - search for shake data from ESM and, if found, save it to local file `ESM shake file`
  - search for shake data from RRSM and, if found, save it to local file `RRSM shake file`

- execute push into remote repository

  


# 3 Example of use #

Run the script: test.py

```
python test.py
```

