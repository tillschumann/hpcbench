from abc import ABCMeta, abstractmethod
from collections import Mapping
import inspect
import logging
import os
import os.path as osp
import shutil

from cached_property import cached_property
from six import (
    assertCountEqual,
    with_metaclass,
)
import yaml

from hpcbench.api import (
    Benchmark,
    ExecutionContext,
    MetricsExtractor,
)
from hpcbench.driver import (
    MetricsDriver,
    YAML_REPORT_FILE,
)
from hpcbench.toolbox.collections_ext import dict_merge
from hpcbench.toolbox.contextlib_ext import (
    mkdtemp,
    pushd,
)

LOGGER = logging.getLogger(__name__)


class AbstractBenchmarkTest(with_metaclass(ABCMeta, object)):
    @abstractmethod
    def get_benchmark_clazz(self):
        """
        :return: Benchmark class to test
        :rtype: subclass of ``hpcbench.api.Benchmark``
        """
        raise NotImplementedError

    @abstractmethod
    def get_benchmark_categories(self):
        """
        :return: List of categories to tests
        :rtype: string list
        """
        raise NotImplementedError

    @abstractmethod
    def get_expected_metrics(self, category):
        """
        :return: metrics extracted from the sample output
        :rtype: dictionary name -> value
        """
        raise NotImplementedError

    @property
    def attributes(self):
        """
        :return: attributes to merge on the Benchmark instance
        :rtype: dictionary
        """
        return {}

    @property
    def check_executable_availability(self):
        """
        :return: True if executables used in execution matrix should
        be checked, False otherwise.
        """
        return False

    @cached_property
    def logger(self):
        return LOGGER.getChild(self.get_benchmark_clazz().name)

    def create_sample_run(self, category):
        pyfile = inspect.getfile(self.__class__)
        prefix = osp.splitext(osp.basename(pyfile))[0] + '.' + category + '.'
        test_dir = osp.dirname(pyfile)
        for file_ in os.listdir(test_dir):
            if file_.startswith(prefix):
                src_file = osp.join(test_dir, file_)
                dest = file_[len(prefix):] + '.txt'
                if osp.isfile(src_file):
                    self.logger.info('using file: %s', src_file)
                    shutil.copy(src_file, dest)

    def test_executable_availability(self):
        if not self.check_executable_availability:
            return
        for execution in self.execution_matrix:
            command = execution['command']
            executable = command[0]
            self.assertTrue(osp.isfile(executable), executable + ' is a file')
            self.assertTrue(os.access(executable, os.X_OK),
                            executable + ' is executable')

    def test_class_has_name(self):
        clazz_name = self.get_benchmark_clazz().name
        assert isinstance(clazz_name, str)
        assert clazz_name  # Not None or empty

    def test_class_is_registered(self):
        clazz = self.get_benchmark_clazz()
        assert issubclass(clazz, Benchmark)
        # We could access the list of subclasses, but bit horrible
        # clazz in Benchmark.__subclasses__

    def test_metrics_extraction(self):
        for category in self.get_benchmark_categories():
            self.check_category_metrics(category)

    def check_category_metrics(self, category):
        self.logger.info('testing metrics of category %s', category)
        self.maxDiff = None
        with mkdtemp() as top_dir, pushd(top_dir):
            with open(YAML_REPORT_FILE, 'w') as ostr:
                yaml.dump(
                    dict(
                        children=['sample-run'],
                        category=category
                    ),
                    ostr
                )
            with pushd('sample-run'):
                self.create_sample_run(category)
                clazz = self.get_benchmark_clazz()
                benchmark = clazz()
                with open(YAML_REPORT_FILE, 'w') as ostr:
                    yaml.dump(dict(category=category), ostr)
                md = MetricsDriver('test-category', benchmark)
                report = md()
                parsed_metrics = report.get('metrics', {})
                expected_metrics = self.get_expected_metrics(category)
                self.assertEqual(parsed_metrics, expected_metrics)

    def test_has_description(self):
        clazz = self.get_benchmark_clazz()
        assert isinstance(clazz.description, str)

    @property
    def execution_matrix(self):
        clazz = self.get_benchmark_clazz()
        benchmark = clazz()
        dict_merge(
            benchmark.attributes,
            self.attributes
        )
        return list(benchmark.execution_matrix(self.exec_context))

    @property
    def exec_context(self):
        return ExecutionContext(
            node='localhost',
            tag='*',
            nodes=['localhost'],
            logger=self.logger,
        )

    @property
    def expected_execution_matrix(self):
        pass

    def test_execution_matrix(self):
        exec_matrix = self.execution_matrix
        assert isinstance(exec_matrix, list)

        expected_exec_matrix = self.expected_execution_matrix
        if expected_exec_matrix is not None:
            assertCountEqual(self, exec_matrix, expected_exec_matrix)

        run_keys = {
            'category', 'command', 'metas', 'environment', 'srun_nodes'
        }
        for runs in exec_matrix:
            assert isinstance(runs, dict)
            assert 'category' in runs
            assert isinstance(runs['category'], str)
            assert runs['category']
            assert 'command' in runs
            assert isinstance(runs['command'], list)
            assert runs['command']
            for arg in runs['command']:
                assert isinstance(arg, str)
            keys = set(runs.keys())
            assert keys.issubset(run_keys)

    def test_metrics_extractors(self):
        clazz = self.get_benchmark_clazz()
        benchmark = clazz()
        all_extractors = benchmark.metrics_extractors
        assert isinstance(all_extractors, (Mapping, list, MetricsExtractor))

        def _check_extractor(exts):
            if not isinstance(exts, list):
                exts = [exts]
            for ext in exts:
                assert isinstance(ext, MetricsExtractor)

        if isinstance(all_extractors, Mapping):
            for name, extractors in all_extractors.items():
                assert isinstance(name, str)
                assert name
                _check_extractor(extractors)
        else:
            _check_extractor(all_extractors)
