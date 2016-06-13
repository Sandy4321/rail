#!/usr/bin/env python
"""
tools.py
Part of Dooplicity framework

Includes a class for iterating through streams easily and a few other tools.

The functions which() and is_exe() was taken from
http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
and is not covered under the license below.

Licensed under the MIT License except where otherwise noted:

Copyright (c) 2014 Abhi Nellore and Ben Langmead.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

from itertools import groupby
import threading
import signal
import subprocess
import gzip
import contextlib
from collections import defaultdict
import time
from traceback import format_exc
import os
import tempfile

@contextlib.contextmanager
def cd(dir_name):
    """ Changes directory in a context only. Borrowed from AWS CLI code.

        This is also in tools.py, but IPython has trouble with it.

        dir_name: directory name to which to change

        No return value.
    """
    if dir_name is None:
        yield
        return
    original_dir = os.getcwd()
    os.chdir(dir_name)
    try:
        yield
    finally:
        os.chdir(original_dir)

class KeepAlive(threading.Thread):
    """ Writes Hadoop status messages to avert task termination. """
    def __init__(self, status_stream, period=120):
        """
            status_stream: where to write status messages
            period: number of seconds between successive status messages
        """
        super(KeepAlive, self).__init__()
        self.period = period
        self.status_stream = status_stream
        # Kills thread when script is finished
        self.daemon = True

    def run(self):
        import time
        while True:
            print >>self.status_stream, ('%s | writing keep alive message to '
                                         'status stream'
                                    % time.strftime('%l:%M%p %Z on %b %d, %Y'))
            self.status_stream.flush()
            print >>self.status_stream, '\nreporter:status:alive'
            self.status_stream.flush()
            print >>self.status_stream, (
                            '%s | wrote keep alive message to status stream'
                                % time.strftime('%l:%M%p %Z on %b %d, %Y')
                        )
            self.status_stream.flush()
            time.sleep(self.period)

def is_exe(fpath):
    """ Tests whether a file is executable.

        fpath: path to file

        Return value: True iff file exists and is executable.
    """
    return os.path.exists(fpath) and os.access(fpath, os.X_OK)

def which(program):
    """ Tests whether an executable is in PATH.

        program: executable to search for

        Return value: path to executable or None if the executable is not
            found.
    """
    def ext_candidates(fpath):
        yield fpath
        for ext in os.environ.get("PATHEXT", "").split(os.pathsep):
            yield fpath + ext

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            for candidate in ext_candidates(exe_file):
                if is_exe(candidate):
                    return candidate
    return None

def sig_handler(signum, frame):
    """ Helper function for register_cleanup that's called on signal. """
    import sys
    sys.exit(0)

def register_cleanup(handler, *args, **kwargs):
    """ Registers cleanup on normal and signal-induced program termination.

        Executes previously registered handler as well as new handler.

        handler: function to execute on program termination
        args: named arguments of handler
        kwargs includes keyword args of handler as well as: 
            signals_to_handle: list of signals to handle, e.g. [signal.SIGTERM,
                signal.SIGHUP]

        No return value.
    """
    if 'signals_to_handle' in kwargs:
        signals_to_handle = kwargs['signals_to_handle']
        del kwargs['signals_to_handle']
    else:
        signals_to_handle = [signal.SIGTERM, signal.SIGHUP]
    from atexit import register
    register(handler, *args, **kwargs)
    old_handlers = [signal.signal(a_signal, sig_handler)
                    for a_signal in signals_to_handle]
    for i, old_handler in enumerate(old_handlers):
        if (old_handler != signal.SIG_DFL) and (old_handler != sig_handler):
            def new_handler(signum, frame):
                try:
                    sig_handler(signum, frame)
                finally:
                    old_handler(signum, frame)
        else:
            new_handler = sig_handler
        signal.signal(signals_to_handle[i], new_handler)

