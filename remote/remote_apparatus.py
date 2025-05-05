"""
Script takes RelMon config and grid certificates
For RelMons in given config, finds DQMIO datasets, downloads
root files from cmsweb and runs ValidationMatrix from CMSSW
for these root files
During the whole process, it sends callbacks to RelmonService
website about file and whole RelMon status changes
Output is stored in Reports directory
"""
import json
import argparse
import re
import logging
import os
import time
import sys
import traceback
import subprocess
from subprocess import Popen
from difflib import SequenceMatcher

# pylint: disable=import-error
from cmswebwrapper import CMSWebWrapper
from events import get_events

# pylint: enable=import-error


def get_dqmio_dataset(workflow):
    """
    Given a workflow dictionary, return first occurence of DQMIO string
    Return None if it could not be found
    """
    output_datasets = workflow.get("OutputDatasets", [])
    for dataset in output_datasets:
        if "/DQMIO" in dataset:
            return dataset

    return None


def get_root_file_path_for_dataset(cmsweb, dqmio_dataset, category_name):
    """
    Get list of URLs for given dataset
    """
    logging.info(
        "Getting root file path for dataset %s. Category %s",
        dqmio_dataset,
        category_name,
    )
    cmssw = dqmio_dataset.split("/")[2].split("-")[0]
    dataset_part = dqmio_dataset.replace("/", "__")
    if category_name == "Data":
        cmsweb_dqm_dir_link = "/dqm/relval/data/browse/ROOT/RelValData/"
    else:
        cmsweb_dqm_dir_link = "/dqm/relval/data/browse/ROOT/RelVal/"

    cmsweb_dqm_dir_link += "_".join(cmssw.split("_")[:3]) + "_x/"
    response = cmsweb.get(cmsweb_dqm_dir_link)
    hyperlink_regex = re.compile("href=['\"]([-\\._a-zA-Z/\\d]*)['\"]")
    hyperlinks = hyperlink_regex.findall(response)[1:]
    hyperlinks = list(hyperlinks)
    logging.info(
        "Substring to look for: %s. Total links in page: %s. Looking in %s",
        dataset_part,
        len(hyperlinks),
        cmsweb_dqm_dir_link,
    )
    hyperlinks = [x for x in hyperlinks if dataset_part in x]
    hyperlinks = sorted(hyperlinks)
    logging.info(
        "Selected hyperlinks %s", json.dumps(hyperlinks, indent=2, sort_keys=True)
    )
    return hyperlinks


def get_client_credentials():
    """
    This function retrieves the client credentials given
    via environment variables

    Returns:
        dict: Credentials required to request an access token via
            client credential grant

    Raises:
        RuntimeError: If there are environment variables that were not provided
    """
    required_variables = [
        "CALLBACK_CLIENT_ID",
        "CALLBACK_CLIENT_SECRET",
        "APPLICATION_CLIENT_ID",
    ]
    credentials = {}
    msg = (
        "Some required environment variables are not available "
        "to send the callback notification. Please set them:\n"
    )
    for var in required_variables:
        value = os.getenv(var)
        if not value:
            msg += "%s\n" % var
            continue
        credentials[var] = value

    if len(credentials) == len(required_variables):
        logging.info("Returning OAuth2 credentials for requesting a token")
        return credentials

    logging.error(msg)
    raise RuntimeError(msg)


def get_access_token(credentials):
    """
    Request an access token to Keycloak (CERN SSO) via a
    client credential grant.

    Args:
        credentials (dict): Credentials required to perform a client credential grant
            Client ID, Client Secret and Target application (audience)

    Returns:
        str: Authorization header including the captured access token

    Raises:
        RuntimeError: If there is an issue requesting the access token
    """
    cern_api_access_token = "https://auth.cern.ch/auth/realms/cern/api-access/token"
    client_id = credentials["CALLBACK_CLIENT_ID"]
    client_secret = credentials["CALLBACK_CLIENT_SECRET"]
    audience = credentials["APPLICATION_CLIENT_ID"]
    command = [
        "curl",
        "-s",
        "--location",
        "--request",
        "POST",
        cern_api_access_token,
        "--header",
        "'Content-Type: application/x-www-form-urlencoded'",
        "--data-urlencode 'grant_type=client_credentials'",
        "--data-urlencode 'client_id=%s'" % client_id,
        "--data-urlencode 'client_secret=%s'" % client_secret,
        "--data-urlencode 'audience=%s'" % audience,
    ]
    command = " ".join(command)
    logging.info("Requesting access token...")
    proc = Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    stdout = proc.communicate()[0]
    stdout = stdout.decode("utf-8")
    if proc.returncode != 0:
        request_error = "Error requesting an access token: %s" % stdout
        logging.error(request_error)
        raise RuntimeError(request_error)

    token_content = json.loads(stdout)
    token = token_content.get("access_token")
    if not token:
        token_error = "Invalid access token request. Details: %s" % token_content
        logging.error(token_error)
        raise RuntimeError(token_error)

    header = "Bearer %s" % token
    return header


