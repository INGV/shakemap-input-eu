#!/bin/bash
#
#
# (c) 2022 Valentino Lauciani <valentino.lauciani@ingv.it>,
#          Sergio Bruni <sergio.bruni@ingv.it>,
#          Istituto Nazione di Geofisica e Vulcanologia.
# 
#####################################################

# Set env
export MPLCONFIGDIR="/tmp"

# Check input parameter
if [[ -z ${@} ]]; then
    echo ""
    /usr/local/bin/python /opt/shakemap-input-eu/shakedata.py -h
    echo ""
    exit 1
fi

# run command
/usr/local/bin/python /opt/shakemap-input-eu/shakedata.py $@
