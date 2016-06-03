##############################################################################
#
# Copyright (c) 2004 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
import os, re, sys, unittest, doctest
import zc.lockfile, time, threading
from zope.testing import renormalizing, setupstack
import tempfile
try:
    from unittest.mock import Mock, patch
except ImportError:
    from mock import Mock, patch

checker = renormalizing.RENormalizing([
    # Python 3 adds module path to error class name.
    (re.compile("zc\.lockfile\.LockError:"),
     r"LockError:"),
    ])

def inc():
    while 1:
        try:
            lock = zc.lockfile.LockFile('f.lock')
        except zc.lockfile.LockError:
            continue
        else:
            break
    f = open('f', 'r+b')
    v = int(f.readline().strip())
    time.sleep(0.01)
    v += 1
    f.seek(0)
    f.write(('%d\n' % v).encode('ASCII'))
    f.close()
    lock.close()

def many_threads_read_and_write():
    r"""
    >>> with open('f', 'w+b') as file:
    ...     _ = file.write(b'0\n')
    >>> with open('f.lock', 'w+b') as file:
    ...     _ = file.write(b'0\n')

    >>> n = 50
    >>> threads = [threading.Thread(target=inc) for i in range(n)]
    >>> _ = [thread.start() for thread in threads]
    >>> _ = [thread.join() for thread in threads]
    >>> with open('f', 'rb') as file:
    ...     saved = int(file.read().strip())
    >>> saved == n
    True

    >>> os.remove('f')

    We should only have one pid in the lock file:

    >>> f = open('f.lock')
    >>> len(f.read().strip().split())
    1
    >>> f.close()

    >>> os.remove('f.lock')

    """

def pid_in_lockfile():
    r"""
    >>> import os, zc.lockfile
    >>> pid = os.getpid()
    >>> lock = zc.lockfile.LockFile("f.lock")
    >>> f = open("f.lock")
    >>> _ = f.seek(1)
    >>> f.read().strip() == str(pid)
    True
    >>> f.close()

    Make sure that locking twice does not overwrite the old pid:

    >>> lock = zc.lockfile.LockFile("f.lock")
    Traceback (most recent call last):
      ...
    LockError: Couldn't lock 'f.lock'

    >>> f = open("f.lock")
    >>> _ = f.seek(1)
    >>> f.read().strip() == str(pid)
    True
    >>> f.close()

    >>> lock.close()
    """


def hostname_in_lockfile():
    r"""
    hostname is correctly written into the lock file when it's included in the
    lock file content template

    >>> import zc.lockfile
    >>> with patch('socket.gethostname', Mock(return_value='myhostname')):
    ...     lock = zc.lockfile.LockFile("f.lock", content_template='{hostname}')
    >>> f = open("f.lock")
    >>> _ = f.seek(1)
    >>> f.read().rstrip()
    'myhostname'
    >>> f.close()

    Make sure that locking twice does not overwrite the old hostname:

    >>> lock = zc.lockfile.LockFile("f.lock", content_template='{hostname}')
    Traceback (most recent call last):
      ...
    LockError: Couldn't lock 'f.lock'

    >>> f = open("f.lock")
    >>> _ = f.seek(1)
    >>> f.read().rstrip()
    'myhostname'
    >>> f.close()

    >>> lock.close()
    """


class TestLogger(object):
    def __init__(self):
        self.log_entries = []

    def exception(self, msg, *args):
        self.log_entries.append((msg,) + args)


class LockFileLogEntryTestCase(unittest.TestCase):
    """Tests for logging in case of lock failure"""
    def setUp(self):
        self.here = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix='zc.lockfile-test-')
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.here)
        setupstack.rmtree(self.tmp)

    def test_log_entry(self):
        # PID and hostname are parsed and logged from lock file on failure
        test_logger = TestLogger()

        def lock(locked, before_closing):
            lock = None
            try:
                lock = zc.lockfile.LockFile('f.lock',
                                            content_template='{pid}/{hostname}')
            except Exception:
                pass
            locked.set()
            before_closing.wait()
            if lock is not None:
                lock.close()

        with patch('os.getpid', Mock(return_value=123)):
            with patch('socket.gethostname', Mock(return_value='myhostname')):
                with patch.object(zc.lockfile, 'logger', test_logger):
                    first_locked = threading.Event()
                    second_locked = threading.Event()
                    thread1 = threading.Thread(
                        target=lock, args=(first_locked, second_locked))
                    thread2 = threading.Thread(
                        target=lock, args=(second_locked, second_locked))
                    thread1.start()
                    first_locked.wait()
                    assert not test_logger.log_entries
                    thread2.start()
                    thread1.join()
                    thread2.join()
        expected = [('Error locking file %s; content: "%s%s"',
                     'f.lock', '123/myhostname', '')]
        assert test_logger.log_entries == expected, test_logger.log_entries


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocFileSuite(
        'README.txt', checker=checker,
        setUp=setupstack.setUpDirectory, tearDown=setupstack.tearDown))
    suite.addTest(doctest.DocTestSuite(
        setUp=setupstack.setUpDirectory, tearDown=setupstack.tearDown,
        checker=checker))
    # Add unittest test cases from this module
    suite.addTest(unittest.defaultTestLoader.loadTestsFromName(__name__))
    return suite