def notify(relmon, callback_url, callback_credentials):
    """
    Send a notification about progress back to RelMon service
    """

    with open("notify_data.json", "w") as json_file:
        json.dump(relmon, json_file, indent=2, sort_keys=True)

    command = [
        "curl",
        "-X",
        "POST",
        callback_url,
        "-s",
        "-k",
        "-L",
        "-m",
        "60",
        "-d",
        "@notify_data.json",
        "-H",
        "'Content-Type: application/json'",
    ]
    if callback_credentials:
        credentials = get_client_credentials()
        access_token = get_access_token(credentials)
        command += [
            "-H",
            "'Authorization: %s'" % access_token,
        ]

    command = " ".join(command)
    logging.info("Notifying...")
    proc = Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    stdout = proc.communicate()[0]
    stdout = stdout.decode("utf-8")
    logging.info("Notification result: %s", stdout)

    os.remove("notify_data.json")
    time.sleep(0.05)


def download_root_files(relmon, cmsweb, callback_url, callback_credentials):
    """
    Download all files needed for comparison and fill relmon dictionary
    """
    for category in relmon.get("categories", []):
        if category["status"] != "initial":
            continue

        category_name = category["name"]
        reference_list = category.get("reference", [])
        target_list = category.get("target", [])
        for item in reference_list + target_list:
            name = item["name"]
            if name.lower().startswith("/relval") and name.lower().endswith("/dqmio"):
                logging.info("Name %s is dataset name", name)
                # Dataset name
                dqmio_dataset = name
            else:
                logging.info("Name %s is workflow name", name)
                # Workflow name
                workflow = cmsweb.get_workflow(item["name"])
                if not workflow:
                    item["status"] = "no_workflow"
                    notify(relmon, callback_url, callback_credentials)
                    logging.warning(
                        "Could not find workflow %s in ReqMgr2", item["name"]
                    )
                    continue

                dqmio_dataset = get_dqmio_dataset(workflow)
                if not dqmio_dataset:
                    item["status"] = "no_dqmio"
                    notify(relmon, callback_url, callback_credentials)
                    logging.warning(
                        "Could not find DQMIO dataset in %s. Datasets: %s",
                        item["name"],
                        ", ".join(workflow.get("OutputDatasets", [])),
                    )
                    continue

            file_urls = get_root_file_path_for_dataset(
                cmsweb, dqmio_dataset, category_name
            )
            if not file_urls:
                item["status"] = "no_root"
                notify(relmon, callback_url, callback_credentials)
                logging.warning(
                    "Could not get root file path for %s dataset of %s workflow",
                    dqmio_dataset,
                    item["name"],
                )
                continue

            item["versioned"] = len(file_urls) > 1
            file_url = file_urls[-1]

            logging.info("File URL for %s is %s", item["name"], file_url)
            item["file_url"] = file_url
            item["file_size"] = 0
            item["status"] = "downloading"
            item["file_name"] = item["file_url"].split("/")[-1]
            item["events"] = 0
            notify(relmon, callback_url, callback_credentials)
            try:
                item["file_name"] = cmsweb.get_big_file(item["file_url"])
                item["status"] = "downloaded"
                item["file_size"] = os.path.getsize(item["file_name"])
                item["events"] = get_events(item["file_name"])
                logging.info(
                    "Downloaded %s. Size %.2f MB. Events %s",
                    item["file_name"],
                    item.get("file_size", 0) / 1024.0 / 1024.0,
                    item["events"],
                )
            except Exception as ex:
                logging.error(ex)
                logging.error("Error getting %s for %s", item["file_url"], item["name"])
                item["status"] = "failed"

            notify(relmon, callback_url, callback_credentials)


