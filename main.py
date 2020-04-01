"""
Module that contains start of the program, tick scheduler and web APIs
"""
import argparse
import logging
import json
import configparser
import os
import time
from datetime import datetime
from flask import Flask, render_template, request, make_response
from flask_restful import Api
from apscheduler.schedulers.background import BackgroundScheduler
from mongodb_database import Database
from local.controller import Controller
from local.relmon import RelMon


app = Flask(__name__,
            static_folder="./frontend/dist/static",
            template_folder="./frontend/dist")
api = Api(app)
scheduler = BackgroundScheduler()
controller = None


@app.route('/')
def index_page():
    """
    Return index.html
    """
    return render_template('index.html')


@app.route('/api/create', methods=['POST'])
def add_relmon():
    """
    API to create a RelMon
    """
    if not is_user_authorized():
        return output_text({'message': 'Unauthorized'}, code=403)

    relmon = json.loads(request.data.decode('utf-8'))
    if not relmon.get('name'):
        return output_text({'message': 'No name'}, code=400)

    relmon['id'] = str(int(time.time()))
    relmon = RelMon(relmon)
    database = Database()
    if database.get_relmons_with_name(relmon.get_name()):
        return output_text({'message': 'RelMon with this name already exists'}, code=422)

    if database.get_relmon(relmon.get_id()):
        return output_text({'message': 'RelMon with this ID already exists'}, code=422)

    controller.create_relmon(relmon, database, user_info_dict())
    controller_tick()
    return output_text({'message': 'OK'})


@app.route('/api/reset', methods=['POST'])
def reset_relmon():
    """
    API to reset a RelMon
    """
    if not is_user_authorized():
        return output_text({'message': 'Unauthorized'}, code=403)

    data = json.loads(request.data.decode('utf-8'))
    if 'id' in data:
        controller.add_to_reset_list(str(int(data['id'])), user_info_dict())
        controller_tick()
        return output_text({'message': 'OK'})

    return output_text({'message': 'No ID'})


@app.route('/api/delete', methods=['DELETE'])
def delete_relmon():
    """
    API to delete a RelMon
    """
    if not is_user_authorized():
        return output_text({'message': 'Unauthorized'}, code=403)

    data = json.loads(request.data.decode('utf-8'))
    if 'id' in data:
        controller.add_to_delete_list(str(int(data['id'])), user_info_dict())
        controller_tick()
        return output_text({'message': 'OK'})

    return output_text({'message': 'No ID'})


@app.route('/api/get_relmons')
def get_relmons():
    """
    API to fetch RelMons from database
    """
    database = Database()
    args = request.args.to_dict()
    if args is None:
        args = {}

    page = int(args.get('page', 0))
    limit = int(args.get('limit', database.PAGE_SIZE))
    query = args.get('q')
    if query:
        query = query.strip()
        if query.lower() in ('new', 'submitted', 'running', 'finishing', 'done', 'failed'):
            query_dict = {'status': query.lower()}
            data, total_rows = database.get_relmons(query_dict=query_dict,
                                                    page=page,
                                                    page_size=limit)
        else:
            query_dict = {'_id': query}
            data, total_rows = database.get_relmons(query_dict=query_dict,
                                                    page=page,
                                                    page_size=limit)
            if total_rows == 0:
                query = '*%s*' % (query)
                # Perform case insensitive search
                query_dict = {'name': {'$regex': query.replace('*', '.*'), '$options': '-i'}}
                data, total_rows = database.get_relmons(query_dict=query_dict,
                                                        page=page,
                                                        page_size=limit)
    else:
        data, total_rows = database.get_relmons(page=page, page_size=limit)

    for relmon in data:
        if 'user_info' in relmon:
            del relmon['user_info']

        relmon['total_relvals'] = 0
        relmon['downloaded_relvals'] = 0
        relmon['compared_relvals'] = 0
        for category in relmon.get('categories'):
            relmon['total_relvals'] += len(category['reference']) + len(category['target'])
            category['reference_status'] = {}
            category['reference_size'] = 0
            for relval in category['reference']:
                category['reference_size'] += relval.get('file_size', 0)
                relmon_status = relval['status']
                if relmon_status not in category['reference_status']:
                    category['reference_status'][relmon_status] = 0

                if relmon_status != 'initial':
                    relmon['downloaded_relvals'] += + 1

                if category['status'] == 'done':
                    relmon['compared_relvals'] += 1

                category['reference_status'][relmon_status] += 1

            category['target_status'] = {}
            category['target_size'] = 0
            for relval in category['target']:
                category['target_size'] += relval.get('file_size', 0)
                relmon_status = relval['status']
                if relmon_status not in category['target_status']:
                    category['target_status'][relmon_status] = 0

                if relmon_status != 'initial':
                    relmon['downloaded_relvals'] = relmon['downloaded_relvals'] + 1

                if category['status'] == 'done':
                    relmon['compared_relvals'] += 1

                category['target_status'][relmon_status] += 1

    return output_text({'data': data, 'total_rows': total_rows, 'page_size': limit})


def output_text(data, code=200, headers=None):
    """
    Makes a Flask response with a plain text encoded body
    """
    resp = make_response(json.dumps(data, indent=1, sort_keys=True), code)
    resp.headers.extend(headers or {})
    resp.headers['Content-Type'] = 'application/json'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/api/edit', methods=['POST'])
