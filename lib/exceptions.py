class ExcessiveDownloadAttempts(Exception):
    """Too many download attempts"""
    pass


class InvalidReport(Exception):
    """Invalid report format"""
    pass


class ReportNotFound(Exception):
    """Could not find a report in lookup"""
    pass


class UnknownUpdateInput(Exception):
    """Update input invalid or unusable"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class InvalidReportIDSpecified(Exception):
    """Report ID not resolvable"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class InvalidReportUpdateInput(Exception):
    """Invalid input used for report update"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class InvalidIntervalUsed(Exception):
    """Invalid input used for interval"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class SystemDNotAvailable(Exception):
    """Invalid input used for interval"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class CrontabNotInstalled(Exception):
    """Crontab package not installed"""

    def __init__(self, command):
        pip_install_command = 'pip install python-crontab'
        self.message = "crontab management not possible unless package installed with:\n$ {}\nAlternatively add " \
                       "the following to crontab:\n{}".format(
            pip_install_command, command)

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class SystemDDirectoryMissing(Exception):
    """No director found"""

    def __init__(self, directory):
        self.message = " directory not found: {}: are you on CentOS?".format(directory)

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class SystemDDirectoryNotWritable(Exception):
    """Service directory not writable"""

    def __init__(self, message):
        self.message = "Service directory not writable: {}".format(message)

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class NoRetentionTimeSpecified(Exception):
    """No Retention time set"""

    def __init__(self):
        self.message = "Specify a retention time value such as 16h or 2d, in your confg.yml file"

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class InvalidDateInput(Exception):
    """No Retention time set"""

    def __init__(self, start, end):
        self.message = "start: {}, end: {}".format(start, end)

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


class StartTimeNotAvailable(Exception):
    """No Retention time set"""

    def __init__(self, start):
        self.message = "StartTime: {}".format(start)

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message