def get_local_subreport_path(category_name, hlt):
    """
    Return name of local folder
    Basically add Report and HLT to category name
    """
    name = category_name
    if "PU" in category_name:
        name = name.split("_")[0] + "Report_PU"
    else:
        name += "Report"

    if hlt:
        name += "_HLT"

    return name


def get_important_part(file_name):
    """
    Return part of dataset file name that will be used for matching
    """
    return file_name.split("__")[1] + "_" + file_name.split("__")[2].split("-")[1]


def make_file_tree(items, category):
    """
    Make "tree" for files based on dataset (part after first __) and run number
    """
    result_tree = {}
    for item in items:
        filename = item["file_name"]
        split_filename = filename.split("__")
        if len(split_filename) < 2:
            logging.error('Bad file name: "%s"', filename)
            continue

        dataset = split_filename[1].split("_")[0]
        if category == "Data":
            run_number = split_filename[0].split("_")[-1]
        else:
            run_number = "all_runs"

        if dataset not in result_tree:
            result_tree[dataset] = {}

        if run_number not in result_tree[dataset]:
            result_tree[dataset][run_number] = []

        result_tree[dataset][run_number].append(item)

    return result_tree


def clean_file_tree(tree):
    """
    Remove empty lists and dictionaries from file "tree"
    """
    for key in list(tree.keys()):
        if isinstance(tree[key], dict):
            clean_file_tree(tree[key])
            if not tree[key]:
                del tree[key]
        elif isinstance(tree[key], list):
            if not tree[key]:
                del tree[key]


def calculate_similarities(references, targets):
    """
    Calculate similarities for all possible pairs of references and targets
    """
    all_ratios = []
    for reference in references:
        for target in targets:
            reference_string = get_important_part(reference["file_name"])
            target_string = get_important_part(target["file_name"])
            ratio = SequenceMatcher(a=reference_string, b=target_string).ratio()
            reference_target_ratio = (reference, target, ratio)
            all_ratios.append(reference_target_ratio)
            logging.info("%s %s -> %s", reference_string, target_string, ratio)

    all_ratios.sort(key=lambda x: x[2], reverse=True)
    return all_ratios


def pick_pairs(all_ratios):
    """
    Pick pairs with highest similarity
    """
    used_references = set()
    used_targets = set()
    selected_pairs = []
    for reference_target_ratio in all_ratios:
        reference = reference_target_ratio[0]
        target = reference_target_ratio[1]
        reference_name = reference["file_name"]
        target_name = target["file_name"]
        ratio = reference_target_ratio[2]
        if reference_name not in used_references and target_name not in used_targets:
            logging.info(
                "Pair %s with %s. Similarity %.3f", reference_name, target_name, ratio
            )
            used_references.add(reference_name)
            used_targets.add(target_name)
            selected_pairs.append((reference, target))

    return selected_pairs


def pair_references_with_targets(category):
    """
    Do automatic pairing based on dataset names, runs and similarities in names
    """
    logging.info("Will try to automatically find pairs in %s", category["name"])
    references = category.get("reference", [])
    targets = category.get("target", [])
    reference_tree = make_file_tree(references, category["name"])
    target_tree = make_file_tree(targets, category["name"])

    logging.info(
        "References tree: %s", json.dumps(reference_tree, indent=2, sort_keys=True)
    )
    logging.info("Targets tree: %s", json.dumps(target_tree, indent=2, sort_keys=True))

    selected_pairs = []

    for reference_dataset, reference_runs in reference_tree.items():
        for reference_run, references_in_run in reference_runs.items():
            targets_in_run = target_tree.get(reference_dataset, {}).get(
                reference_run, []
            )
            if len(references_in_run) == 1 and len(targets_in_run) == 1:
                reference = references_in_run.pop()
                target = targets_in_run.pop()
                reference_name = reference["file_name"]
                target_name = target["file_name"]
                logging.info("Pair %s with %s", reference_name, target_name)
                reference["match"] = target["name"]
                target["match"] = reference["name"]
                selected_pairs.append((reference_name, target_name))
            else:
                logging.info(
                    "Dataset %s. Run %s. Will try to match %s\nwith\n%s",
                    reference_dataset,
                    reference_run,
                    json.dumps(references_in_run, indent=2, sort_keys=True),
                    json.dumps(targets_in_run, indent=2, sort_keys=True),
                )

                all_ratios = calculate_similarities(references_in_run, targets_in_run)
                pairs = pick_pairs(all_ratios)
                for reference, target in pairs:
                    references_in_run.remove(reference)
                    targets_in_run.remove(target)
                    selected_pairs.append((reference["file_name"], target["file_name"]))
                    reference["match"] = target["name"]
                    target["match"] = reference["name"]

    # Delete empty items wo there would be less to print
    for tree in (reference_tree, target_tree):
        clean_file_tree(tree)
        for _, runs in tree.items():
            for _, items_in_run in runs.items():
                for item in items_in_run:
                    if item["status"] == "downloaded":
                        item["status"] = "no_match"

    logging.info(
        "References leftovers tree: %s",
        json.dumps(reference_tree, indent=2, sort_keys=True),
    )
    logging.info(
        "Targets leftovers tree: %s", json.dumps(target_tree, indent=2, sort_keys=True)
    )

    sorted_references = [x[0] for x in selected_pairs]
    sorted_targets = [x[1] for x in selected_pairs]

    return sorted_references, sorted_targets