def edit_relmon():
    """
    API for RelMon editing
    """
    if not is_user_authorized():
        return output_text({'message': 'Unauthorized'}, code=403)

    relmon = json.loads(request.data.decode('utf-8'))
    relmon = RelMon(relmon)
    database = Database()
    existing_relmons_with_same_name = database.get_relmons_with_name(relmon.get_name())
    for existing_relmon_with_same_name in existing_relmons_with_same_name:
        if existing_relmon_with_same_name['id'] != relmon.get_id():
            return output_text({'message': 'RelMon with this name already exists'}, code=422)

    relmon_id = relmon.get_id()
    existing_relmon = database.get_relmon(relmon_id)
    if not relmon_id or not existing_relmon:
        return output_text({'message': 'RelMon does not exist'}, code=422)

    controller.edit_relmon(relmon, database, user_info_dict())
    controller_tick()
    return output_text({'message': 'OK'})


@app.route('/api/update', methods=['POST'])
def update_info():
    """
    API for jobs in HTCondor to notify about progress
    """
    login = request.headers.get('Adfs-Login', '???')
    logger = logging.getLogger('logger')
    if login not in ('pdmvserv', 'jrumsevi'):
        logger.warning('Not letting through user "%s" to do update', login)
        return output_text({'message': 'Unauthorized'}, code=403)

    data = json.loads(request.data.decode('utf-8'))
    database = Database()
    relmon = database.get_relmon(data['id'])
    if not relmon:
        return output_text({'message', 'Could not find'})

    old_status = relmon.get('status')
    relmon['categories'] = data['categories']
    relmon['status'] = data['status']
    logger.info('Update for %s (%s). Status is %s', relmon['name'], relmon['id'], relmon['status'])
    database.update_relmon(RelMon(relmon))
    if relmon['status'] != old_status:
        for job in scheduler.get_jobs():
            job.modify(next_run_time=datetime.now())

    return output_text({'message': 'OK'})


@app.route('/api/tick')
def controller_tick():
    """
    API to trigger a controller tick
    """
    if not is_user_authorized():
        return output_text({'message': 'Unauthorized'}, code=403)

    for job in scheduler.get_jobs():
        job.modify(next_run_time=datetime.now())

    return output_text({'message': 'OK'})


@app.route('/api/user')
def user_info():
    """
    API for user info
    """
    return output_text(user_info_dict())


def user_info_dict():
    """
    Get user name, login, email and authorized flag from request headers
    """
    fullname = request.headers.get('Adfs-Fullname', '')
    login = request.headers.get('Adfs-Login', '')
    email = request.headers.get('Adfs-Email', '')
    authorized_user = is_user_authorized()
    return {'login': login,
            'authorized_user': authorized_user,
            'fullname': fullname,
            'email': email}


def is_user_authorized():
    """
    Return whether user is a member of administrators e-group
    """
    groups = [x.strip().lower() for x in request.headers.get('Adfs-Group', '???').split(';')]
    return 'cms-ppd-pdmv-val-admin-pdmv' in groups


def tick():
    """
    Trigger controller to perform a tick
    """
    controller.tick()


def setup_console_logging():
    """
    Setup logging to console
    """
    logging.basicConfig(format='[%(asctime)s][%(levelname)s] %(message)s', level=logging.INFO)


def get_config(mode):
    """
    Get config as a dictionary
    Based on the mode - prod, dev or env it can be taken either from file or environment variables
    """
    if mode == 'env':
        keys = ['callback_url',
                'cookie_url',
                'grid_certificate',
                'grid_key',
                'host',
                'port',
                'submission_host',
                'remote_directory',
                'ssh_credentials',
                'web_location']
        config = {}
        for key in keys:
            config[key] = os.environ.get(key.upper())

    else:
        config = configparser.ConfigParser()
        config.read('config.cfg')
        config = dict(config.items(mode))

    logging.info('Config values:')
    for key, value in config.items():
        if key == 'ssh_credentials':
            logging.info('%s ******', key)
        else:
            logging.info('%s %s', key, value)

    return config


def main():
    """
    Main function, parse arguments, create a controller and start Flask web server
    """
    parser = argparse.ArgumentParser(description='RelMon Service')
    parser.add_argument('--mode',
                        choices=['prod', 'dev', 'env'],
                        required=True,
                        help='Production (prod) or development (dev) mode from '
                             'config file or environment variables (env) mode')
    parser.add_argument('--debug',
                        help='Debug mode',
                        action='store_true')
    args = vars(parser.parse_args())
    debug = args.get('debug', False)
    setup_console_logging()
    logger = logging.getLogger('logger')
    mode = args.get('mode', 'dev').lower()
    logger.info('Mode is "%s"', mode)
    config = get_config(mode)
    scheduler.add_executor('processpool')
    if not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        global controller
        controller = Controller(config)
        scheduler.add_job(tick, 'interval', seconds=300, max_instances=1)

    scheduler.start()
    port = int(config.get('port', 8001))
    host = config.get('host', '127.0.0.1')
    logger.info('Will run on %s:%s', host, port)
    app.run(host=host,
            port=port,
            debug=debug,
            threaded=True)
    scheduler.shutdown()


if __name__ == '__main__':
    main()