def path_join(unix, *args):
    """ Performs UNIX-like os.path.joins on Windows systems if necessary.

        unix: True iff UNIX-like path join should be performed; else False

        Return value: joined path
    """
    args_list = []
    if unix:
        for i in xrange(len(args) - 1):
            try:
                if args[i][-1] != '/':
                    args_list.append(args[i] + '/')
            except IndexError:
                # Empty element
                pass
        args_list.append(args[-1])
        return ''.join(args_list)
    else:
        return os.path.join(*args)

@contextlib.contextmanager
def xopen(gzipped, *args):
    """ Passes args on to the appropriate opener, gzip or regular.

        In compressed mode, functionality almost mimics gzip.open,
        but uses gzip at command line.

        As of PyPy 2.5, gzip.py appears to leak memory when writing to
        a file object created with gzip.open().

        gzipped: True iff gzip.open() should be used to open rather than
            open(); False iff open() should be used; None if input should be
            read and guessed; '-' if writing to stdout
        *args: unnamed arguments to pass

        Yield value: file object
    """
    import sys
    if gzipped == '-':
        fh = sys.stdout
    else:
        if not args:
            raise IOError('Must provide filename')
        import gzip
        if gzipped is None:
            with open(args[0], 'rb') as binary_input_stream:
                # Check for magic number
                if binary_input_stream.read(2) == '\x1f\x8b':
                    gzipped = True
                else:
                    gzipped = False
        if gzipped:
            try:
                mode = args[1]
            except IndexError:
                mode = 'rb'
            if 'r' in mode:
                # Be forgiving of gzips that end unexpectedly
                old_read_eof = gzip.GzipFile._read_eof
                gzip.GzipFile._read_eof = lambda *args, **kwargs: None
                fh = gzip.open(*args)
            elif 'w' in mode or 'a' in mode:
                try:
                    compresslevel = int(args[2])
                except IndexError:
                    compresslevel = 9
                if 'w' in mode:
                    output_stream = open(args[0], 'wb')
                else:
                    output_stream = open(args[0], 'ab')
                gzip_process = subprocess.Popen(['gzip',
                                                    '-%d' % compresslevel],
                                                    bufsize=-1,
                                                    stdin=subprocess.PIPE,
                                                    stdout=output_stream)
                fh = gzip_process.stdin
            else:
                raise IOError('Mode ' + mode + ' not supported')
        else:
            fh = open(*args)
    try:
        yield fh
    finally:
        if fh is not sys.stdout:
            fh.close()
        if 'gzip_process' in locals():
            gzip_process.wait()
        if 'output_stream' in locals():
            output_stream.close()
        if 'old_read_eof' in locals():
            gzip.GzipFile._read_eof = old_read_eof

def make_temp_dir(scratch=None):
    """ Creates temporary directory in some scratch directory.

        Handles case where scratch directory does not exist.

        scratch: directory in which to create temporary directory

        Return value: path to temporary directory
    """
    if scratch:
        try:
            os.makedirs(scratch)
        except OSError:
            if not os.path.isdir(scratch):
                raise
        return tempfile.mkdtemp(dir=scratch)
    return tempfile.mkdtemp()

def make_temp_dir_and_register_cleanup(scratch=None):
    """ Creates temporary directory and registers its cleanup.

        Handles case where scratch directory does not exist.

        scratch: directory in which to create temporary directory

        Return value: path to temporary directory
    """
    import shutil
    dir_to_cleanup = make_temp_dir(scratch)
    register_cleanup(shutil.rmtree, dir_to_cleanup,
                        ignore_errors=True)
    return dir_to_cleanup

