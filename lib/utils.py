from __future__ import print_function
import yaml
import json
import requests
import os
import errno
import logging
from logging.handlers import RotatingFileHandler
import sys
import re
# from .models import Reports, Report, IndexItem, URL, Service
from datetime import timedelta, datetime
from .exceptions import *
import imp

try:
    imp.find_module('tqdm')
    import tqdm

    loading_bar = True
except ImportError:
    loading_bar = False

logger = logging.getLogger('Util')

import signal
import time


class catch_sigint(object):
    def __init__(self):
        self.caught_sigint = False

    def note_sigint(self, signum, frame):
        self.caught_sigint = True

    def __enter__(self):
        self.oldsigint = signal.signal(signal.SIGINT, self.note_sigint)
        return self

    def __exit__(self, *args):
        signal.signal(signal.SIGINT, self.oldsigint)

    def __call__(self):
        return self.caught_sigint


def truncate_dict(d):
    top = d.items()[0:1]
    bottom = d.items()[-2:]
    mid = [('...', '...'), ('...', '...')]
    return dict(sum(top, bottom, mid), [])


def logthis(logger_instance, level):
    def _decorator(fn):
        def _decorated(*arg, **kwargs):
            logger_instance.log(level, "calling '%s'(%r,%r)", fn.func_name, arg, kwargs)
            ret = fn(*arg, **kwargs)
            if isinstance(ret, dict):
                truncated_ret = {}
                for key, value in ret.items():
                    if isinstance(value, str) or isinstance(value, unicode):
                        truncated_ret[key] = "{}...{}".format(value[0:5], value[-10:]) if len(value) > 20 else value
                    else:
                        truncated_ret[key] = value
            else:
                truncated_ret = ret
                if isinstance(truncated_ret, dict):
                    if len(truncated_ret.items()) > 10:
                        logger_instance.log(level, "called '%s'(%r,%r) got return value: %r", fn.func_name, arg, kwargs,
                                            truncate_dict(truncated_ret))
                    else:
                        logger_instance.log(level, "called '%s'(%r,%r) got return value: %r", fn.func_name, arg, kwargs,
                                            truncated_ret)
                else:
                    logger_instance.log(level, "called '%s'(%r,%r) got return value: %r", fn.func_name, arg, kwargs,
                                        truncated_ret)
                    logger_instance.log(level, "called '%s'(%r,%r) got return value: %r", fn.func_name, arg, kwargs,
                                        truncated_ret)
            return ret

        return _decorated

    return _decorator


def timeit(method):
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        if 'log_time' in kw:
            name = kw.get('log_name', method.__name__.upper())
            kw['log_time'][name] = int((te - ts) * 1000)
        else:
            print('%r  %2.2f ms' % \
                  (method.__name__, (te - ts) * 1000))
        return result

    return timed


class TqdmLoggingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super(self.__class__, self).__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.tqdm.write(msg)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


logger.addHandler(TqdmLoggingHandler())


@logthis(logger, logging.DEBUG)
def load_config(file_path):
    """
    Load YAML configuration from given file path and return parsed content as dict
    :param file_path:
    :return: dict
    """

    with open(file_path, 'r') as fp:
        try:
            config = yaml.load(fp)
            return config
        except yaml.YAMLError as e:
            print("Error loading configuration with: {}".format(e))
            return None


@logthis(logger, logging.DEBUG)
def process_token(response):
    """
    Process json response from token url and manage token expire time etc
    :param response: dict:
    {
    u'session_state': u'52aa9be3-1ef9-46cd-9259-xxxxxxxxxxxxxxxxxxxx',
    u'access_token': u'....', u'id_token': u'....',
    u'expires_in': 300, u'token_type': u'bearer',
    'token_expire_time': 1511149350, 'refresh_token_expire_time': 1511152650,
    u'not-before-policy': 0, u'refresh_expires_in': 3600,
    u'refresh_token': u'....'}

    :return: dict: token
    """
    now = int(time.time())
    tokens = response.json()
    tokens['token_expire_time'] = tokens['expires_in'] + now - 1
    tokens['refresh_token_expire_time'] = tokens['refresh_expires_in'] + now - 1
    return tokens


def process_unexpected_response(response):
    """
    Process/format unexpected response
    :param response:
    :return:
    """
    message = {'status_code': response.status_code}
    try:
        message['body'] = map(lambda y: (y[0], "{}...".format(y[1][:20])) if len(y[1]) > 20 else (y[0], y[1]),
                              response.json())
    except Exception as e:
        message['body'] = "parse_failed:error:{}".format(e)
    message['headers'] = response.headers
    return message


