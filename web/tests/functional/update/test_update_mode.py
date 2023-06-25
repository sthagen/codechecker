#
# -------------------------------------------------------------------------
#
#  Part of the CodeChecker project, under the Apache License v2.0 with
#  LLVM Exceptions. See LICENSE for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
# -------------------------------------------------------------------------
"""
Test update mode where multiple analysis results stored in the same run.
For the test reports were not generated by CodeChecker so metadata
information (analysis command ...) are not available/stored.
"""


import os
import shutil
import sys
import unittest
import uuid

from libtest import codechecker
from libtest import env
from libtest import project
from libtest.debug_printer import print_run_results
from libtest.thrift_client_to_db import get_all_run_results

from codechecker_api.codeCheckerDBAccess_v6.ttypes import DetectionStatus

test_dir = os.path.dirname(os.path.realpath(__file__))


class TestUpdate(unittest.TestCase):

    def setup_class(self):
        """Setup the environment for the tests. """

        global TEST_WORKSPACE
        TEST_WORKSPACE = env.get_workspace('update')

        os.environ['TEST_WORKSPACE'] = TEST_WORKSPACE

        test_config = {}

        test_project_name = uuid.uuid4().hex

        test_project_path = os.path.join(test_dir, "test_proj")

        temp_test_project_data = project.prepare(
                test_project_path, TEST_WORKSPACE)

        test_config['test_project'] = temp_test_project_data

        test_env = env.test_env(TEST_WORKSPACE)

        base_reports = os.path.join(
                temp_test_project_data['test_project_reports'], 'base')

        codechecker_cfg = {
            'suppress_file': None,
            'skip_list_file': None,
            'check_env': test_env,
            'workspace': TEST_WORKSPACE,
            'checkers': [],
            'reportdir': base_reports,
            'analyzers': ['clangsa', 'clang-tidy']
        }

        # Start or connect to the running CodeChecker server and get connection
        # details.
        print("This test uses a CodeChecker server... connecting...")
        server_access = codechecker.start_or_get_server()
        server_access['viewer_product'] = 'update'
        codechecker.add_test_package_product(server_access, TEST_WORKSPACE)

        # Extend the checker configuration with the server access.
        codechecker_cfg.update(server_access)

        ret = codechecker.store(codechecker_cfg,
                                test_project_name)
        if ret:
            sys.exit(1)
        print("Storing the base reports was succcessful.")

        codechecker_cfg['run_names'] = [test_project_name]

        test_config['codechecker_cfg'] = codechecker_cfg

        env.export_test_cfg(TEST_WORKSPACE, test_config)

    def teardown_class(self):
        """Clean up after the test."""

        # TODO: if environment variable is set keep the workspace
        # and print out the path
        global TEST_WORKSPACE

        check_env = env.import_test_cfg(TEST_WORKSPACE)[
            'codechecker_cfg']['check_env']
        codechecker.remove_test_package_product(TEST_WORKSPACE, check_env)

        print("Removing: " + TEST_WORKSPACE)
        shutil.rmtree(TEST_WORKSPACE, ignore_errors=True)

    def setup_method(self, method):
        self._test_workspace = os.environ.get('TEST_WORKSPACE')

        test_class = self.__class__.__name__
        print('Running ' + test_class + ' tests in ' + self._test_workspace)

        self._clang_to_test = env.clang_to_test()

        self._testproject_data = env.setup_test_proj_cfg(self._test_workspace)
        self.assertIsNotNone(self._testproject_data)

        self._cc_client = env.setup_viewer_client(self._test_workspace)
        self.assertIsNotNone(self._cc_client)

        # Get the run names which belong to this test
        run_names = env.get_run_names(self._test_workspace)

        runs = self._cc_client.getRunData(None, None, 0, None)

        test_runs = [run for run in runs if run.name in run_names]

        self.assertEqual(len(test_runs), 1,
                         'There should be only one run for this test.')
        self._runid = test_runs[0].runId
        self._run_name = test_runs[0].name

    def test_disable_checker(self):
        """
        The test depends on a run which was configured for update mode.
        Compared to the original test analysis in this run
        the deadcode.Deadstores checker was disabled.
        In this case the reports are marked as resolved.
        """

        run_results = get_all_run_results(self._cc_client, self._runid)

        print_run_results(run_results)

        # Get check command for the first storage.
        original_check_command = \
            self._cc_client.getCheckCommand(None, self._runid)

        self.assertEqual(original_check_command, "")

        initial_codechecker_cfg = env.import_test_cfg(
            self._test_workspace)['codechecker_cfg']

        initial_test_project_name = self._run_name

        disabled_reports = os.path.join(
            self._testproject_data['test_project_reports'], 'disabled')

        initial_codechecker_cfg['reportdir'] = disabled_reports
        ret = codechecker.store(initial_codechecker_cfg,
                                initial_test_project_name)
        if ret:
            sys.exit(1)

        # Get the results to compare.
        updated_results = get_all_run_results(self._cc_client, self._runid)

        for report in updated_results:
            self.assertEqual(report.detectionStatus, DetectionStatus.RESOLVED)
