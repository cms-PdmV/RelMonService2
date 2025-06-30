# !/bin/bash
# This script sets the required environment variables for
# deploying the application. Source its content!

# RelMonService2 endpoints
export CALLBACK_URL="http://$(hostname):10000/relmonservice/api/update"
export SERVICE_URL="http://$(hostname):10000/relmonservice"

# RelMon Reports page
# TODO: Set the web server url for related to the WebEOS site
# deployed via CERN Web Services. This URL will be something like
# e.g: relmon-mytest.web.cern.ch
export REPORTS_URL=""

# Submission host to access HTCondor
# In case you have issues opening the SSH session, change
# this property to a specific node inside the lxplus8 pool.
export SUBMISSION_HOST="lxplus8.cern.ch"

# Default CMSSW release for picking the RelMon generation module.
export CMSSW_RELEASE='CMSSW_14_1_0_pre7'

# The following directory is relative to $HOME for the
# user used in the $SUBMISSION_HOST. Make sure the directory exists!
# e.g: export REMOTE_DIRECTORY="test/relmonservice/jobs/"
# TODO: Create the folder and assign the relative path.
export REMOTE_DIRECTORY=""

# Service account to access the submission host
# TODO: Set the username for opening the SSH session.
export SERVICE_ACCOUNT_USERNAME=""

# Service account password, provide the real one only if
# your runtime environment does not have Kerberos enabled.
export SERVICE_ACCOUNT_PASSWORD="NotRequiredToSet"

# Absolute path to a folder to store the reports
# This is the folder you will link on the WebEOS site for rendering the
# reports.
# This folder must be reachable from the submission host and the HTCondor
# pool running the job so it can copy the file directly.
# e.g: export WEB_LOCATION_PATH="/eos/user/u/user/test/relmonservice/reports"
#
# TODO: Set the WebEOS site path
export WEB_LOCATION_PATH=""

# MongoDB configuration
export MONGO_DB_HOST="127.0.0.1"

# TODO: Set the MongoDB port to be exported in the host scope!
export MONGO_DB_PORT=""

# TODO: Set the MongoDB administrator user
export MONGO_DB_USER=""

# TODO: Set its password
export MONGO_DB_PASSWORD=""

# Flask configuration for session cookies
export SECRET_KEY="$(openssl rand -base64 64 | sed 's#/#!#g')"

# The following is used to perform callbacks, set a real value
# in case an authentication middleware is set for your 
# development deployment.

# Related to the RelmonService2 deployment.
export CLIENT_ID="NotRequiredToSet"

# Credentials for requesting a token.
export CALLBACK_CLIENT_ID="NotRequiredToSet"
export CALLBACK_CLIENT_SECRET="NotRequiredToSet"
export DISABLE_CALLBACK_CREDENTIALS="True"

# The following is required by Docker Compose
# to properly match the running host user so that host
# volumes access is granted properly
export UID=$(id -u)
export GID=$(id -g)
