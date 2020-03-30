"""
RelMon report production controller
Runs main loop that checks status and acts accordingly
"""

import logging
import time
import os.path
import shutil
import zipfile
from multiprocessing import Manager
from mongodb_database import Database
from local.ssh_executor import SSHExecutor
from local.relmon import RelMon
from local.file_creator import FileCreator
from local.email_sender import EmailSender


class Controller():
    def __init__(self, config):
        self.logger = logging.getLogger('logger')
        self.logger.info('***** Creating a controller! *****')
        self.is_tick_running = False
        self.remote_directory = config['remote_directory']
        if self.remote_directory[-1] == '/':
            self.remote_directory = self.remote_directory[:-1]

        self.ssh_executor = SSHExecutor(config)
        self.file_creator = FileCreator(config)
        self.email_sender = EmailSender(config)
        self.config = config
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
        database = Database()
        self.logger.info('Controller will tick')
        tick_start = time.time()
        # Delete relmons
        self.logger.info('Relmons to delete (%s): %s.',
                         len(self.relmons_to_delete),
                         ','.join([x['id'] for x in self.relmons_to_delete]))
        for relmon_dict in self.relmons_to_delete:
            relmon_id = relmon_dict['id']
            self.__delete_relmon(relmon_id, database, relmon_dict['user_info'])
            self.relmons_to_delete.remove(relmon_dict)

        # Reset relmons
        self.logger.info('Relmons to reset (%s): %s.',
                         len(self.relmons_to_reset),
                         ', '.join([x['id'] for x in self.relmons_to_reset]))
        for relmon_dict in self.relmons_to_reset:
            relmon_id = relmon_dict['id']
            self.__reset_relmon(relmon_id, database, relmon_dict['user_info'])
            self.relmons_to_reset.remove(relmon_dict)

        # Check relmons
        relmons_to_check = database.get_relmons_with_status('submitted')
        relmons_to_check.extend(database.get_relmons_with_status('running'))
        relmons_to_check.extend(database.get_relmons_with_status('finishing'))
        # Add relmons with HTCondor status RUN to be checked
        for relmon_dict in database.get_relmons_with_condor_status('RUN'):
            for added_relmon in relmons_to_check:
                if added_relmon['_id'] == relmon_dict['_id']:
                    break
            else:
                relmons_to_check.append(relmon_dict)

        self.logger.info('Relmons to check (%s): %s.',
                         len(relmons_to_check),
                         ', '.join(r.get('id') for r in relmons_to_check))
        for relmon_json in relmons_to_check:
            relmon = RelMon(relmon_json)
            self.__check_if_running(relmon, database)
            relmon = RelMon(database.get_relmon(relmon.get_id()))
            condor_status = relmon.get_condor_status()
            if condor_status in ('DONE', 'REMOVED'):
                # Refetch after check if running save
                self.__collect_output(relmon, database)

        # Submit relmons
        relmons_to_submit = database.get_relmons_with_status('new')
        self.logger.info('Relmons to submit (%s): %s.',
                         len(relmons_to_submit),
                         ', '.join(r.get('id') for r in relmons_to_submit))
        for relmon_json in relmons_to_submit:
            relmon = RelMon(relmon_json)
            status = relmon.get_status()
            if status == 'new':
                # Double check and if it is new, submit it
                self.__submit_to_condor(relmon, database)

        self.ssh_executor.close_connections()
        tick_end = time.time()
        self.logger.info('Controller tick finished. Took %.2fs',
                         tick_end - tick_start)

    def add_to_reset_list(self, relmon_id, user_info):
        """
        Add relmon id to list of ids to be reset during next tick
        """
        self.logger.info('Will add %s to reset list', relmon_id)
        relmon_id = str(relmon_id)
        for item in self.relmons_to_reset:
            if item['id'] == relmon_id:
                return

        self.relmons_to_reset.append({'id': str(relmon_id),
                                      'user_info': user_info})
        self.logger.info('Added %s to reset list', relmon_id)

    def add_to_delete_list(self, relmon_id, user_info):
        """
        Add relmon id to list of ids to be deleted during next tick
        """
        self.logger.info('Will add %s to delete list', relmon_id)
        relmon_id = str(relmon_id)
        for item in self.relmons_to_delete:
            if item['id'] == relmon_id:
                return

        self.relmons_to_delete.append({'id': str(relmon_id),
                                       'user_info': user_info})
        self.logger.info('Added %s to delete list', relmon_id)

    def create_relmon(self, relmon, database, user_info):
        """
        Create relmon from the supplied dictionary
        """
        relmon.reset()
        relmon.set_user_info(user_info)
        database.create_relmon(relmon)
        self.logger.info('Relmon %s was created', relmon)

    def edit_relmon(self, new_relmon, database, user_info):
        """
        Update relmon categories
        """
        relmon_id = new_relmon.get_id()
        old_relmon_data = database.get_relmon(relmon_id)
        old_relmon = RelMon(old_relmon_data)
        old_cmssw_release = old_relmon.get_cmssw_release()
        new_cmssw_release = new_relmon.get_cmssw_release()
        if old_relmon.get_status() == 'done' and old_cmssw_release == new_cmssw_release:
            self.logger.info('Relmon %s is done, will try to do a smart edit', old_relmon)
            new_category_names = [x['name'] for x in new_relmon.get_json().get('categories')]
            old_category_names = [x['name'] for x in old_relmon.get_json().get('categories')]
            self.logger.info('Relmon %s had these categories: %s', old_relmon, old_category_names)
            self.logger.info('Relmon %s have these categories: %s', new_relmon, new_category_names)
            categories_changed = False
            for category_name in set(new_category_names + old_category_names):
                old_category = old_relmon.get_category(category_name)
                new_category = new_relmon.get_category(category_name)
                old_category_references = [x['name'] for x in old_category.get('reference', [])]
                new_category_references = [x['name'] for x in new_category.get('reference', [])]
                old_category_targets = [x['name'] for x in old_category.get('target', [])]
                new_category_targets = [x['name'] for x in new_category.get('target', [])]
                old_category_pairing = old_category.get('automatic_pairing')
                new_category_pairing = new_category.get('automatic_pairing')
                old_category_hlt = old_category.get('hlt')
                new_category_hlt = new_category.get('hlt')
                changed = False
                changed = changed or old_category_references != new_category_references
                changed = changed or old_category_targets != new_category_targets
                changed = changed or old_category_pairing != new_category_pairing
                changed = changed or old_category_hlt != new_category_hlt
                categories_changed = categories_changed or changed
                if changed:
                    self.logger.info('Category %s of %s changed', category_name, old_relmon)
                    old_category['reference'] = new_category_references
                    old_category['target'] = new_category_targets
                    old_category['automatic_pairing'] = new_category_pairing
                    old_category['hlt'] = new_category_hlt
                    old_relmon.reset_category(category_name)
                else:
                    self.logger.info('Category %s of %s did not change', category_name, old_relmon)

            name_changed = old_relmon_data['name'] != new_relmon.get_name()
            if name_changed and not categories_changed:
                # Only name changed, categories did not change, just a rename
                new_name = new_relmon.get_name()
                self.logger.info('Renaming %s to %s without changing categories' % (old_relmon, new_name))
                old_relmon.get_json()['name'] = new_name
                ssh_executor = SSHExecutor(self.config)
                ssh_executor.execute_command([
                    'cd %s' % (self.file_creator.web_location),
                    'EXISTING_REPORT=$(ls -1 %s*.sqlite | head -n 1)' % (relmon_id),
                    'echo "Existing file name: $EXISTING_REPORT"',
                    'mv "$EXISTING_REPORT" "%s___%s.sqlite"' % (relmon_id, new_name),
                ])
                old_relmon.set_user_info(user_info)
                database.update_relmon(old_relmon)
            elif categories_changed:
                # Categories changed, will have to resubmit
                new_name = new_relmon.get_name()
                old_relmon.get_json()['name'] = new_name
                old_relmon.set_status('new')
                old_relmon.set_condor_id(0)
                old_relmon.set_condor_status('<unknown>')
                old_relmon.set_user_info(user_info)
                database.update_relmon(old_relmon)
            else:
                self.logger.info('Nothing changed for %s?' % (old_relmon))

        else:
            self.logger.info('Relmon %s will be reset', old_relmon)
            old_relmon.get_json()['name'] = new_relmon.get_name()
            old_relmon.get_json()['categories'] = new_relmon.get_json().get('categories', [])
            # Update only name and categories, do not allow to update anything else
            old_relmon.reset()
            database.update_relmon(old_relmon)
            self.add_to_reset_list(relmon_id, user_info)

        self.logger.info('Relmon %s was edited', old_relmon)

    def __submit_to_condor(self, relmon, database):
        """
        Take relmon object and submit it to HTCondor
        """
        relmon_id = relmon.get_id()
        local_relmon_directory = 'relmons/%s' % (relmon_id)
        remote_relmon_directory = '%s/%s' % (self.remote_directory, relmon_id)
        self.logger.info('Will submit %s to HTCondor', relmon)
        self.logger.info('Remote directory of %s is %s', relmon, remote_relmon_directory)
        self.logger.info('Saving %s to database', relmon)
        database.update_relmon(relmon)
        # Refetch after update
        relmon = RelMon(database.get_relmon(relmon_id))
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
            local_name = '%s/RELMON_%s' % (local_relmon_directory, relmon_id)
            remote_name = '%s/RELMON_%s' % (remote_relmon_directory, relmon_id)
            self.ssh_executor.upload_file('%s.json' % (local_name),
                                          '%s.json' % (remote_name))
            self.ssh_executor.upload_file('%s.sub' % (local_name),
                                          '%s.sub' % (remote_name))
            self.ssh_executor.upload_file('%s.sh' % (local_name),
                                          '%s.sh' % (remote_name))

            self.logger.info('Will try to submit %s', relmon)
            # Run condor_submit
            # Submission happens through lxplus as condor is not available on website machine
            # It is easier to ssh to lxplus than set up condor locally
            stdout, stderr = self.ssh_executor.execute_command([
                'cd %s' % (remote_relmon_directory),
                'module load lxbatch/tzero && condor_submit RELMON_%s.sub' % (relmon_id)
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
        database.update_relmon(relmon)

    def __check_if_running(self, relmon, database):
        relmon_condor_id = relmon.get_condor_id()
        self.logger.info('Will check if %s is running in HTCondor, id: %s',
                         relmon,
                         relmon_condor_id)
        stdout, stderr = self.ssh_executor.execute_command(
            'module load lxbatch/tzero && condor_q -af:h ClusterId JobStatus | grep %s' % (relmon_condor_id)
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

        relmon = RelMon(database.get_relmon(relmon.get_id()))
        self.logger.info('Saving %s condor status as %s', relmon, new_condor_status)
        relmon.set_condor_status(new_condor_status)
        database.update_relmon(relmon)

    def __collect_output(self, relmon, database):
        condor_status = relmon.get_condor_status()
        if condor_status not in ['DONE', 'REMOVED']:
            self.logger.info('%s status is not DONE or REMOVED, it is %s', relmon, condor_status)
            return

        logging.info('Collecting output for %s', relmon)
        relmon_id = relmon.get_id()
        remote_relmon_directory = '%s/%s' % (self.remote_directory, relmon_id)
        local_relmon_directory = 'relmons/%s' % (relmon_id)

        self.ssh_executor.download_file(
            '%s/validation_matrix.log' % (remote_relmon_directory),
            '%s/validation_matrix.log' % (local_relmon_directory)
        )
        remote_name = '%s/RELMON_%s' % (remote_relmon_directory, relmon_id)
        local_name = '%s/%s' % (local_relmon_directory, relmon_id)
        self.ssh_executor.download_file(
            '%s.out' % (remote_name),
            '%s.out' % (local_name)
        )
        self.ssh_executor.download_file(
            '%s.log' % (remote_name),
            '%s.log' % (local_name)
        )
        self.ssh_executor.download_file(
            '%s.err' % (remote_name),
            '%s.err' % (local_name)
        )

        downloaded_files = []
        if os.path.isfile('%s.out' % (local_name)):
            downloaded_files.append('%s.out' % (local_name))

        if os.path.isfile('%s.log' % (local_name)):
            downloaded_files.append('%s.log' % (local_name))

        if os.path.isfile('%s.err' % (local_name)):
            downloaded_files.append('%s.err' % (local_name))

        if os.path.isfile('%s/validation_matrix.log' % (local_relmon_directory)):
            downloaded_files.append('%s/validation_matrix.log' % (local_relmon_directory))

        attachments = []
        if downloaded_files:
            archive_name = '%s.zip' % (local_name)
            attachments = [archive_name]
            with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zip_object:
                for file_path in downloaded_files:
                    zip_object.write(file_path, file_path.split('/')[-1])

        if relmon.get_status() != 'failed':
            relmon.set_status('done')
            self.__send_done_notification(relmon, files=attachments)
        else:
            self.__send_failed_notification(relmon, files=attachments)

        database.update_relmon(relmon)
        shutil.rmtree(local_relmon_directory, ignore_errors=True)

    def __reset_relmon(self, relmon_id, database, user_info):
        relmon_json = database.get_relmon(relmon_id)
        relmon = RelMon(relmon_json)
        self.__terminate_relmon(relmon)
        old_username = relmon.get_user_info().get('login')
        new_username = user_info.get('login')
        if old_username != new_username:
            self.logger.info('Reset by %s while not done, should inform %s', new_username, old_username)
            self.__send_reset_notification(relmon, user_info)

        relmon.reset()
        relmon.set_user_info(user_info)
        database.update_relmon(relmon)

    def __delete_relmon(self, relmon_id, database, user_info):
        relmon_json = database.get_relmon(relmon_id)
        relmon = RelMon(relmon_json)
        self.__terminate_relmon(relmon)
        database.delete_relmon(relmon)

    def __terminate_relmon(self, relmon):
        self.logger.info('Trying to terminate %s', relmon)
        condor_id = relmon.get_condor_id()
        if condor_id > 0:
            self.ssh_executor.execute_command('module load lxbatch/tzero && condor_rm %s' % (condor_id))
        else:
            self.logger.info('Relmon %s HTCondor id is not valid: %s', relmon, condor_id)

        self.logger.info('Finished terminating relmon %s', relmon)

    def __send_reset_notification(self, relmon, new_user_info):
        relmon_name = relmon.get_name()
        new_user_fullname = new_user_info.get('fullname', '<anonymous>')
        body = 'Hello,\n\n'
        body += 'RelMon %s was reset by %s.\n' % (relmon_name, new_user_fullname)
        body += 'You will not receive notification when this RelMon finishes running.\n'
        body += 'RelMon in RelMon Service: https://pdmv-relmonsvc.web.cern.ch/relmonsvc?q=%s\n' % (relmon_name)
        subject = 'RelMon %s was reset' % (relmon_name)
        recipients = [relmon.get_user_info()['email']]
        self.email_sender.send(subject, body, recipients)

    def __send_done_notification(self, relmon, files=None):
        relmon_name = relmon.get_name()
        body = 'Hello,\n\n'
        body += 'RelMon %s has finished running.\n' % (relmon_name)
        body += 'Reports can be found here: https://pdmv-new-relmon.web.cern.ch/pdmv-new-relmon/?q=%s\n' % (relmon_name)
        body += 'RelMon in RelMon Service: https://pdmv-relmonsvc.web.cern.ch/relmonsvc?q=%s\n' % (relmon_name)
        if files:
            body += 'You can find job output as an attachment.\n'

        subject = 'RelMon %s is done' % (relmon_name)
        recipients = [relmon.get_user_info()['email']]
        self.email_sender.send(subject, body, recipients, files)

    def __send_failed_notification(self, relmon, files=None):
        relmon_name = relmon.get_name()
        body = 'Hello,\n\n'
        body += 'RelMon %s has failed.\n' % (relmon_name)
        body += 'RelMon in RelMon Service: https://pdmv-relmonsvc.web.cern.ch/relmonsvc?q=%s\n' % (relmon_name)
        if files:
            body += 'You can find job output as an attachment.\n'

        subject = 'RelMon %s failed' % (relmon_name)
        recipients = [relmon.get_user_info()['email']]
        self.email_sender.send(subject, body, recipients, files)