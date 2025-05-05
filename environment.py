"""
This module parses some configuration variables from
the runtime environment to use them in different sections
from this application

Attributes:
    CALLBACK_URL (str): This is the url for the endpoint that HTCondor
        jobs use to update the status for the running RelMon job.
        For example: "https://cms-pdmv-prod.web.cern.ch/relmonservice/api/update"
        For more details, please see the endpoint definition: /api/update.
    SERVICE_URL (str): This is the url for RelMonService2 application.
        For example: "https://cms-pdmv-prod.web.cern.ch/relmonservice"
        It is used to include the application's url into email notifications
        and for request cookies/tokens for authenticating callback request.
    REPORTS_URL (str): This is the url for RelMon report page. 
        For example: "https://cms-pdmv-prod.web.cern.ch/relmon"
        This is a static web page that renders all outputs for the reports.
    SUBMISSION_HOST (str): This is the server where this application will open an SSH session
        to submit jobs through HTCondor. For example: "lxplus.cern.ch"
    REMOTE_DIRECTORY (str): This is the folder (into AFS or EOS) that stores 
        all the required bundle files to submit a HTCondor job.
    SERVICE_ACCOUNT_USERNAME (str): Username to authenticate to `SUBMISSION_HOST`
    SERVICE_ACCOUNT_PASSWORD (str): Password to authenticate to `SUBMISSION_HOST`
    EMAIL_AUTH_REQUIRED (bool): If this environment variable is provided,
        the email client will authenticate to the email server. By default it is false,
        because this anonymous server does not require to authenticate.
    WEB_LOCATION_PATH (str): This is the path (AFS or EOS)
        where all RelMon reports are going to be stored. This is the path used by `REPORT_URL`
        application to load the reports static files.
    TICK_INTERNAL (int): Elapsed time in seconds to perform a tick, please see `controller.tick()`
        for more details.
    MONGO_DB_HOST (str): MongoDB host for opening a client session.
    MONGO_DB_PORT (int): MongoDB port for opening a client session.
    MONGO_DB_USER (str): MongoDB user to authenticate a new client session.
    MONGO_DB_PASSWORD (str): MongoDB password to authenticate a new client session.
    HOST (str): Flask listening hostname
    PORT (int): Flask port
    DEBUG (bool): Enables DEBUG mode for RelMonService2 application
    ENABLE_AUTH_MIDDLEWARE (bool): Enables the AuthenticationMiddleware to parse JWT 
        or enable the application to handle OIDC flow by itself.
    SECRET_KEY (str): Flask secret key.
    CLIENT_ID (str): Client ID related to RelMonService2 application
        or the reverse proxy that provides authentication.
    CALLBACK_CLIENT_ID (str): Client ID for CLI integration application.
    CALLBACK_CLIENT_SECRET (str): Client secret for CLI integration application.
    CMSSW_RELEASE (str): cms-sw version to use for generating the monitoring report.
    HTCONDOR_CAF_POOL (bool): If this environment variable is provided,
        RelMon batch jobs will be configured to run inside the dedicated pool CMS CAF.
        Otherwise, they will run in the public shared pool.
    FILE_CREATOR_GIT_SOURCE (str): RelMonService2 source code to load inside the
        HTCondor batch jobs.
    FILE_CREATOR_GIT_BRANCH (str): Branch to use from `FILE_CREATOR_GIT_SOURCE`.
"""
import os
import inspect

# RelMonService2 application
CALLBACK_URL: str = os.getenv("CALLBACK_URL", "")
SERVICE_URL: str = os.getenv("SERVICE_URL", "")
REPORTS_URL: str = os.getenv("REPORTS_URL", "")
SUBMISSION_HOST: str = os.getenv("SUBMISSION_HOST", "")
REMOTE_DIRECTORY: str = os.getenv("REMOTE_DIRECTORY", "")
SERVICE_ACCOUNT_USERNAME: str = os.getenv("SERVICE_ACCOUNT_USERNAME", "")
SERVICE_ACCOUNT_PASSWORD: str = os.getenv("SERVICE_ACCOUNT_PASSWORD", "")
EMAIL_AUTH_REQUIRED: bool = bool(os.getenv("EMAIL_AUTH_REQUIRED"))
WEB_LOCATION_PATH: str = os.getenv("WEB_LOCATION_PATH", "")
TICK_INTERVAL: int = int(os.getenv("TICK_INTERVAL", "600"))
CMSSW_RELEASE: str = os.getenv("CMSSW_RELEASE", "CMSSW_11_0_4")

# MongoDB database
MONGO_DB_HOST: str = os.getenv("MONGO_DB_HOST", "")
MONGO_DB_PORT: int = int(os.getenv("MONGO_DB_PORT", "27017"))
MONGO_DB_USER: str = os.getenv("MONGO_DB_USER", "")
MONGO_DB_PASSWORD: str = os.getenv("MONGO_DB_PASSWORD", "")

# Flask web server
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
DEBUG: bool = bool(os.getenv("DEBUG"))
ENABLE_AUTH_MIDDLEWARE: bool = bool(os.getenv("ENABLE_AUTH_MIDDLEWARE"))

# OAuth2 credentials
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
CLIENT_ID: str = os.getenv("CLIENT_ID", "")
CALLBACK_CLIENT_ID: str = os.getenv("CALLBACK_CLIENT_ID", "")
CALLBACK_CLIENT_SECRET: str = os.getenv("CALLBACK_CLIENT_SECRET", "")
DISABLE_CALLBACK_CREDENTIALS = bool(os.getenv("DISABLE_CALLBACK_CREDENTIALS"))

# HTCondor submission pool
HTCONDOR_CAF_POOL = bool(os.getenv("HTCONDOR_CAF_POOL"))
HTCONDOR_MODULE = "lxbatch/tzero" if HTCONDOR_CAF_POOL else "lxbatch/share"

# Repository source for the remote execution in HTCondor.
FILE_CREATOR_GIT_SOURCE: str = os.getenv("FILE_CREATOR_GIT_SOURCE", "https://github.com/cms-PdmV/relmonservice2.git")
FILE_CREATOR_GIT_BRANCH: str = os.getenv("FILE_CREATOR_GIT_BRANCH", "master")

# Check that all environment variables are provided
missing_environment_variables: dict[str, str] = {
    k: v
    for k, v in globals().items()
    if not k.startswith("__")
    and not inspect.ismodule(v)
    and not isinstance(v, bool)
    and not v
}

if missing_environment_variables:
    msg: str = (
        "There are some environment variables "
        "required to be set before running this application\n"
        "Please set the following values via environment variables\n"
        "For more details, please see the description available into `environment.py` module\n"
        f"{list(missing_environment_variables.keys())}"
    )
    raise RuntimeError(msg)