def engine_string_from_list(id_list):
    """ Pretty-prints list of engine IDs.

        id_list: list of engine IDs

        Return value: string condensing list of engine IDs
    """
    id_list = sorted(set(id_list))
    to_print = []
    if not id_list: return ''
    last_id = id_list[0]
    streak = 0
    for engine_id in id_list[1:]:
        if engine_id == last_id + 1:
            streak += 1
        else:
            if streak > 1:
                to_print.append('%d-%d' % (last_id - streak, last_id))
            elif streak == 1:
                to_print.append('%d, %d' % (last_id - 1, last_id))
            else:
                to_print.append('%d' % last_id)
            streak = 0
        last_id = engine_id
    if streak > 1:
        to_print.append('%d-%d' % (last_id - streak, last_id))
    elif streak == 1:
        to_print.append('%d, %d' % (last_id - 1, last_id))
    else:
        to_print.append('%d' % last_id)
    if len(to_print) > 1:
        to_print[-1] = ' '.join(['and', to_print[-1]])
    return ', '.join(to_print)

def apply_async_with_errors(rc, ids, function_to_apply, *args, **kwargs):
    """ apply_async() that cleanly outputs engines responsible for exceptions.

        For IPython parallel mode.

        WARNING: in general, this method requires Dill for pickling.
        See https://pypi.python.org/pypi/dill
        and http://matthewrocklin.com/blog/work/2013/12/05
        /Parallelism-and-Serialization/

        rc: IPython parallel Client object
        ids: IDs of engines where function_to_apply should be run
        function_to_apply: function to run across engines. If this is a
            dictionary whose keys are exactly the engine IDs, each engine ID's
            value is regarded as a distinct function corresponding to the key.
        *args: contains unnamed arguments of function_to_apply. If a given
            argument is a dictionary whose keys are exactly engine IDs,
            each engine ID's value is regarded as a distinct argument
            corresponding to the key. The same goes for kwargs.
        **kwargs: includes --
            errors_to_ignore: list of exceptions to ignore, where each
               exception is either a string or a tuple (exception name
                as a string, text to find in exception message)
            message: message to append to exception raised
            and named arguments of function_to_apply
            dict_format: if True, returns engine-result key-value dictionary;
                if False, returns list of results

        Return value: list of AsyncResults, one for each engine spanned by
            direct_view
    """
    if 'dict_format' not in kwargs:
        dict_format = False
    else:
        dict_format = kwargs['dict_format']
        del kwargs['dict_format']
    if not ids:
        if dict_format:
            return {}
        else:
            return []
    if 'errors_to_ignore' not in kwargs:
        errors_to_ignore = []
    else:
        errors_to_ignore = kwargs['errors_to_ignore']
        del kwargs['errors_to_ignore']
    if 'message' not in kwargs:
        message = None
    else:
        message = kwargs['message']
        del kwargs['message']
    id_set = set(ids)
    if not (isinstance(function_to_apply, dict)
            and set(function_to_apply.keys()).issubset(id_set)):
        function_to_apply_holder = function_to_apply
        function_to_apply = {}
        for i in ids:
            function_to_apply[i] = function_to_apply_holder
    new_args = defaultdict(list)
    for arg in args:
        if (isinstance(arg, dict)
            and set(arg.keys()).issubset(id_set)):
            for i in arg:
                new_args[i].append(arg[i])
        else:
            for i in ids:
                new_args[i].append(arg)
    new_kwargs = defaultdict(dict)
    for kwarg in kwargs:
        if (isinstance(kwargs[kwarg], dict)
            and set(kwargs[kwarg].keys()).issubset(id_set)):
            for i in ids:
                new_kwargs[i][kwarg] = kwargs[kwarg][i]
        else:
            for i in ids:
                new_kwargs[i][kwarg] = kwargs[kwarg]
    asyncresults = []
    ids_not_to_return = set()
    for i in ids:
        asyncresults.append(
                rc[i].apply_async(
                    function_to_apply[i],*new_args[i],**new_kwargs[i]
                )
            )
    while any([not asyncresult.ready() for asyncresult in asyncresults]):
        time.sleep(1e-1)
    asyncexceptions = defaultdict(set)
    for asyncresult in asyncresults:
        try:
            asyncdict = asyncresult.get_dict()
        except Exception as e:
            exc_to_report = format_exc()
            proceed = False
            for error_to_ignore in errors_to_ignore:
                if isinstance(error_to_ignore, tuple):
                    error_to_ignore, text_to_find = (
                            error_to_ignore
                        )
                else:
                    text_to_find = None
                if error_to_ignore in exc_to_report and (
                        text_to_find is None or
                        text_to_find in exc_to_report
                    ):
                    proceed = True
                    ids_not_to_return.add(asyncresult.metadata['engine_id'])
            if not proceed:
                asyncexceptions[format_exc()].add(
                        asyncresult.metadata['engine_id']
                    )
    if asyncexceptions:
        runtimeerror_message = []
        for exc in asyncexceptions:
            runtimeerror_message.extend(
                    ['Engine(s) %s report(s) the following exception.'
                        % engine_string_from_list(
                              list(asyncexceptions[exc])
                            ),
                     exc]
                 )
        raise RuntimeError('\n'.join(runtimeerror_message
                            + ([message] if message else [])))
    # Return only those results for which there is no failure
    if not dict_format:
        return [asyncresult.get() for asyncresult in asyncresults
                    if asyncresult.metadata['engine_id']
                    not in ids_not_to_return]
    to_return = {}
    for i, asyncresult in enumerate(asyncresults):
        if asyncresult.metadata['engine_id'] not in ids_not_to_return:
            to_return[asyncresult.metadata['engine_id']] = asyncresult.get()
    return to_return

