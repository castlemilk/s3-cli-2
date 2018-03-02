
## S3 CLI
Basic CLI client for interfacing with the s3 RESTFul API. 
Enabling modularised functionality and handling the required token and session management. 

Set up your config file as shown below. This config.yml file should be in the same root
as where the cli.py file is.
### config.yml
```yaml
auth:
  username: smithy
  password: chips
  token_url: https://my/special/and/secure/endpoint/token
  client:
    id: my-yummy-id-you-might-know
    secret: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxx
API:
  url: https://api-endpoint.com/api/

save:
  directory: /tmp/
  retention_time: 1h

logging:
  debug: false
  enabled: false
  level: exception
  file: /var/log/wifi-docs.log

```

## Getting started
### requirements
* python2.7
* [virtualenv]([https://virtualenv.pypa.io/en/stable/)
* requests
* pyYAML
* tqdm (optional)
* python-crontab (optional)


### Install

```
git clone https://github.com/castlemilk/s3-cli.git
cd s3-cli
virtualenv -p `which python2.7` ./cli
source cli/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
$ python wd.py -h            
usage: wd.py [options]

tool for managing interaction with s3 API

optional arguments:
  -h, --help            show this help message and exit
  -lr, --list-reports   list reports for a specified period
  -dl, --download-latest
                        download latest reports from 1 day ago
  -dr, --download-reports
                        Download reports from a specific time window using -e
                        and -s
  -i INTERVAL, --interval INTERVAL
                        interval to poll for new reports [e.g. daily, hourly,
                        10m, 24h, 18h, 6h etc] (default: daily)
  -d, --daemon          enter self-contained daemon mode running in a run-loop
                        with given interval (default: False)
  -sd, --systemd        install systemd configuration to manage the automated
                        fetching of wifi-doctor summary reports (default:
                        False)
  -ct, --crontab        add a crontab entery that runs the download command
                        with the OS managing the interval via crontabs
                        intervals (default: False)
  -c CONFIG, --config CONFIG
                        specify a config file path to use for the cli/daemon
                        (default: ${PWD}/config.yml)
  --detailed            Run command with detailed mode enabled, will present
                        additional information potentially making additional
                        network fetches (default: False)

specify time period:
  -s START, --start START
                        start period to search from [format: ISO 8601 (e.g.
                        2017-11-20T09:32:18Z)] (default: 2017-11-24T09:41:55Z)
  -e END, --end END     end period to search upto [format: ISO 8601 (e.g.
                        2017-11-20T09:32:18Z)] (default: 2017-11-25T09:41:55Z)

```
### Download latest reports
This will download the latest reports between now and a day ago. The client will ensure no
duplicated downloads are made via a localised indexing that is cross-checking already 
stored/download files as well as a historical record if previously downloaded files are
deleted.
```
$ python wifid.py -dl
```
### List reports with detailed information like download size
```bash
$ python wifid.py -lr --detailed

```
Outputs
```bash
Report [Period: 2017-11-26T06:00:00Z]
 |   report type   |               URL PATH                | size [MB]  |
 | -------------------------------------------------------------------- |
 | radioChannel    | /product/xxxxxx..606/a.csv | 34         |
 | auxiliary       | /product/xxxxxx..112606/b.csv | 5          |
 | interfaces      | /product/xxxxxx..112606/c.csv | 59         |
 | station         | /product/xxxxxx..17112606/d.csv | 587        |
 | command         | /product/xxxxxx..7112606/e.csv | 1          |
 | radio           | /product/xxxxxx..2017112606/f.csv | 10         |
 | cure            | /product/xxxxxx..D2017112606/g.csv | 35         |
 | gateway         | /product/xxxxxx..17112606/h.csv | 11         |
 Report [Period: 2017-11-26T12:00:00Z]
 |   report type   |               URL PATH                | size [MB]  |
 | -------------------------------------------------------------------- |
 | radioChannel    | /product/xxxxxx..612/a.csv | 34         |
 | auxiliary       | /product/xxxxxx..112612/b.csv | 5          |
 | interfaces      | /product/xxxxxx..112612/c.csv | 59         |
 | station         | /product/xxxxxx..17112612/d.csv | 586        |
 | command         | /product/xxxxxx..7112612/e.csv | 1          |
 | radio           | /product/xxxxxx..2017112612/f.csv | 10         |
 | cure            | /product/xxxxxx..D2017112612/g.csv | 35         |
 | gateway         | /product/xxxxxx..17112612/h.csv | 11         |
 Report [Period: 2017-11-26T18:00:00Z]
 |   report type   |               URL PATH                | size [MB]  |
 | -------------------------------------------------------------------- |
 | radioChannel    | /product/xxxxxx..618/a.csv | 34         |
 | auxiliary       | /product/xxxxxx..112618/b.csv | 5          |
 | interfaces      | /product/xxxxxx..112618/c.csv | 59         |
 | station         | /product/xxxxxx..17112618/d.csv | 585        |
 | command         | /product/xxxxxx..7112618/e.csv | 1          |
 | radio           | /product/xxxxxx..2017112618/f.csv | 10         |
 | cure            | /product/xxxxxx..D2017112618/g.csv | 35         |
 | gateway         | /product/xxxxxx..17112618/h.csv | 11         |
----------------------------------------
SUMMARY: 
 TOTAL_FILES: 24
 TOTAL_DOWNLOADABLE [MB]: 2232      

```


## Install as a Service on CentOS [Manually]
Create a systemd file named wd-doc.service to be placed in 
/etc/system/systemd/wd.service
```
[Unit]
Description=wd report downloader
After=multi-user.target

[Service]
User=centos
ExecStart=/usr/bin/python /install/directory/s3-cli/wd.py -dl
Restart=always
TimeoutStartSec=10
RestartSec=3600

[Install]
WantedBy=multi-user.target
```
Install and enable this service with:
```bash
$ systemctl enable wd
$ systemctl start wd
```
## Install as a Service on CentOS [Using CLI]
Run the below command and it will attempt to install the required service files on the 
given host. 
Where the interval arguement allows you to specify how frequently do you want the 
service to poll the report API for new reports. i.e daily, 12h, 18h, 6h etc
```bash
$ python wd.py -sd --interval daily
```

Other options are available for installing in a daemon/polling mode, such as crontab or 
a python run loop. Explore the help options to get further infromation.