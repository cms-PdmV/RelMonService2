> [!IMPORTANT]  
> This repository has been migrated to the PPD Technical Support team inside the CERN GitLab instance: [RelMonService2](https://gitlab.cern.ch/cms-ppd/technical-support/web-services/RelMonService2). Please open and follow issues directly there, do not open or follow them here!

# RelMonService2

## Introduction

RelMonService2 is a web based tool that helps users generate release monitoring (RelMon) reports. It takes user given workflow names (ReqMgr2 request names) as input, downloads DQMIO datasets, feeds them to `ValidationMatrix.py` script of CMSSW and moves generated reports to reports website. This is a second version of RelMon Service. This version of RelMon Service uses CERN HTCondor to run `ValidationMatrix.py` jobs.

## RelMon

One RelMon is one comparison job of datasets. Each RelMon can have up to 7 categories with multiple datasets in each category. RelMon name should reflect what is being compared as this name will be used in reports page, for example, `CMSSW_11_1_0_pre2vsCMSSW_11_1_0_pre1`.

Each RelMon has these attributes. Some are editable by user, but most reflect it's status:
  * **ID** - unique identifier, timestamp of RelMon creation
  * **Name** - RelMon name, used in reports page too. Must be unique
  * **Status** - RelMon status:
    * **new** - RelMon is new and will soon be submitted to HTCondor batch system
    * **submitted** - RelMon was successfully submitted to HTCondor batch system and is waiting for resources (CPU, memory and disk space) to start running. Time in this status depends on RelMon size and load of HTCondor system
    * **running** - RelMon got resources in HTCondor and now is downloading files or running the `ValidationMatrix.py`. Time in this status depends on RelMon size
    * **finishing** - RelMon finished running all `ValidationMatrix.py` commands and now is packing and transferring reports to reports website
    * **done** - RelMon is done, reports are available
    * **failed** - RelMon submission or job at HTCondor failed. Carefully inspect workflow names, check email for logs, reset the RelMon or contact an administrator for more help
  * **HTCondor job status** - Status of HTCondor job. Can be seen in tooltip while hovering on RelMon status. Usually it is one of these:
    * **IDLE** - job is waiting for resources
    * **RUN** - job is running
    * **DONE** - job is done
    * **<unknown>** - RelMon Service could not retrieve status of HTCondor job. This happens when HTCondor scheduler (manager) is not accessible. This is temporary and does not have influence on job. If job was running before, it will continue running, if it was IDLEing, it will continue doing that until resources are available
  * **HTCondor job ID** - job identifier in HTCondor. Can be seen in tooltip while hovering on RelMon status. This is used mostly for debug purposes
  * **Last update** - when was the last time this RelMon received updates about itself like Status, HTCondor job status or Progress
  * **Download progress** - how many DQMIO dataset files are downloaded
  * **Comparison progress** - rough estimate of `ValidationMatrix.py` progress based on number of references and targets in each category

#### Categories
Categories are a convenient way to group comparisons in RelMon and reports pages. Each category has a list of references and targets. Categories in RelMon are the following:
 * Data
 * FullSim
 * FastSim
 * Generator
 * FullSim PU
 * FastSim PU

There is a difference where datasets are downloaded from for different categories:
 * Datasets of Data category are downloaded from https://cmsweb.cern.ch/dqm/relval/data/browse/ROOT/RelValData/
 * Datasets of other categories are downloaded from https://cmsweb.cern.ch/dqm/relval/data/browse/ROOT/RelVal/

Another difference among categories is HLT option: all categories, except Generator can run HLT comparison. Generator has only "No HLT" option. 

Each category has it's own status, pairing mode and HLT option:
  * **Category status** - current status of this category. Can be one of these:
    * **initial** - category is waiting to be compared
    * **comparing** - category is being compared at the moment using `ValidationMatrix.py`
    * **done** - category is done being compared
  * **Pairing** - `auto` (automatic) or `manual`
  * **HLT** - only HLT, no HLT or Both (HLT and no HLT)

#### References and targets
Items in references and targets lists are workflow names from ReqMgr2, e.g. `pdmvserv_RVCMSSW_11_0_0_..._190915_164000_1993` or DQMIO dataset names, e.g. `/RelValTTbar_14TeV/CMSSW_11_3_0_pre6-...-v1/DQMIO`. Number of items must be equal in references and targets lists of the same category. If there are no references and targets in a category, it will be ignored. For each category, each item in reference list is compared with one item in target list. Which one is compared with which depends on pairing mode.

Each reference and target has it's own status:
  * **initial** - workflow is waiting to have it's DQMIO dataset downloaded
  * **downloading** - DQMIO dataset of this workflow is being currently downloaded
  * **downloaded** - DQMIO dataset of this workflow was successfully downloaded
  * **failed** - .root file exists, but error occurred while downloading the file
  * **no_workflow** - could not find workflow with given name in ReqMgr2
  * **no_dqmio** - workflow was found, but does not have DQMIO dataset among output datasets
  * **no_root** - workflow was found and has DQMIO dataset, but no corresponding .root file could be found in [https://cmsweb.cern.ch/dqm/relval/data/browse/ROOT/](https://cmsweb.cern.ch/dqm/relval/data/browse/ROOT/)
  * **no_match** - DQMIO dataset could not be matched (paired) to another DQMIO dataset in references or targets

#### Pairing
Items in references and targets lists can be paired either automatically or manually. Manual pairing compares first item in references list to first item in target list, second item to second item, etc. In this case it is up to a user to put them in correct order. In automatic pairing dataset names will be used to automatically make pairs based on run number (Data category only), dataset name and processing string. Datasets with identical run numbers and datasets and most similar processing strings will be paired.

#### HLT
There are three options for HLT: No HLT, Only HLT and Both. This option controls `--HLT` flag of `ValidationMatrix.py`. "No HLT" will run `ValidationMatrix.py` only once for that category without `--HLT` flag. "Only HLT" will run only once for that category with the flag. "Both" will run `ValidationMatrix.py` twice for that category - once with `--HLT` flag and then without it.

#### Force re-run
If RelMon is done, each category will have an option option to "Force re-run" the category without changing anything in it. This allows to retry comparison of that cateogry without changing anything

#### Resource requirements in HTCondor
Resource requirements in HTCondor job are based on RelMon size. If total number of references and targets of all categories are:
 * **≤ 10 (up to 5 vs 5)** - 1 core, 2GB memory
 * **≤ 30 (up to 15 vs 15)** - 2 cores, 4GB memory
 * **≤ 90 (up to 45 vs 45)** - 4 cores, 8GB memory
 * **≤ 180 (up to 90 vs 90)** - 8 cores, 16GB memory
 * **> 180 (more than 90 vs 90)** - 16 cores, 32GB memory

`ValidationMatrix.py` `-N` argument will be equal to number of cores in list above, so it would utilize all available cores in parallel.

Disk space requirement is 300MB for each reference and target, so if there are 5 references and 5 targets, disk requirement is (5 + 5) * 300MB = 3000MB.

## How RelMon Service works
It is beneficial to know how RelMon service works internally to understand why it behaves like so in certain situations. RelMon service works based on "ticks". Each tick performs these steps:
  1. Check if there are RelMons in "to be deleted" list. If there are, delete them
  2. Check if there are RelMons in "to be reset" list. If there are, reset them to status "new"
  3. Check if there are any RelMons currently submitted to HTCondor (status "submitted", "running", "finishing"). If there are, check job status by running `condor_q`. If HTCondor status changed to done, download job logs and notify user about successful completion
  4. Check if there are RelMons with status "new". This includes RelMons that were reset in step 2. If there are, submit them to HTCondor

These ticks are automatically performed every 10 minutes. Tick is also triggered by creation of new RelMon, deletion, reset and edit actions, so user would not have to wait for 10 minutes to see the changes. It can also be triggered by clicking "Force Refresh" button. One iteration might take a couple of minutes if there are a few RelMons that are submitted or need to be submitted. Note that if one RelMon was reset and triggered a tick and other RelMon was reset while tick of the first RelMon was still ongoing, second RelMon will not be reset immediately and will have to wait for next tick.

## Creating RelMon
New RelMon can be created by clicking Create New RelMon at the top of the page.

User must specify a name and fill one or more categories with references and targets. User can switch between categories by clicking on tabs below RelMon name fields. Each category has it's own references, targets fields as well as pairing and HLT options. References and targets must be specified one per line. Empty lines are ignored.

## Editing RelMon
It is possible to edit a RelMon while it is still running or when it is done. If RelMon is edited while it is not yet done, it will be reset and redone from scratch. If RelMon is edited after being done, only changes will be applied, that is:
 * If RelMon is not "done" and is edited, it will be canceled, reset and redone from scratch
 * If RelMon is "done" and is only renamed in edit, `ValidationMatrix.py` will not be run, only RelMon in RelMon service and reports page will be renamed immediately
 * If RelMon is "done" and references, targets, pairing and/or HLT is changed in a category, only that category will be redone, other categories will be untouched
 * If RelMon is "done" and workflows are added to an empty category, only that category will be done and added to RelMon report in reports page
 * If RelMon is "done" and all workflows are removed from a category, that category will be removed from RelMon report in reports page
 * If RelMon is "done" and "Force re-run" of category is selected, only that category will be redone, other categories will be untouched

RelMon can be edited by clicking Edit button at the bottom of RelMon.

## Resetting RelMon
If RelMon is reset, all of it will be redone from scratch.

RelMon can be reset by clicking Reset button at the bottom of RelMon.

## Deleting RelMon
If RelMon is deleted in RelMon service, reports will not be removed from reports page.

RelMon can be deleted by clicking Delete button at the bottom of RelMon.

## Search
User can search for RelMons by using a search field at the top of the page. User can specify either RelMon ID, full or part of RelMon name, RelMon status. Search is case insensitive.

## Users
There are two types of users in RelMon service: simple users and authorized users. Authorized users have a star next to their name at the top of the page. Only authorized users can created, edit, reset and delete RelMons as well as Trigger a Status Refresh (trigger a Tick). Simple users can view RelMons, open detailed view and use search.