def validate_token(token):
    """
    Check if token is valid based of the tokens current expiry timings
    :param token:
    {
    u'session_state': u'52aa9be3-1ef9-46cd-9259-xxxxxxxxxxxxxxxxx',
    u'access_token': u'....', u'id_token': u'....',
    u'expires_in': 300, u'token_type': u'bearer',
    'token_expire_time': 1511149350, 'refresh_token_expire_time': 1511152650,
    u'not-before-policy': 0, u'refresh_expires_in': 3600,
    u'refresh_token': u'....'}
    :return:
    """
    now = int(time.time())
    if token['token_expire_time'] < now < token['refresh_token_expire_time']:
        # access_token expired, can still use refresh_token
        return 1
    elif now > token['refresh_token_expire_time']:
        return -1
    elif now < token['token_expire_time']:
        return 0




def is_writable(directory):
    """
    Checks if directory is writable for process user
    :param directory:
    :return:
    """
    try:
        make_sure_path_exists(directory)
        tmp_prefix = "write_tester";
        count = 0
        filename = os.path.join(directory, tmp_prefix)
        while os.path.exists(filename):
            filename = "{}.{}".format(os.path.join(directory, tmp_prefix), count)
            count = count + 1
        f = open(filename, "w")
        f.close()
        os.remove(filename)
        return True
    except Exception as e:
        logger.info("DIRECTORY_UNWRITABLE:directory:{}".format(directory))
        return False


def make_sure_path_exists(path):
    """
    Check if path exists, otherwise creates it.
    :param path:
    :return:
    """
    try:
        os.makedirs(path)
        return True
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise Exception("CANNOT CREATE DIRECTORY: {}".format(path))


def make_sure_directory_exists(directory):
    """
    Check if directory exists, otherwise creates it.
    :param directory:
    :return:
    """

    if re.search('\S\.[A-z]+$', directory):
        logger.debug("MAKE_SURE_DIRECTORY_EXITS:REFORMATTING:directory_old:{}".format(directory))
        directory = '/'.join(directory.split('/')[:-1])
        logger.debug("MAKE_SURE_DIRECTORY_EXITS:REFORMATTING:directory_new:{}".format(directory))

    try:
        os.makedirs(directory)
        return True
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            logger.exception("CANNOT CREATE DIRECTORY:{}\n\t\t\t   MESSAGE:{}".format(directory, exception))
            raise Exception("CANNOT CREATE DIRECTORY:{}\n\t\t\t   MESSAGE:{}".format(directory, exception))
        else:
            return True


def destination_exists(path):
    """
    Check if path exists
    :param path:
    :return:
    """
    return os.path.exists(path)


def directory_exists(directory):
    """
    Check if directory
    :param path:
    :return:
    """
    return os.path.exists(directory)


def setup_logging(logging_conf):
    """
    Setup the logging configured as per the yaml configuration specifications
    :param logging_conf:
    :return:
    """
    log = logging.getLogger('')
    log.setLevel(getattr(logging, logging_conf['level'].upper()))

    if logging_conf is None:
        logging_conf = {'enabled': False, 'level': 'critical'}
    if logging_conf['enabled'] and logging_conf['debug'] and not logging_conf['file']:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        log.addHandler(ch)

    if logging_conf['enabled'] and logging_conf['file']:
        make_sure_directory_exists(logging_conf['file'])
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                      datefmt='%m/%d/%Y %I:%M:%S %p', )
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        log.addHandler(ch)

        fh = RotatingFileHandler(logging_conf['file'], maxBytes=(1048576 * 5), backupCount=3)
        fh.setFormatter(formatter)
        log.addHandler(fh)
    if not logging_conf['enabled']:
        logging.basicConfig(level=logging.CRITICAL)
    return


def multi_download_file(write_lock, idx, num_tasks, url, attempt, chunk_size, timeout):
    return download_file(url, attempt, write_lock, chunk_size, timeout, idx, num_tasks)


