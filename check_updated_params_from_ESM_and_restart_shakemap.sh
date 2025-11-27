#!/bin/bash
# ------------------------------------------------------------
# Author      : Valentino Lauciani
# Date        : 06/05/2025
# ------------------------------------------------------------
#

# Check for required commands
REQUIRED_COMMANDS=("curl" "jq" "date")
for CMD in "${REQUIRED_COMMANDS[@]}"; do
    if ! command -v "$CMD" >/dev/null 2>&1; then
        echo "[ERROR] Required command '$CMD' is not installed." >&2
        exit 1
    fi
done

# Detect OS type for cross-platform date compatibility
OS_TYPE=$(uname)

# Functions
function date_start () {
        if [[ "$OS_TYPE" == "Darwin" ]]; then
            # macOS
            DATE_START=$(date +%Y-%m-%d_%H:%M:%S)
        else
            # Linux
            DATE_START=$(date +%Y-%m-%d_%H:%M:%S)
        fi
        echo -------------------- START - $(basename $0) - ${DATE_START} --------------------
}
function date_end () {
        if [[ "$OS_TYPE" == "Darwin" ]]; then
            # macOS
            DATE_END=$(date +%Y-%m-%d_%H:%M:%S)
        else
            # Linux
            DATE_END=$(date +%Y-%m-%d_%H:%M:%S)
        fi
        echo -------------------- END - $(basename $0) - ${DATE_END} --------------------
        echo ""
}
function echo_date() {
        if [[ "$OS_TYPE" == "Darwin" ]]; then
            # macOS
            DATE_ECHO=$(date +%Y-%m-%d_%H:%M:%S)
        else
            # Linux
            DATE_ECHO=$(date +%Y-%m-%d_%H:%M:%S)
        fi
        echo "[${DATE_ECHO}] - ${1}"
}
function usage() {
    echo "Usage: $(basename "$0") [-u YYYY-MM-DDThh:mm:ss]"
    echo "  -u    Specify the updatedafter date in format YYYY-MM-DDThh:mm:ss"
    echo "If -u is provided, it must be followed by a value."
    date_end
    exit 1
}

# Set variables
DIRHOME=${HOME}
DIRWORK=$( cd $(dirname $0) ; pwd)
DIRTMP=/tmp
FILE_RESPONSE="${DIRTMP}/$(basename $0)__response.txt"
FILE_UPDATEDAFTER="/tmp/$(basename $0)__updatedafter.txt"
NOW=$(date +%Y-%m-%dT%H:%M:%S)
SET_FILE_UPDATEDAFTER=0
# ESM Variables
BASE_URL="https://esm-db.eu/esmws/event-processing-update/1/query"
MINLAT="27"
MAXLAT="81"
MINLON="-32"
MAXLON="51"
MINMAG="4"
INDENT="true"

date_start

# Check IF DIRTMP exists
if [ ! -d "${DIRTMP}" ]; then
    echo "[ERROR] Temporary directory ${DIRTMP} does not exist." >&2
    date_end
    exit 1
fi

# Parse options for -u using getopts
UPDATEDAFTER_OPT=""
while getopts ":u:" opt; do
    case $opt in
        u)
            UPDATEDAFTER_OPT="$OPTARG"
            ;;
        \?)
            echo "Invalid option: -$OPTARG"
            usage
        ;;
        :)
            echo "Option -$OPTARG requires an argument"
            usage
        ;;
    esac
done