class dlist(object):
    """ List data type that spills to disk if a memlimit is reached.

        Keeping memory usage low can be important in Hadoop, so this class
        is included in Dooplicity.

        Random access is not currently permitted. The list should properly
        be used by appending all elements, then iterating through them to
        read them.
    """
    def __init__(self, limit=5000000):
        """
            limit: maximum number of elements allowed in list before
                spilling to disk
        """
        self.mem_list = []
        self.disk_stream = None
        self.limit = limit

    def __enter__(self):
        return self

    def __iter__(self):
        """ Iterates through list.

            NOTE THAT seek to beginning of file is performed if some of the
            list is not in memory!
        """
        for item in self.mem_list:
            yield item
        if self.disk_stream is not None:
            self.disk_stream.flush()
            self.disk_stream.seek(0)
            for line in self.disk_stream:
                yield line.strip()

    def append(self, item):
        """ Appends item to list. Only strings are permitted right now.

            item: string to append
        """
        if type(item) is not str:
            raise TypeError('An item appended to a dlist must be a string.')
        if self.disk_stream is None:
            if len(self.mem_list) < self.limit:
                self.mem_list.append(item)
            else:
                # Open new temporary file
                import tempfile
                self.disk_stream = tempfile.TemporaryFile()
                print >>self.disk_stream, item
        else:
            print >>self.disk_stream, item

    def tear_down(self):
        if self.disk_stream is not None:
            self.disk_stream.close()

    def __exit__(self, type, value, traceback):
        self.tear_down()
 
