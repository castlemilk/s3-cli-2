from lib import utils
import logging
import time
from multiprocessing import Queue, Process, freeze_support, Lock
from Queue import Empty
import tqdm
from .models import IndexItem, URL, Reports

logger = logging.getLogger('S3Downloader')


class S3Downloader:
    """
    Class reponsible for multi-process/multi-threaded file download. Takes in a list of urls and carries out the
    download of all given files
    """

    @utils.logthis(logger, logging.INFO)
    def __init__(self, config, urls=None):
        if utils.is_writable(config['directory']):
            self.save_path = config['directory']
        else:
            raise Exception("CANNOT_WRITE_TO_DIRECTORY: {}".format(config['directory']))
        self.chunk_size = 8096
        self.timeout = 20
        self.meta_timeout = 3
        self.workers = 10
        self.urls = urls
        self.queue = Queue()
        self.index_path = "{}/{}".format(self.save_path, 'history.index')
        self.index_lmt = utils.get_file_modified_time(self.index_path)
        self.retention_time = config['retention_time']
        self.reports = Reports(self.save_path, self.index_path, self.retention_time)
        self.index = self.reports.load_index()

    def download_reports(self, reports):
        """
        Download a set of urls
        :param reports:
        [
        Report,
        Report,
        Report
        ]
        :return:
        """
        # TODO: make the Reports object responsible for de-duping and managing the index read/write
        for id, report in reports.reports.items():
            self.reports.add(report)
        self.reports.prune_stale_reports()
        return self.download_urls()

    def download_urls(self):
        """
        Download a set of urls
        Will attempt to download failed urls twice, after this it will return a list of urls still not downloaded.
        The scenario where this will occur is when it takes longer than 15 minutes for the workers to start downloading
        all files. If this happens then the pre-signged aws URLS will no longer be valid. The returned URLS will
        trigger the above manager to re-run the download_urls function, but in doing so will be fetching fresh
        pre-signed urls. The above manager will handle the refining down of the report summary to ensure only the desired
        URLS are to be processed.
        :param reports:
        :param urls:
        [
        {
            'url': 'https://.....blabla.com'
            'meta': {
                u'path': '2017/11/20/06/interfaces.csv'
                u'report_type': 'interfaces',
                u'year': u'2017'
                u'month': u'11',
                u'day': u'20',
                u'hour': u'06',
                u'tenant': u'adrtgw45-0b09-4722-ab0e-xxxxxxxxxxxxxx'
            },
            ...
        ]
        :return:
        """
        urls = self.reports.get_downloadable_urls()
        if not urls:
            return 0
        try:
            attempt = 1
            while urls:
                num_tasks = len(urls)
                logger.info("DOWNLOAD_REPORTS:RUN:{}".format(attempt))
                logger.info("DOWNLOAD_REPORTS:URL:NUM_TASKS:{}".format(num_tasks))
                failed_urls = []
                freeze_support()
                write_lock = Lock()
                in_queue = Queue(num_tasks)
                fail_queue = Queue(num_tasks)
                out_queue = Queue(num_tasks)

                tqdm.tqdm.write("|   DOWNLOADING {} FILES".format(num_tasks))

                def worker(lk, idx, in_jobs, out_jobs, fail_jobs, history_file, chunk_size, timeout):
                    try:
                        while True:
                            url_obj = in_jobs.get_nowait()
                            success = utils.multi_download_file(lk,
                                                                idx,
                                                                num_tasks,
                                                                url_obj,
                                                                attempt,
                                                                chunk_size,
                                                                timeout)
                            if isinstance(success, URL):
                                out_jobs.put_nowait(success)
                                lk.acquire()
                                self.reports.append_index(IndexItem(url_obj.get_path()))
                                lk.release()

                            else:
                                fail_jobs.put_nowait(url_obj)
                    except Empty:
                        logger.debug("WORKER:QUEUE_EMPTY:WORKER:PID:{}:NAME:{}".format(p.pid, p.name))
                        return None
                    except KeyboardInterrupt as kbi:
                        logger.warn("FAILED_TO_JOIN:KEYBOARD_INTERRUPT:{}".format(kbi))
                        return
                    except Exception as e:
                        logger.exception("WORKER_EXCEPTION:EXCEPTION:{}".format(e))
                        return None

                if fail_queue.empty():
                    for url in urls:
                        in_queue.put(url, timeout=1)
                else:
                    while not fail_queue.empty():
                        failed_urls.append(fail_queue.get())

                urls = failed_urls
                if attempt > 2:
                    self.reports.set_downloaded(False)
                    raise utils.ExcessiveDownloadAttempts()

                processes = []
                for i in range(0, self.workers):
                    p = Process(target=worker,
                                args=[write_lock, i, in_queue, out_queue, fail_queue, self.index_path, self.chunk_size,
                                      self.timeout])
                    p.daemon = True
                    p.start()
                    processes.append(p)

                while True:
                    try:
                        url = out_queue.get_nowait()
                        self.reports.update_url(url)
                    except Empty:
                        time.sleep(.2)
                    if not any(p.is_alive() for p in processes) and out_queue.empty() and fail_queue.empty():
                        # all the workers are done and nothing is in the queue
                        logger.debug("DONE:PROCESS_STATUS:{}".format([p.is_alive() for p in processes]))
                        out_queue.close()
                        fail_queue.close()
                        in_queue.close()
                        self.reports.set_downloaded(True)
                        return self.reports
                    elif not fail_queue.empty():
                        while not fail_queue.empty():
                            failed_urls.append(fail_queue.get())
                        urls = failed_urls
                        attempt += 1
                        self.reports.set_downloaded(False)
                        break
                attempt += 1
        except utils.ExcessiveDownloadAttempts:
            logger.exception("DOWNLOAD_REPORTS:EXCESSIVE_ATTEMPTS_MADE:REFRESHING_PRE_SIGNED_URLS")
            # TODO: do a pre-signed refresh here and rerun-download as required
            return urls

    def get_reports_meta(self, reports = None):
        """
        Multiprocess fetch the header content from the given list of urls and return this meta-information.
        Metadata is updated on the Report object via the update() method which will hydrate the object with
        any additional properties that are discovered when a url dictionary is passed into the update method.
        :param reports:
        :return:
        """
        if reports:
            self.reports = reports
        if not self.reports:
            raise Exception("No reports available")
        urls = self.reports.get_urls()
        print(urls)
        workers = 10
        urls_meta = []
        try:
            attempt = 1
            while urls:
                num_tasks = len(urls)
                failed_urls = []
                freeze_support()
                write_lock = Lock()
                in_queue = Queue(num_tasks * 2)
                out_queue = Queue(num_tasks * 2)
                fail_queue = Queue(num_tasks * 2)

                def worker(lk, idx, in_jobs, out_jobs, fail_jobs, timeout):
                    try:
                        while True:

                            url_item = in_jobs.get_nowait()
                            url_with_meta = utils.multi_content_fetch(lk,
                                                                      idx,
                                                                      num_tasks,
                                                                      url_item,
                                                                      attempt,
                                                                      timeout)
                            if isinstance(url_with_meta, URL):
                                logger.debug("WORKER:URL:SUCCESS")
                                out_jobs.put_nowait(url_with_meta)

                            else:
                                logger.debug("WORKER:URL:FAILURE")
                                fail_jobs.put(url_item, block=False, timeout=1)
                    except Empty:
                        logger.debug("WORKER:QUEUE:EMPTY")
                        # return

                if fail_queue.empty():
                    for url in urls:
                        in_queue.put_nowait(url)

                if attempt > 2:
                    raise utils.ExcessiveDownloadAttempts()

                processes = []
                for i in range(0, workers):
                    p = Process(target=worker, args=[write_lock, i, in_queue, out_queue, fail_queue, self.meta_timeout])
                    p.daemon = True
                    p.start()
                    processes.append(p)
                while True:
                    try:
                        url = out_queue.get_nowait()
                        self.reports.update_url(url)

                    except Empty:
                        time.sleep(.2)
                    finally:
                        if not any(p.is_alive() for p in processes) and out_queue.empty() and fail_queue.empty():
                            # all the workers are done and nothing is in the queue
                            logger.debug("DONE:PROCESS_STATUS:{}".format([p.is_alive() for p in processes]))
                            out_queue.close()
                            fail_queue.close()
                            in_queue.close()
                            return self.reports
                        elif not fail_queue.empty():
                            while not fail_queue.empty():
                                failed_urls.append(fail_queue.get())
                            urls = failed_urls
                            attempt += 1
                            break




        except utils.ExcessiveDownloadAttempts:
            logger.exception("DOWNLOAD_META:EXCESSIVE_ATTEMPTS_MADE")
            # TODO: do a pre-signed refresh here and rerun-download as required
            return urls_meta