if [ -n "$UPDATEDAFTER_OPT" ]; then
    # Validate format: YYYY-MM-DDThh:mm:ss
    if [[ ! "$UPDATEDAFTER_OPT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$ ]]; then
        error_msg "Error: UPDATEDAFTER provided with -s must be in format YYYY-MM-DDThh:mm:ss"
        exit 1
    fi
    # Validate date
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        # macOS: use -j -f for parsing
        if ! date -j -f "%Y-%m-%dT%H:%M:%S" "$UPDATEDAFTER_OPT" "+%Y-%m-%dT%H:%M:%S" >/dev/null 2>&1; then
            error_msg "Error: UPDATEDAFTER provided with -s is not a valid date"
            exit 1
        fi
    else
        # Linux: use -d
        if ! date -d "$UPDATEDAFTER_OPT" "+%Y-%m-%dT%H:%M:%S" >/dev/null 2>&1; then
            error_msg "Error: UPDATEDAFTER provided with -s is not a valid date"
            exit 1
        fi
    fi
    UPDATEDAFTER="$UPDATEDAFTER_OPT"
    echo_date "Using UPDATEDAFTER from option: $UPDATEDAFTER"
elif [ -f "$FILE_UPDATEDAFTER" ]; then
    UPDATEDAFTER=$(cat "$FILE_UPDATEDAFTER")
    echo_date "Using UPDATEDAFTER from $FILE_UPDATEDAFTER: $UPDATEDAFTER"
else
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        # macOS: use -v for date arithmetic
        UPDATEDAFTER=$(date -v-1d +%Y-%m-%dT%H:%M:%S)
    else
        # Linux: use -d
        UPDATEDAFTER=$(date -d "1 days ago" +%Y-%m-%dT%H:%M:%S)
    fi
    echo_date "Computed UPDATEDAFTER: $UPDATEDAFTER"
fi
echo ""

# Construct URL
URL="${BASE_URL}?updatedafter=${UPDATEDAFTER}&minlat=${MINLAT}&maxlat=${MAXLAT}&minlon=${MINLON}&maxlon=${MAXLON}&minmag=${MINMAG}&indent=${INDENT}"

echo_date "[INFO] Constructed URL: $URL"

# Fetch JSON data and HTTP status code
TMP_RESPONSE_FILE=$(mktemp)
HTTP_STATUS=$(curl -s -m 60 -w "%{http_code}" -o "$TMP_RESPONSE_FILE" "$URL")

# if HTTP_STATUS is equal to "200", the request was successful
if [ "$HTTP_STATUS" -eq 200 ]; then
    RESPONSE=$(cat "$TMP_RESPONSE_FILE")
    rm -f "$TMP_RESPONSE_FILE"

    if [ -z "$RESPONSE" ]; then
        echo_date "[ERROR] No response received from the API." >&2
        exit 1
    fi

    echo_date "[INFO] Successfully fetched data from API. Parsing ingv_event_id values..."
    # Parse and print ingv_event_id for each event

    EVENTIDS=$( echo "$RESPONSE" | jq -r '[.[] | .emsc_event_id // empty] | join(",")' )
    echo_date " EVENTIDS: $EVENTIDS"
    cd ${DIRWORK}
    docker run --rm -v $(pwd):/opt/shakemap-input-eu -v $(pwd)/ssh_key:/home/shake/.ssh ingv/shakemap-input-eu -o /opt/shakemap-input-eu -k ${EVENTIDS}

    # Set SET_FILE_UPDATEDAFTER
    SET_FILE_UPDATEDAFTER=1
elif [ "$HTTP_STATUS" -eq 204 ]; then
    echo_date "[INFO] No data: ${HTTP_STATUS}"
    rm -f "$TMP_RESPONSE_FILE"
    
    # Set SET_FILE_UPDATEDAFTER
    SET_FILE_UPDATEDAFTER=1
else
    echo_date "[ERROR] HTTP request failed with status code: ${HTTP_STATUS}"
    echo_date "[ERROR] Response body:"
    cat "$TMP_RESPONSE_FILE" >&2
    rm -f "$TMP_RESPONSE_FILE"

    date_end
    exit 1
fi

if (( ${SET_FILE_UPDATEDAFTER} == 1 )); then
    # Save NOW as new UPDATEDAFTER for next run
    echo "${NOW}" > "$FILE_UPDATEDAFTER"
    echo_date "[INFO] Saved new UPDATEDAFTER to $FILE_UPDATEDAFTER: $NOW"
fi

date_end
