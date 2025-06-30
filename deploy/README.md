# Deploy a development version

> [!IMPORTANT]
> There are several prerequisites you must fulfill before deploying a development version of this tool:

- Use a development runtime environment reachable inside the CERN general purpose network as the HTCondor jobs need to be able to send callback signals.
- Have a CERN account with access to the [lxplus](https://lxplusdoc.web.cern.ch/) service or to a VM node located inside the CERN general purpose network.
- Have an X.509 certificate to authenticate to the CMS Web Services configured in your CERN account. Please follow these guidelines to request one if required [Personal certificates from CERN](https://twiki.cern.ch/twiki/bin/view/CMSPublic/PersonalCertificate) - [Basic requirements for using the Grid](https://twiki.cern.ch/twiki/bin/view/CMSPublic/WorkBookStartingGrid#BasicGrid).
- Have `docker` and `docker compose` available in your development environment. If you do not have it already, you could install by following the guidelines at: [Install Docker Engine](https://docs.docker.com/engine/install/).
- Have `python3.11` installed for your development environment. If you do not have it already, you could install it via [pyenv](https://github.com/pyenv/pyenv).
- Have `node` installed for your development environment. It is recommended to use the latest LTS version, nevertheless any version `node > 16` should work. If you do not have it already, you could install it via [nvm](https://github.com/nvm-sh/nvm).
- Have a copy of this repository, fork it.

After you fulfill these prerequisites, follow the next steps:

1. Clone the forked repository you created before
2. Edit the file `deploy/env.sh` and complete the `TODO` items available there.
3. Source the environment variables via `source deploy/env.sh`.
4. Edit the file `deploy/nginx/conf.d/proxy.conf` and complete the `TODO` items available there.
5. Deploy the application's components via `docker compose -f deploy/compose.yml up -d`.

At this stage, you have deployed the database and a reverse proxy to forward and authenticate the requests. Next, let's deploy the RelMonService2 application.

6. Create a virtual environment, activate the environment and install the required dependencies: `python3.11 -m venv venv && source ./venv/bin/activate && pip install -r requirements.txt`
7. Install `node` dependencies: `cd frontend/ && npm i && cd ..`

To conclude, deploy the RelMon Report page. This web server will be used to render the generated reports available via SQLite files. To ease this step, deploy an Apache server via the [CERN Web Services](https://webservices-portal.web.cern.ch/) portal using WebEOS site.

8. Set the category of this site as `Test`.
9. Create a folder inside the `/eos` personal filesystem for the `SERVICE_ACCOUNT_USERNAME` account. This will be the path you will set in the `WEB_LOCATION_PATH` variable.
10. Complete the required steps to share the folder with the web server - [Details](https://cernbox.docs.cern.ch/advanced/web-pages/personal_website_content/).
11. Enable `.htaccess` files for the web server.
12. Copy all the content available in the folder `report_website/` to `${WEB_LOCATION_PATH}/`. Do not forget to copy the `.htaccess` file too.

With this steps, the web application should have been deployed successfully and you're ready to continue with your development tasks!

13. Start the development application via: `./relmonsvc.sh dev`. Press `Ctrl+C` to stop the services.