class xstream(object):
    """ Permits Pythonic iteration through partitioned/sorted input streams.

        All iterators are implemented as generators. Could have subclassed
        itertools.groupby here; however, implementation of itertools.groupby
        may change from version to version of Python. Implementation is thus
        just based on itertools.groupby from
        https://docs.python.org/2/library/itertools.html .

        Usage: for key, xpartition in xstream(hadoop_stream):
                   for value in xpartition:
                        <code goes here>

        Each of key and value above is a tuple of strings.

        Properties
        -------------
        key: key tuple that denotes current partition; this is an attribute
            of both an xstream. None when no lines have been read yet.
        value: tuple that denotes current value. None when no lines have been
            read yet.

        Init vars
        -------------
        input_stream: where to find input lines
        key_fields: the first "key_fields" fields from an input line are
            considered the key denoting a partition
        separator: delimiter separating fields from each input line
        skip_duplicates: skip any duplicate lines that may follow a line
    """
    @staticmethod
    def stream_iterator(
            input_stream,
            separator='\t',
            skip_duplicates=False
        ):
        if skip_duplicates:
            for line, _ in groupby(input_stream):
                yield tuple(line.strip().split(separator))
        else:
            for line in input_stream:
                yield tuple(line.strip().split(separator))

    def __init__(
            self, 
            input_stream,
            key_fields=1,
            separator='\t',
            skip_duplicates=False
        ):
        self._key_fields = key_fields
        self.it = self.stream_iterator(
                        input_stream,
                        separator=separator,
                        skip_duplicates=skip_duplicates
                    )
        self.tgtkey = self.currkey = self.currvalue = object()

    def __iter__(self):
        return self

    def next(self):
        while self.currkey == self.tgtkey:
            self.currvalue = next(self.it)    # Exit on StopIteration
            self.currkey = self.currvalue[:self._key_fields]
        self.tgtkey = self.currkey
        return self.currkey, self._grouper(self.tgtkey)

    def _grouper(self, tgtkey):
        while self.currkey == tgtkey:
            yield self.currvalue[self._key_fields:]
            self.currvalue = next(self.it)    # Exit on StopIteration
            self.currkey = self.currvalue[:self._key_fields]

