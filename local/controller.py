"""
RelMon report production controller
Runs main loop that checks status and acts accordingly
"""

import logging
import time
from multiprocessing import Manager
from couchdb_database import Database
from local.ssh_executor import SSHExecutor
from local.relmon import RelMon
from local.file_creator import FileCreator


class Controller(object):

    # Directory in remote host to keep files for submission and collect output
    __remote_directory = 'relmon_test/'
    # Place where results should be moved
    __web_location = '/eos/project/c/cmsweb/www/pdmv-web-test/relmon_test/'

    def __init__(self):
        self.logger = logging.getLogger('logger')
        self.logger.info('***** Creating a controller! *****')
        self.is_tick_running = False
        self.db = Database()
        self.ssh_executor = SSHExecutor()
        self.file_creator = FileCreator(self.__remote_directory,
                                        self.__web_location)
        # Multithread manager
        manager = Manager()
        # Lists of relmon ids
        self.relmons_to_reset = manager.list()
        self.relmons_to_delete = manager.list()

    def tick(self):
        """
        Controller works by doing "ticks" every once in a while
        During a tick it shoud check all existing relmon's and
        their status and, if necessary, perform actions like
        submission or output collection
        Actions go like this:
        * Delete relmons that are in deletion list
        * Reset relmons that are in reset list
        * Check running relmons
        * Submit new relmons
        """
        self.logger.info('Controller will tick')
        tick_start = time.time()
        # Delete relmons
        self.logger.info('Relmons to delete (%s): %s.',
                         len(self.relmons_to_delete),
                         ','.join(self.relmons_to_delete))
        for relmon_id in self.relmons_to_delete:
            self.__delete_relmon(relmon_id)
            self.relmons_to_delete.remove(relmon_id)

        # Reset relmons
        self.logger.info('Relmons to reset (%s): %s.',
                         len(self.relmons_to_reset),
                         ', '.join(self.relmons_to_reset))
        for relmon_id in self.relmons_to_reset:
            self.__reset_relmon(relmon_id)
            self.relmons_to_reset.remove(relmon_id)

        # Check relmons
        relmons_to_check = self.db.get_relmons_with_status('submitted', include_docs=True)
        relmons_to_check.extend(self.db.get_relmons_with_status('running', include_docs=True))
        relmons_to_check.extend(self.db.get_relmons_with_status('finishing', include_docs=True))
        relmons_to_check.extend(self.db.get_relmons_with_status('finished', include_docs=True))
        self.logger.info('Relmons to check (%s): %s.',
                         len(relmons_to_check),
                         ', '.join(r.get('id') for r in relmons_to_check))
        for relmon_json in relmons_to_check:
            relmon = RelMon(relmon_json)
            self.__check_if_running(relmon)
            condor_status = relmon.get_condor_status()
            if condor_status in ['DONE', 'REMOVED']:
                # Refetch after check if running save
                relmon = RelMon(self.db.get(relmon.get_id()))
                self.__collect_output(relmon)

        # Submit relmons
        relmons_to_submit = self.db.get_relmons_with_status('new', include_docs=True)
        self.logger.info('Relmons to submit (%s): %s.',
                         len(relmons_to_submit),
                         ', '.join(r.get('id') for r in relmons_to_submit))
        for relmon_json in relmons_to_submit:
            relmon = RelMon(relmon_json)
            status = relmon.get_status()
            if status == 'new':
                # Double check and if it is new, submit it
                self.__submit_to_condor(relmon)

        self.ssh_executor.close_connections()
        tick_end = time.time()
        self.logger.info('Controller tick finished. Took %.2fs',
                         tick_end - tick_start)

    def add_to_reset_list(self, relmon_id):
        """
        Add relmon id to list of ids to be reset during next tick
        """
        self.logger.info('Will add %s to reset list', relmon_id)
        if str(relmon_id) not in self.relmons_to_reset:
            self.logger.info('Added %s to reset list', relmon_id)
            self.relmons_to_reset.append(str(relmon_id))

    def add_to_delete_list(self, relmon_id):
        """
        Add relmon id to list of ids to be deleted during next tick
        """
        self.logger.info('Will add %s to delete list', relmon_id)
        if str(relmon_id) not in self.relmons_to_delete:
            self.logger.info('Added %s to delete list', relmon_id)
            self.relmons_to_delete.append(str(relmon_id))

    def create_relmon(self, relmon_data):
        """
        Create relmon from the supplied dictionary
        """
        relmon_data['id'] = str(int(time.time()))
        relmon = RelMon(relmon_data)
        relmon.reset()
        self.db.update_relmon(relmon)
        self.logger.info('Relmon %s was created', relmon)

    def edit_relmon(self, relmon_data):
        """
        TODO: To be documented...
        """
        relmon = RelMon(relmon_data)
        self.db.update_relmon(relmon)
        self.logger.info('Relmon %s was edited', relmon)

    def __submit_to_condor(self, relmon):
        """
        Take relmon object and submit it to HTCondor
        """
        relmon_id = relmon.get_id()
        local_relmon_directory = 'relmons/%s/' % (relmon_id)
        remote_relmon_directory = '%s%s/' % (self.__remote_directory, relmon_id)
        self.logger.info('Will submit %s to HTCondor', relmon)
        self.logger.info('Remote directory of %s is %s', relmon, remote_relmon_directory)
        self.logger.info('Resetting %s before submission', relmon)
        relmon.reset()
        self.logger.info('Saving %s to database', relmon)
        self.db.update_relmon(relmon)
        # Refetch after update
        relmon = RelMon(self.db.get_relmon(relmon_id))
        self.logger.info('Resources for %s: CPU: %s, memory: %s, disk %s',
                         relmon,
                         relmon.get_cpu(),
                         relmon.get_memory(),
                         relmon.get_disk())
        try:
            self.logger.info('Will create files for %s', relmon)
            # Dump the json to a file
            self.file_creator.create_relmon_file(relmon)
            # Create HTCondor submit file
            self.file_creator.create_condor_job_file(relmon)
            # Create actual job script file
            self.file_creator.create_job_script_file(relmon)

            self.logger.info('Will prepare remote directory for %s', relmon)
            # Prepare remote directory. Delete old one and create a new one
            self.ssh_executor.execute_command([
                'rm -rf %s' % (remote_relmon_directory),
                'mkdir -p %s' % (remote_relmon_directory)
            ])

            self.logger.info('Will upload files for %s', relmon)
            # Upload relmon json, submit file and script to run
            self.ssh_executor.upload_file('%s%s.json' % (local_relmon_directory, relmon_id),
                                          '%s%s.json' % (remote_relmon_directory, relmon_id))
            self.ssh_executor.upload_file('%s%s.sub' % (local_relmon_directory, relmon_id),
                                          '%s%s.sub' % (remote_relmon_directory, relmon_id))
            self.ssh_executor.upload_file('%s%s.sh' % (local_relmon_directory, relmon_id),
                                          '%sRELMON_%s.sh' % (remote_relmon_directory, relmon_id))

            self.logger.info('Will try to submit %s', relmon)
            # Run condor_submit
            # Submission happens through lxplus as condor is not available on website machine
            # It is easier to ssh to lxplus than set up condor locally
            stdout, stderr = self.ssh_executor.execute_command([
                'cd %s' % (remote_relmon_directory),
                'condor_submit %s.sub' % (relmon_id)
            ])
            # Parse result of condor_submit
            if not stderr and '1 job(s) submitted to cluster' in stdout:
                # output is "1 job(s) submitted to cluster 801341"
                relmon.set_status('submitted')
                condor_id = int(float(stdout.split()[-1]))
                relmon.set_condor_id(condor_id)
                relmon.set_condor_status('IDLE')
                self.logger.info('Submitted %s. Condor job id %s', relmon, condor_id)
            else:
                self.logger.error('Error submitting %s.\nOutput: %s.\nError %s',
                                  relmon,
                                  stdout,
                                  stderr)
                relmon.set_status('failed')

        except Exception as ex:
            relmon.set_status('failed')
            self.logger.error('Exception while trying to submit %s: %s', relmon, str(ex))

        self.logger.info('%s status is %s', relmon, relmon.get_status())
        self.db.update_relmon(relmon)

    def __check_if_running(self, relmon):
        relmon_condor_id = relmon.get_condor_id()
        self.logger.info('Will check if %s is running in HTCondor, id: %s',
                         relmon,
                         relmon_condor_id)
        stdout, stderr = self.ssh_executor.execute_command(
            'condor_q -af:h ClusterId JobStatus | grep %s' % (relmon_condor_id)
        )
        new_condor_status = '<unknown>'
        if stdout and not stderr:
            status_number = stdout.split()[-1]
            self.logger.info('Relmon %s status is %s', relmon, status_number)
            status_dict = {
                '0': 'UNEXPLAINED',
                '1': 'IDLE',
                '2': 'RUN',
                '3': 'REMOVED',
                '4': 'DONE',
                '5': 'HOLD',
                '6': 'SUBMISSION ERROR'
            }
            new_condor_status = status_dict.get(status_number, 'REMOVED')
        else:
            self.logger.error('Error with HTCondor?\nOutput: %s.\nError %s',
                              stdout,
                              stderr)

        self.logger.info('Saving %s condor status as %s', relmon, new_condor_status)
        relmon.set_condor_status(new_condor_status)
        self.db.update_relmon(relmon)

    def __collect_output(self, relmon):
        condor_status = relmon.get_condor_status()
        if condor_status not in ['DONE', 'REMOVED']:
            self.logger.info('%s status is not DONE or REMOVED, it is %s', relmon, condor_status)
            return

        relmon_id = relmon.get_id()
        remote_relmon_directory = '%s%s/' % (self.__remote_directory, relmon_id)
        local_relmon_directory = 'relmons/%s/' % (relmon_id)

        self.ssh_executor.download_file(
            '%svalidation_matrix.log' % (remote_relmon_directory),
            '%svalidation_matrix.log' % (local_relmon_directory)
        )
        self.ssh_executor.download_file(
            '%s%s.out' % (remote_relmon_directory, relmon_id),
            '%s%s.out' % (local_relmon_directory, relmon_id)
        )
        self.ssh_executor.download_file(
            '%s%s.log' % (remote_relmon_directory, relmon_id),
            '%s%s.log' % (local_relmon_directory, relmon_id)
        )
        self.ssh_executor.download_file(
            '%s%s.err' % (remote_relmon_directory, relmon_id),
            '%s%s.err' % (local_relmon_directory, relmon_id)
        )

        _, _ = self.ssh_executor.execute_command([
            'cd %s' % (remote_relmon_directory),
            'cd ..',
            'rm -r %s' % (relmon_id)
        ])
        if relmon.get_status() != 'failed':
            relmon.set_status('done')

        self.db.update_relmon(relmon)

    def __reset_relmon(self, relmon_id):
        relmon_json = self.db.get_relmon(relmon_id)
        relmon = RelMon(relmon_json)
        self.__terminate_relmon(relmon)
        relmon.reset()
        self.db.update_relmon(relmon)

    def __delete_relmon(self, relmon_id):
        relmon_json = self.db.get_relmon(relmon_id)
        relmon = RelMon(relmon_json)
        self.__terminate_relmon(relmon)
        self.db.delete_relmon(relmon)

    def __terminate_relmon(self, relmon):
        self.logger.info('Trying to terminate %s', relmon)
        condor_id = relmon.get_condor_id()
        if condor_id > 0:
            self.ssh_executor.execute_command('condor_rm %s' % (condor_id))
        else:
            self.logger.info('Relmon %s HTCondor id is not valid: %s', relmon, condor_id)

        self.logger.info('Finished terminating relmon %s', relmon)