def get_dataset_lists(category):
    """
    Return lists of files to compare
    Automatically paired if automatic pairing is enabled
    """
    reference_list = category.get("reference", {})
    target_list = category.get("target", {})
    reference_dataset_list = []
    target_dataset_list = []
    automatic_pairing = category["automatic_pairing"]

    if not reference_list and not target_list:
        return [], []

    if automatic_pairing:
        reference_dataset_list, target_dataset_list = pair_references_with_targets(
            category
        )
    else:
        for i in range(min(len(reference_list), len(target_list))):
            if reference_list[i]["file_name"] and target_list[i]["file_name"]:
                reference_dataset_list.append(reference_list[i]["file_name"])
                target_dataset_list.append(target_list[i]["file_name"])
                reference_list[i]["match"] = target_list[i]["name"]
                target_list[i]["match"] = reference_list[i]["name"]

            if not reference_list[i]["file_name"]:
                logging.error(
                    "File name is missing for %s, will not compare this workflow",
                    reference_list[i]["name"],
                )

            if not target_list[i]["file_name"]:
                logging.error(
                    "File name is missing for %s, will not compare this workflow",
                    target_list[i]["name"],
                )

    return reference_dataset_list, target_dataset_list


def compare_compress_move(
    category_name, hlt, reference_list, target_list, cpus, log_file
):
    """
    The main function that compares, compresses and moves reports to Reports directory
    """
    subreport_path = get_local_subreport_path(category_name, hlt)
    comparison_command = " ".join(
        [
            "ValidationMatrix.py",
            "-R",
            ",".join(reference_list),
            "-T",
            ",".join(target_list),
            "-o",
            subreport_path,
            "-N %s" % (cpus),
            "--hash_name",
            "--HLT" if hlt else "",
        ]
    )

    # Remove all /cms-service-reldqm/style/blueprint/ from HTML files
    path_fix_command = (
        "find %s/ -type f -name '*.html' |xargs -L1 "
        "sed -i -e 's#/cms-service-reldqm/style/blueprint/##g'" % (subreport_path)
    )
    img_src_fix_command = (
        "find %s/ -type f -name '*.html' |xargs -L1 "
        "sed -i -e 's#http://cmsweb.cern.ch//dqm#https://cmsweb.cern.ch/dqm#g'"
        % (subreport_path)
    )
    compression_command = " ".join(["dir2webdir.py", subreport_path])
    move_command = " ".join(["mv", subreport_path, "Reports/"])

    logging.info("ValidationMatrix command: %s", comparison_command)
    proc = Popen(comparison_command, stdout=log_file, stderr=log_file, shell=True)
    proc.communicate()

    logging.info("Path fix command: %s", path_fix_command)
    proc = Popen(path_fix_command, stdout=log_file, stderr=log_file, shell=True)
    proc.communicate()

    logging.info("<img> src fix command: %s", img_src_fix_command)
    proc = Popen(img_src_fix_command, stdout=log_file, stderr=log_file, shell=True)
    proc.communicate()

    logging.info("Compression command: %s", compression_command)
    proc = Popen(compression_command, stdout=log_file, stderr=log_file, shell=True)
    proc.communicate()

    logging.info("Move command: %s", move_command)
    proc = Popen(move_command, stdout=log_file, stderr=log_file, shell=True)
    proc.communicate()