if __name__ == '__main__':
    # Run unit tests
    import unittest
    import os
    import shutil

    class TestXstream(unittest.TestCase):
        """ Tests xstream class. """
        def setUp(self):
            # Set up temporary directory
            self.temp_dir_path = tempfile.mkdtemp()
            self.input_file = os.path.join(self.temp_dir_path, 'hadoop.temp')

        def test_partitioning_1(self):
            """ Fails if input data isn't partitioned properly. """
            with open(self.input_file, 'w') as input_stream:
                # Create some fake data with two key fields
                input_stream.write(
                        'chr1\t1\ta\t20\t90\n'
                        'chr1\t1\ti\t10\t50\n'
                        'chr1\t1\ti\t30\t70\n'
                        'chr1\t1\ti\t75\t101\n'
                        'chr3\t2\ti\t90\t1300\n'
                        'chr1\t2\ti\t90\t1300\n'
                        'chr1\t2\ti\t91\t101\n'
                    )
            with open(self.input_file) as input_stream:
                partitions = {}
                for key, xpartition in xstream(input_stream, 2):
                    partitions[key] = []
                    for value in xpartition:
                        partitions[key].append(value)
            self.assertEqual(partitions, 
                    {
                        ('chr1', '1') : [
                                            ('a', '20', '90'),
                                            ('i', '10', '50'),
                                            ('i', '30', '70'),
                                            ('i', '75', '101')
                                        ],
                        ('chr3', '2') : [
                                            ('i', '90', '1300')
                                        ],
                        ('chr1', '2') : [
                                            ('i', '90', '1300'),
                                            ('i', '91', '101')
                                        ]
                    }
                )

        def test_partitioning_2(self):
            """ Fails if input data isn't partitioned properly. """
            with open(self.input_file, 'w') as input_stream:
                # Create some fake data with two key fields
                input_stream.write(
                        '1\tA\n'
                        '1\tB\n'
                        '1\tC\n'
                        '1\tD\n'
                        '1\tE\n'
                        '1\tF\n'
                        '2\tG\n'
                        '3\tH\n'
                        '3\tI\n'
                        '3\tJ\n'
                    )
            with open(self.input_file) as input_stream:
                partitions = {}
                for key, xpartition in xstream(input_stream, 1):
                    partitions[key] = []
                    for value in xpartition:
                        partitions[key].append(value)
            self.assertEqual(partitions, 
                    {
                        ('1',) : [('A',), ('B',), ('C',),
                                  ('D',), ('E',), ('F',)],
                        ('2',) : [('G',)],
                        ('3',) : [('H',), ('I',), ('J',)]
                    }
                )

        def test_duplicate_line_skipping(self):
            """ Fails if duplicate lines aren't skipped. """
            with open(self.input_file, 'w') as input_stream:
                # Create some fake data with two key fields
                input_stream.write(
                        'chr1\t1\ta\t20\t90\n'
                        'chr1\t1\ta\t20\t90\n'
                        'chr1\t1\ti\t10\t50\n'
                        'chr1\t1\ti\t30\t70\n'
                        'chr1\t1\ti\t30\t70\n'
                        'chr1\t1\ti\t30\t70\n'
                        'chr1\t1\ti\t30\t70\n'
                        'chr1\t1\ti\t75\t101\n'
                        'chr1\t1\ti\t75\t101\n'
                        'chr1\t2\ti\t90\t1300\n'
                        'chr1\t2\ti\t91\t101\n'
                    )
            with open(self.input_file) as input_stream:
                output = [(key, value) for key, xpartition
                            in xstream(input_stream, 2, skip_duplicates=True)
                            for value in xpartition]
            self.assertEqual(output,
                    [(('chr1', '1'), ('a', '20', '90')),
                     (('chr1', '1'), ('i', '10', '50')),
                     (('chr1', '1'), ('i', '30', '70')),
                     (('chr1', '1'), ('i', '75', '101')),
                     (('chr1', '2'), ('i', '90', '1300')),
                     (('chr1', '2'), ('i', '91', '101'))]
                )

        def test_empty_input(self):
            """ Fails if it fails. """
            with open(self.input_file, 'w') as input_stream:
                pass
            with open(self.input_file) as input_stream:
                for key, xpartition in xstream(input_stream, 1):
                    for value in xpartition:
                        pass

        def tearDown(self):
            # Kill temporary directory
            shutil.rmtree(self.temp_dir_path)

    class TestXopen(unittest.TestCase):
        """ Tests xopen function. """
        def setUp(self):
            # Set up temporary directory
            self.temp_dir_path = tempfile.mkdtemp()
            self.python_file = os.path.join(self.temp_dir_path, 'py.gz')
            self.unix_file = os.path.join(self.temp_dir_path, 'unix.gz')

        def test_write_consistency(self):
            """ Fails if xopen compressed write disagrees with gzip.open. """
            data = os.urandom(128 * 1024) 
            with gzip.open(self.python_file, 'w') as python_stream:
                python_stream.write(data)
            with xopen(True, self.unix_file, 'w') as unix_stream:
                unix_stream.write(data)
            output = subprocess.check_output(
                            'diff <(gzip -cd %s) <(gzip -cd %s)'
                            % (self.python_file, self.unix_file),
                            shell=True, executable='/bin/bash'
                        )
            self.assertEqual(output, '')

        def test_single_line_read(self):
            """ Raises exception if single line can't be read from file. """
            with xopen(True, self.unix_file, 'w') as unix_stream:
                print >>unix_stream, 'first line'
                print >>unix_stream, 'second line'
            with xopen(None, self.unix_file, 'r') as unix_stream:
                first_line = unix_stream.readline()
            self.assertEqual(first_line.strip(), 'first line')

        def test_append(self):
            """ Raises exception if appending to existing gz doesn't work. """
            with xopen(True, self.unix_file, 'w') as unix_stream:
                print >>unix_stream, 'first line'
            with xopen(True, self.unix_file, 'a') as unix_stream:
                print >>unix_stream, 'second line'
            with xopen(None, self.unix_file, 'r') as unix_stream:
                first_line = unix_stream.readline().strip()
                second_line = unix_stream.readline().strip()
                third_line = unix_stream.readline()
            self.assertEqual(first_line.strip(), 'first line')
            self.assertEqual(second_line.strip(), 'second line')
            self.assertEqual(third_line, '')

        def tearDown(self):
            # Kill temporary directory
            shutil.rmtree(self.temp_dir_path)

    unittest.main()
