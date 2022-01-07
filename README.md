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

The script `ee2db.py` inserts earthquake events into the `quakedb` . Its input is the xml file produce by Early-Est. It uses the module: [ee2json](https://gitlab.rm.ingv.it/early-est/ee2json) for converting the input file into the json format and then It calls the [web service](http://caravel-dev.int.ingv.it )  for inserting the events into the `quakedb` database

## 1.1 Files in the project ##

The following files are maintained in the archive:

| file | description |
| ------ | ------ |
| /ee2db.py | the script |
| /test.py | test script |
| README.md | This readme file you are reading |


# 2. Installation #
## 2.1 Python ##

You need Python 3.5+ installed.
We assume, in the rest of this document, that python command points to python 3.5+

- You also need to install pip on your linux system:


    sudo apt-get install python-pip

- You also need to install the module `ee2json`:


```
pip install git+https://gitlab+deploy-token-49:CE8DXPECvX1tHpsy4s5w@gitlab.rm.ingv.it/early-est/ee2json.git
```

The `ee2json` needs the configuration file `.ee2jsonrc`, located in the user home directory

You have to create this file like the following: 

```
{
   "localspace": {
      "name": "early-est-1.2.4_space1",
      "description": ""
   },
   "provenance": {
      "name": "INGV",
      "description": "from WS",
      "softwarename": "early-est",
      "username": "ee"
   }
}
```

Refer to the  [ee2json documentation](https://gitlab.rm.ingv.it/early-est/ee2json) for details.

- Then install the module `jinja2`

```
pip install jinja2
```

- Then You clone the project `ee2db`:


```
git clone https://gitlab.rm.ingv.it/early-est/ee2db
```



# 2.2 ee2db.py

This script uses the module `ee2json`. It adds the events to the `quakedb` by invoking a web service.

Launch the script with the option `-h` to show the usage:

`python ee2db.py -h`

An example of the launch is the following:

`python ee2db.py -x ./input_files/monitor_1.1.9.xml -w http://caravel.int.ingv.it -l DEBUG `

The only mandatory  option is `-x`  followed by the xml file containing the events (this is the file produced by Early-Est).

The log messages are printed to the standard output.

The default value of the log severity is INFO.

if the option `-w` is not provided, the script just log the json-formatted events to the log file (if the log severity level is not greater than INFO)

if the option `-w` is provided, the script calls the service with the href obtained joining the parameter associated to the option (origin) with the pathname: `/api/quakedb/v1/event`

The href relative to the above launch example is: `http://caravel.int.ingv.it/api/quakedb/v1/event`

This script needs two additional python modules: `requests` and `validators`, that are automatically installed when installing the module `ee2json`


## Delete events

ee2db.py registers, at each run, the ids of the elaborated events, in a file (named event list file). At each launch, the first thing it does is to compare the ids generated at the previous launch, with the ones present in the file `hypolist.csv` (provided by early-est), and set to deleted the events present in the event file list but not in `hypolist.csv`. At the end of this operation, it delete the event list file. 

[The following diagram](https://docs.google.com/drawings/d/1Qcd5fMgu4A3OpbrK1ktpNBOMm1N_ITaN6L-PEDYaT4w/edit?usp=sharing) shows this scenario.


# 3 Test the script #

Run the script: test.py

```
python test.py
```

