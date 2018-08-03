import os
import shutil
import tempfile
import unittest

from avocado.utils import process

from .. import AVOCADO, BASEDIR


class GDBPluginTest(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='avocado_' + __name__)

    def test_gdb_prerun_commands(self):
        os.chdir(BASEDIR)
        cmd_line = ('%s run --job-results-dir %s --sysinfo=off '
                    '--gdb-prerun-commands=/dev/null passtest.py'
                    % (AVOCADO, self.tmpdir))
        process.run(cmd_line)

    def test_gdb_multiple_prerun_commands(self):
        os.chdir(BASEDIR)
        cmd_line = ('%s run --job-results-dir %s --sysinfo=off '
                    '--gdb-prerun-commands=/dev/null '
                    '--gdb-prerun-commands=foo:/dev/null passtest.py'
                    % (AVOCADO, self.tmpdir))
        process.run(cmd_line)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)


if __name__ == '__main__':
    unittest.main()