def run_validation_matrix(relmon, cpus, callback_url, callback_credentials):
    """
    Iterate through categories and start comparison process
    """
    with open("validation_matrix.log", "w") as log_file:
        for category in relmon.get("categories", []):
            if category["status"] != "initial":
                continue

            category_name = category["name"]
            subreport_path_no_hlt = get_local_subreport_path(category_name, False)
            logging.info("Creating directory %s", subreport_path_no_hlt)
            os.makedirs("Reports/" + subreport_path_no_hlt)
            if category_name.lower() != "generator":
                subreport_path_hlt = get_local_subreport_path(category_name, True)
                logging.info("Creating directory %s", subreport_path_hlt)
                os.makedirs("Reports/" + subreport_path_hlt)

            hlt = category["hlt"]
            logging.info("Category: %s", category_name)
            logging.info("HLT: %s", hlt)
            reference_list, target_list = get_dataset_lists(category)
            if reference_list and target_list:
                category["status"] = "comparing"
                notify(relmon, callback_url, callback_credentials)
                # Run Generator without HLT
                # Do not run Generator with HLT
                if hlt in ("only", "both") and category_name.lower() != "generator":
                    # Run with HLT
                    # Do not run generator with HLT
                    compare_compress_move(
                        category_name, True, reference_list, target_list, cpus, log_file
                    )

                if hlt in ("no", "both") or category_name.lower() == "generator":
                    # Run without HLT
                    # Run Generator without HLT
                    compare_compress_move(
                        category_name,
                        False,
                        reference_list,
                        target_list,
                        cpus,
                        log_file,
                    )

            category["status"] = "done"
            notify(relmon, callback_url, callback_credentials)


def main():
    """
    Main function
    """
    parser = argparse.ArgumentParser(
        description="File downloader and ValidationMatrix runner"
    )
    parser.add_argument("--relmon", "-r", type=str, help="JSON file with RelMon")
    parser.add_argument("--cert", "-c", type=str, help="File name for GRID certificate")
    parser.add_argument("--key", "-k", type=str, help="File name for GRID key")
    parser.add_argument("--proxy", "-p", type=str, help="File name for GRID proxy file")
    parser.add_argument(
        "--cpus",
        nargs="?",
        const=1,
        type=int,
        default=1,
        help="Number of CPU cores for ValidationMatrix",
    )
    parser.add_argument("--callback", type=str, help="URL for callbacks")
    parser.add_argument(
        "--notifydone", action="store_true", help="Just notify that job is completed"
    )
    parser.add_argument(
        "--callback-credentials",
        action="store_true",
        help="Request and send OAuth tokens to authenticate the callback"
    )

    args = vars(parser.parse_args())
    logging.basicConfig(
        stream=sys.stdout,
        format="[%(asctime)s][%(levelname)s] %(message)s",
        level=logging.INFO,
    )

    cert_file = args.get("cert")
    key_file = args.get("key")
    proxy_file = args.get("proxy")
    relmon_filename = args.get("relmon")
    cpus = args.get("cpus", 1)
    callback_url = args.get("callback")
    notify_done = bool(args.get("notifydone"))
    callback_credentials = bool(args.get("callback_credentials"))
    logging.info(
        "Arguments: %s; cert %s; key %s; proxy: %s; cpus %s; callback %s; notify %s",
        relmon_filename,
        cert_file,
        key_file,
        proxy_file,
        cpus,
        callback_url,
        "YES" if notify_done else "NO",
    )

    with open(relmon_filename) as relmon_file:
        relmon = json.load(relmon_file)

    try:
        if notify_done:
            if relmon["status"] != "failed":
                relmon["status"] = "done"
            else:
                logging.info("Will notify about failure")
        else:
            if (not cert_file or not key_file) and proxy_file:
                cert_file = proxy_file
                key_file = proxy_file

            cmsweb = CMSWebWrapper(cert_file, key_file)
            relmon["status"] = "running"
            notify(relmon, callback_url, callback_credentials)
            download_root_files(relmon, cmsweb, callback_url, callback_credentials)
            run_validation_matrix(relmon, cpus, callback_url, callback_credentials)
            relmon["status"] = "finishing"
    except Exception as ex:
        logging.error(ex)
        logging.error(traceback.format_exc())
        relmon["status"] = "failed"
    finally:
        with open(relmon_filename, "w") as relmon_file:
            json.dump(relmon, relmon_file, indent=2, sort_keys=True)

    notify(relmon, callback_url, callback_credentials)


if __name__ == "__main__":
    main()
