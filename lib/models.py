from utils import destination_exists, \
    touch, make_sure_directory_exists, directory_exists, is_writable, \
    parse_interval, rm_file, get_report_period, parse_date
from .exceptions import *
import base64
from urlparse import urlparse
from datetime import timedelta, datetime
import json
from uuid import uuid4
import sys
import os
import re
from subprocess import call

import logging

logger = logging.getLogger('Models')


class Reports(object):
    """
    Top Level manager object which handles the updating and presentation/formatting of data for a given number
    of Report objects
    """

    def __init__(self, save_path=None, index_path=None, retention_time=None):
        self.uuid = uuid4()
        self.reports = dict()
        self.save_path = save_path
        self.index = None
        self.index_path = index_path
        self.downloaded = False
        self.retention_time = retention_time

    def get_sorted_reports(self, reverse=False):
        return sorted(self.reports.items(), key=lambda x: x[1].timestamp, reverse=reverse)

    def filter(self, filter_type, value):
        """
        Filter reports based of type and value
        :param filter_type:
        :param value:
        :return:
        """
        if filter_type == 'rn':
            self.reports = dict(filter(
                lambda x: any([x[1].report_number == int(rn) for rn in value]), self.reports.items()))
        elif filter_type == 'rrn':
            sorted_reports = self.get_sorted_reports(reverse=True)
            self.reports = dict([sorted_reports[int(x)-1] for x in value])


    def parse_report_list(self, report_list):
        """
            Parse the response body from the report list endpoint
            :param report_list: sample:
            {
              "period": {
                "start": "2016-02-16T09:32:18Z",
                "end": "2016-02-17T09:32:18Z"
              },
              "history": {
                [
                  {
                    "timestamp": "2016-02-17T00:00:00",
                    "report": {
                      "a": "https://path/to/gateway-b.csv",
                      "b": "https://path/to/gateway-aux-b.csv",
                      "c": "https://path/to/radio-b.csv",
                      "d": "https://path/to/radio-channel-b.csv",
                      "e": "https://path/to/station-b.csv",
                      "f": "https://path/to/cure-b.csv",
                      "g": "https://path/to/command-b.csv"
                    }
                  }
                  {
                    "timestamp": "2016-02-17T00:00:00",
                    "report": {
                      "a": "https://path/to/gateway-b.csv",
                      "b": "https://path/to/gateway-aux-b.csv",
                      "c": "https://path/to/radio-b.csv",
                      "d": "https://path/to/radio-channel-b.csv",
                      "e": "https://path/to/station-b.csv",
                      "f": "https://path/to/cure-b.csv",
                      "g": "https://path/to/command-b.csv"
                    }
                  }
                ]
              }
            }
            :return:
            """
        for report in report_list['history']:
            report_obj = Report(report['timestamp'], report['report'])
            self.add(report_obj)

    def set_index(self, index):
        self.index = index

    def get_index(self):
        return self.index

    def set_downloaded(self, downloaded):
        self.downloaded = downloaded

    def get_downloaded(self):
        return self.downloaded

    def get_downloaded_size(self):
        return sum(filter(None, map(lambda x: x.get_size(), self.get_urls()))) / 10 ** 6

    def append_index(self, indexItem):
        """
        Add IndexItem to index file, if index file doesnt exist then it is created wit a+ mode
        :param index_path:
        :param destination:
        :return:
        """
        if not make_sure_directory_exists(self.index_path):
            logger.exception("APPEND_INDEX_FAILURE:CANNOT_MAKE_DIRECTORY")
            raise Exception("CANNOT_APPEND_INDEX")
        try:
            mode = 'a' if destination_exists(self.index_path) else 'a+'
            with open(self.index_path, mode=mode) as f:
                json.dump(indexItem.dumps(), f)
                f.write('\n')
            return indexItem
        except Exception as e:
            logger.exception("APPEND_INDEX_FAILURE:MESSAGE:{}".format(e))
            raise Exception("CANNOT_APPEND_INDEX")

    def load_index(self, index_path=None):
        """
          Load the historical index for previously downloaded files
          :param index_path:
          :return:
          [
          IndexItem,
          IndexItem,
          IndexItem,
          ...
          IndexItem,
          ]
          """
        if index_path:
            self.index_path = index_path
        if not destination_exists(self.index_path):
            touch(self.index_path)
            self.index = [IndexItem('')]
            return self.index
        try:
            with open(self.index_path, mode='r') as f:
                index = map(lambda x: IndexItem(json.loads(x)), f.readlines())
                if index:
                    self.index = index
                    return self.index
                else:
                    self.index = [IndexItem('')]
                    return self.index
        except Exception as e:
            logger.exception("LOAD_INDEX_FAILURE:MESSAGE:{}".format(e))
            raise Exception("LOAD_INDEX_FAILURE")

    def destination_in_index(self, destination):
        """
            Check if url exists in historical index
            :param index: either index of type index_file_location or a list of IndexItems
            :param destination: save_path + report_prefix
            :return:
            """
        obj = IndexItem(destination)
        if isinstance(self.index, str):
            return next(iter(filter(lambda x: x.get_hash() == obj.get_hash(), set(self.load_index(self.index)))), None)
        elif isinstance(self.index, list):
            return next(iter(filter(lambda x: x.get_hash() == obj.get_hash(), set(self.index))), None)
        else:
            return

    def get_prunable_reports(self, retention_time=None):
        """
        Determine which reports can be pruned based of a comparison between downloaded time and the specified
        retention period
        :param retention_time:
        :return:
        """
        # if not isinstance(retention_time, datetime):
        #     raise Exception
        if retention_time:
            self.retention_time = retention_time

        if isinstance(self.index, list):
            return map(lambda x: base64.b64decode(x.get_hash()),
                       filter(lambda x: x.stale(self.retention_time), self.index))
        elif self.index_path:
            self.index = self.load_index(self.index_path)
            return map(lambda x: base64.b64decode(x.get_hash()),
                       filter(lambda x: x.stale(self.retention_time), self.index))
        else:
            raise Exception

    def prune_stale_reports(self, retention_time=None):
        """
        Remove reports classified as stale, freeing up space on disk
        :param retention_time:
        :return:
        """
        if retention_time:
            self.retention_time = retention_time
        if not self.retention_time:
            raise NoRetentionTimeSpecified()
        stale_files = self.get_prunable_reports()
        for file_path in stale_files:
            if destination_exists(file_path):
                rm_file(file_path)
            else:
                logger.debug("FILE_ALREADY_REMOVED:{}".format(file_path))

        return True

    def get_downloadable_urls(self, index_path=None, index=None, save_path=None):
        if index_path:
            self.index_path = index_path
        if index:
            self.index = index
        if save_path:
            self.save_path = save_path
        if not self.index or not self.save_path:
            raise Exception("MUST UPDATE REPORT OBJECT WITH BOTH INDEX AND SAVE_PATH INFORMATION")
        urls = self.get_urls()
        num_reports_found = len(urls)
        skippable_reports = 0
        downloadable_urls = []
        for url in urls:
            destination = url.get_path(self.save_path)
            exists = self.destination_in_index(destination)
            if exists:
                skippable_reports += 1
                continue
            else:
                downloadable_urls.append(url)
        for i, url in enumerate(downloadable_urls):
            destination = url.get_path()
            url.set_save_path(self.save_path)
            url.set_position(i)
            if url.get_path():
                url.set_description("|dest:{}|".format(destination))
            else:
                url.set_description("|task:{}|".format(i))
        if skippable_reports > 0:
            logger.warn("DOWNLOAD_REPORTS:SKIPPING: {} reports out of {}".format(skippable_reports, num_reports_found))

        return downloadable_urls

    def get_save_path(self):
        return self.save_path

    def set_save_path(self, save_path):
        self.save_path = save_path
        for url in self.get_urls():
            url.set_save_path(self.save_path)
        return

    def get_num_urls(self):
        return len(self.get_urls())

    def get_total_downloadable_size(self):
        return int(sum(filter(None, map(lambda x: x.get_size(), self.get_urls()))))

    def add(self, report):
        if isinstance(report, Report):
            self.reports[report.get_id()] = report
        else:
            raise InvalidReport()

    def get_report(self, report_id):
        if self.reports.get(report_id):
            return self.reports[report_id]
        else:
            raise ReportNotFound

    def delete(self, report):
        if isinstance(report, Report):
            return self.reports.pop(report.get_id())
        elif isinstance(report, str):
            return self.reports.pop(report)

    def update_reports(self, obj):
        logger.debug("UPDATE_REPORTS:UPDATING:{}".format(obj))
        if isinstance(obj, Report):
            self.reports[obj.get_id()] = obj
            return self.reports
        else:
            raise InvalidReportUpdateInput

    def update_url(self, url):
        logger.debug("UPDATE_URLS:UPDATING:{}".format(url))
        if isinstance(url, URL):
            report = self.reports[url.get_report_id()]
            if isinstance(report, Report):
                self.reports[url.get_report_id()].urls = report.update_urls(url)
            return self.reports
        else:
            raise InvalidReportUpdateInput

    def update_reports_from_dict(self, report):
        if isinstance(report, dict):
            if report.get('id'):
                if self.reports.get(report['id']):
                    try:
                        self.reports[report['id']] = self.reports[report['id']].update(report)
                    except Exception:
                        raise Exception("Failed to update report, ID: {}, body: {}", report['id'], report)
                else:
                    raise ReportNotFound()
            elif report.get('report'):
                if self.reports.get(report['report']) and report['type']:
                    try:
                        self.reports[report['report']] = self.reports[report['report']].update(report)
                    except Exception:
                        raise Exception("Failed to update report, ID: {}, body: {}", report['id'], report)
                elif self.reports.get(report['report']) and not report['type']:
                    raise Exception("Failed to update report [no type available], ID: {}, body: {}", report['id'],
                                    report)
                elif not self.reports.get(report['report']):
                    raise ReportNotFound()
                else:
                    raise InvalidReportUpdateInput(report)
            else:
                raise InvalidReportIDSpecified(report)
            raise InvalidReport()

    def display_reports(self, detailed=False):
        """
        Display all available reports (sorted)
        :return:
        """
        for id, report in self.get_sorted_reports():
            report.display_report(detailed)

    def display_summary(self, detailed=False):
        print("{}".format("-" * 40))
        print("SUMMARY: ")
        print(" TOTAL_FILES: {}".format(self.get_num_urls()))
        if detailed:
            print(" TOTAL_DOWNLOADABLE [MB]: {:<10d}".format(self.get_total_downloadable_size() / 10 ** 6))

    def flatten_reports(self):
        """
           Flatten a list of Report objects into a list of download links and their corresponding meta-data. I.E
           [
           Report, Report, Report
           ] -> [
           {
               'url': 'https://.....blabla.com'
               'meta': {
                   u'report_type': 'interfaces',
                   u'year': u'2017'
                   u'month': u'11',
                   u'day': u'20',
                   u'hour': u'06',
                   u'tenant': u'18basdfsf953a3-0b09-4722-ab0e-xxxxxxxxxxxxxxx'
               },
               ...
           ]
           or {
           'uuid': Report,
           'uuid': Report,
           ...
           'uuid': Report
           } -> [
           {
               'url': 'https://.....blabla.com'
               'meta': {
                   u'report_type': 'interfaces',
                   u'year': u'2017'
                   u'month': u'11',
                   u'day': u'20',
                   u'hour': u'06',
                   u'tenant': u'asdfasdf-0b09-4722-ab0e-xxxxxxxxxxxxxxxxxxxxxxx'
               },
               ...
           ]
           :param reports:
           :return:
           """
        if isinstance(self.reports, list):
            return sum(map(lambda x: x.get_urls, self.reports), [])
        elif isinstance(self.reports, dict):
            return sum(map(lambda x: x.get_urls, self.reports.values()), [])
        else:
            logger.info("FLATTEN_REPORTS:INVALID_INPUT:reports:type:{}".format(type(self.reports)))
            return

    def get_urls(self):
        """
        Return a flattened list of urls across all report instances
        :return:
        """
        return self.flatten_reports()

    def get_indexed_urls(self):
        """
        Retrieve list of urls which have been indexed
        :return:
        """

    def get_url(self, url):
        if url.get_report_id():
            report = self.get_report(url.get_report_id())
            if isinstance(report, Report):
                return report.get_url(url)
            else:
                raise InvalidReportUpdateInput(url)