@logthis(logger, logging.DEBUG)
def download_file(url_obj, attempt, write_lock, chunk_size=8096, timeout=20, idx=0, num_tasks=1):
    """
    Download a given file via requests streaming interface
    :param url_obj:
    :param chunk_size:
    :param timeout:
    :param num_tasks:
    :param attempt:
    :param write_lock:
    :param idx: process id
    :param url: s3 pre-signed object URL
    :return:
    """
    # TODO: Add more URL object manipulation and create an interface that enables index writing based of the state of
    #  URL object. This will give a cleaner interface for writing indexes. Potentially something like URL().index
    ts = time.time()
    url = url_obj.get_url()
    destination = url_obj.get_path()
    if destination_exists(destination) and attempt <= 1:
        logger.warn("DOWNLOAD_FILE:EXISTS_ALREADY:OVERWRITING:{}".format(destination))
    if not directory_exists(destination):
        make_sure_directory_exists(destination)
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        size = int(response.headers['Content-length'])  # size in bytes
        url_obj.set_size(size)

        logger.debug("DOWNLOAD_FILE:URL:{}..{}".format(url[:25], url[-25:]))
        logger.debug("DOWNLOAD_FILE:FILE_SIZE::{} [MB]".format(size / 10 ** 6))

        # return
        write_lock.acquire()
        with open(destination, 'wb') as f:
            if loading_bar:

                descr = "|worker:{:2}|task:{:2}/{:2}|size:{:5}[MB]|{:50}".format(
                    idx, url_obj.get_position(), num_tasks, size / 10 ** 6, destination)

                with tqdm.tqdm(total=size, position=idx + 1, desc=descr, unit='B', unit_scale=True) as t:
                    write_lock.release()

                    def update():
                        write_lock.acquire()
                        t.update(chunk_size)
                        write_lock.release()

                    def close():
                        write_lock.acquire()
                        t.set_postfix_str("COMPLETED", True)
                        t.clear()
                        t.close()
                        write_lock.release()

                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            update()
                    close()
            else:
                write_lock.release()
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)

        logger.debug("DOWNLOAD_FILE:COMPLETE:DESTINATION:{}".format(destination))
        return url_obj
    except requests.ConnectionError as ete:
        logger.debug("DOWNLOAD_FILE:CONNECTION_TIMEOUT:MESSAGE:{}".format(ete))
        return False
    except requests.ReadTimeout as rte:
        logger.debug("DOWNLOAD_FILE:READ_TIMEOUT:MESSAGE:{}".format(rte))
        return False
    except KeyboardInterrupt as kie:
        logger.debug("DOWNLOAD_FILE:KEYBOARD_INTERRUPT:MESSAGE:{}".format(kie))
        return False
    except Exception as e:
        logger.debug("DOWNLOAD_FILE:UNKNOWN_FAILURE:MESSAGE:{}".format(e))
        return False
    finally:
        te = time.time()
        logger.debug("DOWNLOAD_FILE:TOOK:{:0.2f} seconds".format(float((te - ts))))


def multi_content_fetch(lk, idx, num_tasks, url, attempt, timeout):
    return download_file_meta(lk, idx, url, num_tasks, attempt, timeout)


def download_file_meta(lk, idx, url, num_tasks, attempt, timeout):
    """
    Download header content from file and process into a meta object representing information about the
    content to be downloaded.
    :param idx:
    :param url:
    :param num_tasks:
    :param attempt:
    :param timeout:
    :return:
    """
    ts = time.time()
    try:
        response = requests.get(url.get_url(), stream=True, timeout=timeout)
        response.close()
        # logger.debug("DOWNLOAD_FILE_META:headers:{}".format(response.headers))
        size = int(response.headers['Content-length'])  # size in bytes
        url.set_size(size)
        return url
    except requests.ConnectionError as ete:
        logger.debug("DOWNLOAD_FILE:CONNECTION_TIMEOUT:MESSAGE:{}".format(ete))
        return False
    except requests.ReadTimeout as rte:
        logger.debug("DOWNLOAD_FILE:READ_TIMEOUT:MESSAGE:{}".format(rte))
        return False
    except KeyboardInterrupt as kie:
        logger.debug("DOWNLOAD_FILE:KEYBOARD_INTERRUPT:MESSAGE:{}".format(kie))
        return False
    except Exception as e:
        logger.debug("DOWNLOAD_FILE:UNKNOWN_FAILURE:MESSAGE:{}".format(e))
        return False
    finally:
        te = time.time()
        logger.debug("DOWNLOAD_FILE:TOOK:{:0.2f} seconds".format(float((te - ts))))


@logthis(logger, logging.DEBUG)
def append_index(index_path, indexItem):
    """
    Add IndexItem to index file, if index file doesnt exist then it is created wit a+ mode
    :param index_path:
    :param destination:
    :return:
    """
    if not make_sure_directory_exists(index_path):
        logger.exception("APPEND_INDEX_FAILURE:CANNOT_MAKE_DIRECTORY")
        raise Exception("CANNOT_APPEND_INDEX")
    try:
        mode = 'a' if destination_exists(index_path) else 'a+'
        with open(index_path, mode=mode) as f:
            json.dump(indexItem.dumps(), f)
            f.write('\n')
        return indexItem
    except Exception as e:
        logger.exception("APPEND_INDEX_FAILURE:MESSAGE:{}".format(e))
        raise Exception("CANNOT_APPEND_INDEX")




def get_file_modified_time(destination):
    """
    Determine the last modified time of a given file
    :param destination:
    :return:
    """
    if destination_exists(destination):
        return os.stat(destination).st_mtime
    else:
        return None


