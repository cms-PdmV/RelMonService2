"""
Module for FileCreator
"""
import json
from environment import (
    REMOTE_DIRECTORY,
    WEB_LOCATION_PATH,
    SERVICE_URL,
    CALLBACK_URL,
    CALLBACK_CLIENT_ID,
    CALLBACK_CLIENT_SECRET,
    CLIENT_ID,
)


class FileCreator:
    """
    File creator creates bash executable for condor and condor submission job file
    """

    def __init__(self):
        self.remote_location = REMOTE_DIRECTORY
        self.web_location = WEB_LOCATION_PATH
        if self.web_location[-1] == "/":
            self.web_location = self.web_location[:-1]

        self.cookie_url = SERVICE_URL
        self.callback_url = CALLBACK_URL

    def create_job_script_file(self, relmon):
        """
        Create bash executable for condor
        """
        relmon_id = relmon.get_id()
        cpus = relmon.get_cpu()
        relmon_name = relmon.get_name()
        script_file_name = "relmons/%s/RELMON_%s.sh" % (relmon_id, relmon_id)
        old_web_sqlite_path = "%s/%s*.sqlite" % (self.web_location, relmon_id)
        web_sqlite_path = '"%s/%s___%s.sqlite"' % (
            self.web_location,
            relmon_id,
            relmon_name,
        )
        script_file_content = [
            "#!/bin/bash",
            "DIR=$(pwd)",
            "export HOME=$(pwd)",
            # Clone the relmon service
            "git clone https://github.com/cms-PdmV/relmonservice2.git",
            # FIXME: After merging this with master, include the old content
            # available into this file. This is, the fallback mechanism to download
            # the source code as .zip file
            "git fetch && git checkout SSOMigrationV2",
            "git pull origin SSOMigrationV2",
            # CMSSW environment setup
            "source /cvmfs/cms.cern.ch/cmsset_default.sh",
            "scramv1 project CMSSW CMSSW_11_0_4",
            "cd CMSSW_11_0_4/src",
            # Open scope for CMSSW
            "(",
            "eval `scramv1 runtime -sh`",
            "cd ../..",
            # Create reports directory
            "mkdir -p Reports",
            # Run the remote apparatus
            "python relmonservice2/remote/remote_apparatus.py "  # No newline
            "-r RELMON_%s.json -p proxy.txt --cpus %s --callback %s"
            % (relmon_id, cpus, self.callback_url),
            # Close scope for CMSSW
            ")",
            "cd $DIR",
            # Remove all root files
            "rm *.root",
            # Copy sqlitify to Reports directory
            "cp relmonservice2/remote/sqltify.py Reports/sqltify.py",
            # Go to reports directory
            "cd Reports",
            # Try to copy existing reports file
            "EXISTING_REPORT=$(ls -1 %s | head -n 1)" % (old_web_sqlite_path),
            'echo "Existing file name: $EXISTING_REPORT"',
            'if [ ! -z "$EXISTING_REPORT" ]; then',
            '  echo "File exists"',
            '  time rsync -v "$EXISTING_REPORT" reports.sqlite',
            "fi",
            # Run sqltify
            "python3 sqltify.py",
            # Checksum for created sqlite
            'echo "HTCondor workspace"',
            'echo "MD5 Sum"',
            "md5sum reports.sqlite",
            # List sizes
            "ls -l reports.sqlite",
            # Do integrity check
            'echo "Integrity check:"',
            'echo "PRAGMA integrity_check;" | sqlite3 reports.sqlite',
            # Remove old sql file from web path
            'if [ ! -z "$EXISTING_REPORT" ]; then',
            '  rm -f "$EXISTING_REPORT"',
            "fi",
            # Copy reports sqlite to web path
            "time rsync -v reports.sqlite %s" % (web_sqlite_path),
            # Checksum for created sqlite
            'echo "EOS space"',
            'echo "MD5 Sum"',
            "md5sum %s" % (web_sqlite_path),
            # List sizes
            "ls -l %s" % (web_sqlite_path),
            # Do integrity check
            'echo "Integrity check:"',
            'echo "PRAGMA integrity_check;" | sqlite3 %s' % (web_sqlite_path),
            "cd $DIR",
            "cp cookie.txt relmonservice2/remote",
            "python3 relmonservice2/remote/remote_apparatus.py "  # No newlines here
            "-r RELMON_%s.json --callback %s --notifydone"
            % (relmon_id, self.callback_url),
        ]

        script_file_content_string = "\n".join(script_file_content)
        with open(script_file_name, "w") as output_file:
            output_file.write(script_file_content_string)

    @classmethod
    def create_relmon_file(cls, relmon):
        """
        Dump relmon to a JSON file
        """
        relmon_id = relmon.get_id()
        relmon_data = relmon.get_json()
        relmon_file_name = "relmons/%s/RELMON_%s.json" % (relmon_id, relmon_id)
        with open(relmon_file_name, "w") as output_file:
            json.dump(relmon_data, output_file, indent=2, sort_keys=True)

    @classmethod
    def create_condor_job_file(cls, relmon):
        """
        Create a condor job file for a relmon
        """
        relmon_id = relmon.get_id()
        cpus = relmon.get_cpu()
        memory = relmon.get_memory()
        disk = relmon.get_disk()
        condor_file_name = "relmons/%s/RELMON_%s.sub" % (relmon_id, relmon_id)
        credentials_env = (
            f"CALLBACK_CLIENT_ID={CALLBACK_CLIENT_ID} "
            f"CALLBACK_CLIENT_SECRET={CALLBACK_CLIENT_SECRET} "
            f"APPLICATION_CLIENT_ID={CLIENT_ID}"
        )
        credentials_env_arg = f'"{credentials_env}"'
        condor_file_content = [
            "executable             = RELMON_%s.sh" % (relmon_id),
            'environment            = "%s"' % (credentials_env_arg),
            "output                 = RELMON_%s.out" % (relmon_id),
            "error                  = RELMON_%s.err" % (relmon_id),
            "log                    = RELMON_%s.log" % (relmon_id),
            "transfer_input_files   = RELMON_%s.json,proxy.txt" % (relmon_id),
            "when_to_transfer_output = on_exit",
            "request_cpus           = %s" % (cpus),
            "request_memory         = %s" % (memory),
            "request_disk           = %s" % (disk),
            '+JobFlavour            = "tomorrow"',
            "+JobPrio               = 100",
            'requirements           = (OpSysAndVer =?= "CentOS7")',
            # Leave in queue when status is DONE for two hours - 7200 seconds
            "leave_in_queue         = JobStatus == 4 && (CompletionDate =?= UNDEFINED"
            "                         || ((CurrentTime - CompletionDate) < 7200))",
            '+AccountingGroup       = "group_u_CMS.CAF.PHYS"',
            "queue",
        ]

        condor_file_content_string = "\n".join(condor_file_content)
        with open(condor_file_name, "w") as output_file:
            output_file.write(condor_file_content_string)