class Report(object):
    """
    Report serde for content returned from the historical report fetch API endpoint
    """

    def __init__(self, timestamp, kwargs):
        if isinstance(timestamp, str):
            self.timestamp = parse_date(timestamp)
        elif isinstance(timestamp, unicode):
            self.timestamp = parse_date(timestamp)
        elif isinstance(timestamp, datetime):
            self.timestamp = timestamp
        self.id = base64.b64decode(self.timestamp)
        self.urls = {}
        self.report_name, self.report_number = get_report_period(self.timestamp)
        for name, url in kwargs.items():
            if url:
                self.urls[name] = URL(self.id, name, url)

    def __repr__(self):
        header = "{}".format(self.report_name)
        body = ""
        for report_type, url in self.urls.items():
            body += "url: {}, size: {}\n".format(url.get_url(), url.get_size())
        return "{}\n{}\n".format(header, body)

    def update_urls(self, url):
        """
        Attempt to reconcile attributes and update, and if they don't exist then create or error
        :param url:
       {
                'url': '...',
                'meta': '...',
                'type': '...',
                'report': '...',
            }
        or object: URL
        :return:
        """

        if isinstance(url, dict):

            if url.get('report_type'):
                url = self.urls[url['report_type']]
                if url:
                    self.urls[url['report_type']] = url.update(url)
                    return self.urls
            else:
                raise UnknownUpdateInput(url)

        if isinstance(url, URL):

            if url.get_type():
                if url:
                    self.urls[url.get_type()] = url
                    return self.urls
            else:
                raise UnknownUpdateInput(url)

    def get_dict(self):
        return {
            'timestamp': self.timestamp,
            'id': self.id,
            'urls': self.urls,
        }

    @property
    def get_reports(self):
        """
        Return list of reports
        :return:
        [
            {
                'url': '...'
                'meta': '...'
            }
        ]
        """
        return filter(None, self.urls.values())

    @property
    def get_urls(self):
        """
        Return list of reports
        :return:
        [
            {
                'url': '...'
                'meta': '...'
            }
        ]
        """
        return filter(None, self.urls.values())

    def get_url(self, url):
        if isinstance(url, URL):
            return self.urls[url.get_type()]
        if isinstance(url, str):
            return self.urls[url]

    def get_id(self):
        return self.id

    def display_report(self, detailed=False):
        """
        display all report infromation
        :return:
        """

        print("{}".format(self.report_name))

        if detailed:
            print(" | {:^15s} | {:^37s} | {:^10s} |".format('report type', 'URL PATH', 'size [MB]'))
            print(" | {:68s} |".format("-" * 68))
        else:
            print(" | {:^15s} | {:^37s} |".format('report type', 'url'))
            print(" | {:55s} |".format("-" * 55))
        for report_type, url in self.urls.items():
            if url:
                if len(url.get_parsed_url().path) > 35:
                    if url.get_size() and detailed:
                        print(" | {:15s} | {:15s}..{:20s} | {:<10d} |".format(url.get_type(),
                                                                              url.get_parsed_url().path[0:15],
                                                                              url.get_parsed_url().path[-20:],
                                                                              url.get_size('MB'),
                                                                              ))
                    else:
                        print(" | {:15s} | {:15s}..{:20s} |".format(url.get_type(),
                                                                    url.get_parsed_url().path[0:15],
                                                                    url.get_parsed_url().path[-20:],
                                                                    ''
                                                                    ))
                else:
                    if url.get_size() and detailed:
                        print(" {:15s} | {:35s} | {:^10d} |".format(url.get_type(),
                                                                    url.get_parsed_url().path[0:15],
                                                                    url.get_size('MB')
                                                                    ))
                    else:
                        print(" {:15s} | {:35s} | ".format(url.get_type(),
                                                           url.get_parsed_url().path[0:15],
                                                           ))