def touch(fname, times=None):
    fhandle = open(fname, 'a')
    try:
        os.utime(fname, times)
    finally:
        fhandle.close()


def rm_file(fname):
    """
    Removes a given file
    :param fname: full file path
    :return: boolean
    """
    # TODO: add more advanced features for file tree cleanup etc.
    try:
        os.remove(fname)
        return True
    except:
        raise Exception
    finally:
        logger.debug("RM_FILE:REMOVED:{}".format(fname))


def get_time_now():
    return datetime.utcnow().isoformat()[:-7] + 'Z'


def get_time_day_ago():
    return (datetime.utcnow() - timedelta(days=1)).isoformat()[:-7] + 'Z'


def get_time_retention_period_ago(retention_time):
    seconds = parse_interval(retention_time)
    return (datetime.utcnow() - timedelta(days=1)).isoformat()[:-7] + 'Z'


def join(path1, path2):
    return os.path.join(path1, path2)


def systemd_available():
    """
    Check that the systemd file has been correctly installed and is present in the expected directory
    :return:
    """
    if destination_exists('/etc/systemd/system/wifid.service'):
        return True


def parse_interval(interval):
    """
    process/convert the interval value into a integer representation
    :param interval: can be string or int
    :return: int
    """
    if isinstance(interval, int):
        return interval
    if isinstance(interval, str):
        period_formatting = re.search('(?P<value>[0-9]+)(?P<period>[A-z])$', interval)
        word_formatting = re.search('[A-z]+$', interval)
        if period_formatting:
            # format is 160m or 24h
            try:

                value = int(period_formatting.groupdict()['value'])
                period = str(period_formatting.groupdict()['period'])
                if period == 'h':
                    return value * 60 * 60
                elif period == 'm':
                    return value * 60
                elif period == 'd':
                    return value * 60 * 60 * 24
                elif period == 'w':
                    return value * 60 * 60 * 24 * 7
                else:
                    raise InvalidIntervalUsed(
                        "invalid interval specified: {}, must be either <value [type int]><period [type str]> i.e "
                        "60m, 1h or 5d".format(interval))

            except InvalidIntervalUsed as iiu:
                raise Exception(iiu)
            except Exception as e:
                raise InvalidIntervalUsed(e)

        if word_formatting:
            if interval == 'daily':
                return 60 * 60 * 24
            elif interval == 'weekly':
                return 60 * 60 * 24 * 7
            elif interval == 'hourly':
                return 60 * 60
            else:
                raise InvalidIntervalUsed(
                    "invalid interval specified: {}, must be either daily, weekly or hourly".format(interval))


def parse_date(date):
    """
    attempt to parse different date formats
    :param date:
    :return:
    """
    try:
        return datetime.strptime(date, 'YYYY-MM-dd').isoformat() + 'Z'
    except Exception as e:
        # logger.exception("ERROR_PARSING:E:{}".format(e))
        pass
    try:
        return datetime.strptime(date, '%Y-%m-%d').isoformat() + 'Z'
    except Exception as e:
        # logger.exception("ERROR_PARSING:E:{}".format(e))
        pass
    try:
        return datetime.strptime(date, '%Y-%m-%d %H:%M:%S').isoformat() + 'Z'
    except Exception as e:
        # logger.exception("ERROR_PARSING:E:{}".format(e))
        pass
    try:
        return datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ').isoformat() + 'Z'
    except Exception as e:
        # logger.exception("ERROR_PARSING:E:{}".format(e))
        pass
    try:
        return datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ').isoformat() + 'Z'
    except Exception as e:
        # logger.exception("ERROR_PARSING:E:{}".format(e))
        pass
    raise Exception

@logthis(logger, logging.DEBUG)
def get_report_period(date):
    """
    Map the given report time into a report period i.e the following hour grouping:
    day x
    Report 0 - 00:00:00
    Report 1 - 06:00:00
    Report 2 - 12:00:00
    Report 4 - 18:00:00
    :param date:
    :return:
    """

    if isinstance(date, str):
        parsed_date = datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ')
    elif isinstance(date, unicode):
        parsed_date = datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ')
    elif isinstance(date, datetime):
        parsed_date = date
    else:
        logger.exception("TIMESTAMP_PARSE_FAILED:{}".format(date))
        raise Exception
    report_num = int(parsed_date.hour / 6) + 1
    return ("{}-{}-{} Report:{:d} [{}]".format(parsed_date.year,
                                               parsed_date.month,
                                               parsed_date.day,
                                               report_num,
                                               parsed_date.isoformat() + 'Z'),
            report_num)


def initializer():
    """Ignore SIGINT in child workers."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