class NewObject(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if isinstance(value, dict):
                value = NewObject(**value)
            setattr(self, key, value)


class URL(object):
    """
    Class for representing a AWS pre-signed URL and all of the relavent meta-data
    """

    def __init__(self, report_id, report_type, url):
        self.report_id = report_id
        self.report_type = report_type
        self.url = url
        self.save_path = None
        self.description = None
        self.parsed_url = urlparse(self.url)
        self.meta = NewObject()
        self.generate_meta()
        self.size = None
        self.position = None
        self.downloaded = False
        self.path = None

    def generate_meta(self):
        """
        From parsed aws url fetch additional meta data such as timestamp, type.

        :param name: type of url i.e a, b etc
        :param url: aws pre-signed url for download
        :return: meta information parsed from given url
        """
        map(lambda x:
            setattr(self.meta, x.split(' ')[0], x.split(' ')[1])
            if (len(x.split(' ')[1]) <= 4 or x.split(' ')[0] == 'tenant')
            else setattr(self.meta, x.split(' ')[0], x.split(' ')[1][-2:]),
            filter(lambda x: len(x.split(' ')) > 1, self.parsed_url.path.replace('%3D', ' ').split('/')))
        # meta['report_type'] = self.report_type
        setattr(self.meta, 'report_type', self.report_type)
        # if getattr(self, ) and meta.get('month') and meta.get('day') and meta.get('hour'):
        filepath = "{}/{}/{}/{}/{}".format(self.meta.year,
                                           self.meta.month,
                                           self.meta.day,
                                           self.meta.hour,
                                           self.parsed_url.path.split('/')[-1])
        # meta['path'] = filepath
        setattr(self.meta, 'path', filepath)
        # else:
        #     # meta['path'] = self.parsed_url.path.split('/')[-1]
        #     setattr(self.meta, 'path', self.parsed_url.path.split('/')[-1])
        # return meta

    def __str__(self):
        return "report_id: {}, report_type: {}, url: {}, size: {}".format(self.report_id,
                                                                          self.report_type,
                                                                          self.url,
                                                                          self.size)

    def __repr__(self):
        return "report_id: {}, report_type: {}, url: {}, size: {}".format(self.report_id,
                                                                          self.report_type,
                                                                          self.url,
                                                                          self.size)

    def get_path(self, save_path=None):
        if save_path:
            return "{}/{}".format(save_path, self.meta.path)
        else:
            return "{}/{}".format(self.save_path, self.meta.path)

    def set_path(self, path):
        self.path = path

    def get_downloaded(self):
        return self.downloaded

    def set_downloaded(self, downloaded):
        self.downloaded = downloaded

    def get_save_path(self):
        return self.save_path

    def set_save_path(self, save_path):
        self.save_path = save_path

    def get_url(self):
        return self.url

    def set_url(self, url):
        self.url = url

    def get_parsed_url(self):
        return self.parsed_url

    def get_type(self):
        return self.report_type

    def set_type(self, report_type):
        self.report_type = report_type

    def get_meta(self):
        return self.meta

    def set_meta(self, meta):
        self.meta = meta

    def get_size(self, units=None):
        if not self.size:
            return
        if units == 'MB':
            return int(self.size) / 10 ** 6
        elif units == 'GB':
            return int(self.size) / 10 ** 9
        else:
            return int(self.size)

    def set_size(self, size):
        self.size = size

    def get_description(self):
        return self.description

    def set_description(self, description):
        self.description = description

    def get_position(self):
        return self.position

    def set_position(self, position):
        self.position = position

    def get_report_id(self):
        return self.report_id

    def update_property(self, prop, value):
        return setattr(self, prop, value)

    def update(self, d):
        """

        :param d:
        :return:
        """
        if isinstance(d, dict):
            for key, value in d.items():
                current_attribute = getattr(self, key, None)
                if current_attribute:
                    setattr(self, key, value)


class IndexItem:
    """
    Serde for processing index items in the form:
    """

    def __init__(self, content):
        self.content = content
        self.date_format = "%Y-%m-%d %H:%M:%S"

        if isinstance(content, str):
            self.destination = content
            self.hash = base64.b64encode(content)
            self.date = datetime.utcnow().strftime(self.date_format)
        elif isinstance(content, dict):
            if content.get['date']:
                self.date = content['date']
            else:
                self.date = None
            # if content.get('hash'):
            self.hash = content['hash']
            self.destination = base64.b64decode(self.hash)
        elif isinstance(content, unicode):
            json_blob = json.loads(content)
            self.date = datetime.strptime(json_blob['date'], self.date_format)
            self.hash = json_blob['hash']
            self.destination = base64.b64decode(self.hash)

    def stale(self, retention_time):
        retention_date = (datetime.utcnow() - timedelta(seconds=parse_interval(retention_time)))
        if isinstance(self.date, str):
            self.date = datetime.strptime(self.date, self.date_format)
        logger.debug("INDEX_DATE:{}".format(self.date))
        logger.debug("RETENTION_DATE:{}".format(retention_date))

        # if isinstance(self.data, datetime.datetime):
        if retention_date > self.date:
            return True
        else:
            return False
        # else:
        #     if retention_date > self.date:
        #         return True
        #     else:
        #         return False


    def get_hash(self):
        return self.hash

    def get_date(self):
        return self.date

    def __repr__(self):
        return self.content

    def __str__(self):
        return "destination: {}|hash: {}|date: {}".format(self.destination, self.hash, self.date)

    def load(self, json_blob):
        """
        deserliaize a json blob into IndexItem object
        :param json_blob:
        :return:
        """
        return IndexItem(json_blob)

    def dumps(self):
        """
        return json blob representation of object
        :return:
        """
        return json.dumps({
            'date': self.date,
            'hash': self.hash
        })


class Service(object):
    def __init__(self, interval, kwargs):
        self.name = "wifid"
        self.args = kwargs
        self.service_directory = '/etc/systemd/system'
        self.service_file_name = 'wifid.service'
        self.description = "{} agent runner".format(self.name)
        self.service_properties = {}
        self.user = 'root'
        self.exec_start = self.build_exec_start(interval)
        self.command = None
        self.restart_interval = parse_interval(interval)

    def __str__(self):
        return self.get_body()

    def build_exec_start(self, interval):
        """
        Build the execStart command for the systemd file
        :param interval:
        :return:
        """
        python_executable = sys.executable
        wifi_full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wd.py')
        if self.args['rn']:
            command = "{} {} -dl -rn {}".format(python_executable, wifi_full_path, ' '.join(self.args['rn']))
        else:

            command = "{} {} -dl".format(python_executable, wifi_full_path, interval)
        self.command = command
        return command

    def get_body(self):
        body = """
[Unit]
Description={description}
After=multi-user.target

[Service]
User={user}
ExecStart={exec_start}
Restart=always
TimeoutStartSec=10
RestartSec={restart_interval}

[Install]
WantedBy=multi-user.target
        """.format(description=self.description,
                   user=self.user,
                   restart_interval=self.restart_interval,
                   exec_start=self.exec_start)
        return body

    def install(self):
        """
        Attempt install the service file into directory /etc/systemd/system/
        :return:
        """
        if not directory_exists(self.service_directory):
            raise SystemDDirectoryMissing(self.service_directory)

        if not is_writable(self.service_directory):
            raise SystemDDirectoryNotWritable(self.service_directory)

        with open(os.path.join(self.service_directory, self.service_file_name), 'w') as f:
            f.write(self.get_body())

        call(["systemctl", "enable", self.service_file_name])
        call(["systemctl", "start", self.service_file_name])

        return True


class Crontab(object):
    def __init__(self, interval):
        try:
            from crontab import CronTab
            from crontab import SPECIALS
            self.crontab_available = True
        except Exception as e:
            self.crontab_available = False
            logger.exception("ERROR:{}".format(e))
            raise CrontabNotInstalled(self.command)
        self.interval = interval
        self.name = "wifid"
        self.command = self.build_crontab_command()
        self.crontab_period = self.build_crontab_period()
        self.crontab_line = "{} {}".format(self.crontab_period, self.command)
        self.cron_job = None
        self.cron = CronTab(user=True)
        self.cron_period_set_string = SPECIALS[self.interval]

    def __str__(self):
        return self.command

    def install(self):
        if self.crontab_available:
            from crontab import CronTab

            self.cron_job = self.cron.new(command=self.command)
            self.set_interval()
            self.cron.write()

    def set_interval(self):
        """
        Translate a arbitrary interval input into the required contab formatting
        :return:
        """
        period_formatting = re.search('(?P<value>[0-9]+)(?P<period>A-z)$', self.interval)
        word_formatting = re.search('[A-z]+$', self.interval)
        if period_formatting:
            # format is 160m or 24h
            try:
                value = int(period_formatting.groupdict()['value'])
                period = str(period_formatting.groupdict()['period'])
                if period == 'h':
                    self.cron_job.every(value).hours()
                elif period == 'm':
                    self.cron_job.every(value).minutes()
                elif period == 'd':
                    self.cron_job.every(value).days()
                else:
                    raise InvalidIntervalUsed(
                        "invalid interval specified: {}, must be either daily, weekly or hourly".format(self.interval))

            except InvalidIntervalUsed as iiu:
                raise Exception(iiu)
            except Exception as e:
                raise InvalidIntervalUsed(e)

        if word_formatting:
            self.cron_job.setall(self.cron_period_set_string)
            if self.interval == 'daily':
                self.cron_job.setall(self.cron_period_set_string)
            elif self.interval == 'weekly':
                return 60 * 60 * 24 * 7
            elif self.interval == 'hourly':
                return 60 * 60
            else:
                raise InvalidIntervalUsed(
                    "invalid interval specified: {}, must be either daily, weekly or hourly".format(self.interval))

    def build_crontab_period(self):
        """

        :return:
        """

    def build_crontab_command(self):
        """
        Build the execStart command for the systemd file
        :param interval:
        :return:
        """
        python_executable = sys.executable
        wifi_full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wd.py')
        command = "{} {} -dl".format(python_executable, wifi_full_path)
        self.command = command
        return command


class Proxy:
    """
    Proxy model, providing interfaces for the structuring of proxt information
    """

    def __init__(self, secure, host, port, username=None, password=None):
        """

        :param (optional, default = HTTPS) secure: HTTP/HTTPS
        :param (required) host: resolvable host/IP address
        :param (required) port: proxy port
        :param (optional) username: proxy username
        :param (optional) password: proxy password
        """
        self.secure = secure
        self.type = 'HTTPS' if secure else 'HTTP'
        self.host = host
        self.port = port
        self.username = username
        self.password = password
