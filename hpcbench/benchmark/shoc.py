"""The Scalable HeterOgeneous Computing (SHOC) Benchmark Suite
   https://github.com/vetter/shoc
"""
import re

from cached_property import cached_property

from hpcbench.api import (
    Benchmark,
    Metrics,
    MetricsExtractor,
)
from hpcbench.toolbox.process import find_executable


class SHOCExtractor(MetricsExtractor):
    METRICS = dict(
        h2d_bw=Metrics.MegaBytesPerSecond,
        d2h_bw=Metrics.MegaBytesPerSecond,
        flops_dp=Metrics.Flops,
        flops_sp=Metrics.Flops,
        gmem_readbw=Metrics.MegaBytesPerSecond,
        gmem_writebw=Metrics.MegaBytesPerSecond,
        lmem_readbw=Metrics.MegaBytesPerSecond,
        lmem_writebw=Metrics.MegaBytesPerSecond,
        sgemm_n=Metrics.Flops,
        dgemm_n=Metrics.Flops,
    )
    METRICS_NAMES = set(METRICS)
    EXPR = re.compile(r'[\w]+\:\s+(\d*\.?\d+)')
    MATCHING_LINES = {
        'result for bspeed_download:': 'h2d_bw',
        'result for bspeed_readback:': 'd2h_bw',
        'result for maxspflops:': 'flops_sp',
        'result for maxdpflops:': 'flops_dp',
        'result for gmem_readbw:': 'gmem_readbw',
        'result for gmem_writebw:': 'gmem_writebw',
        'result for lmem_readbw:': 'lmem_readbw',
        'result for lmem_writebw:': 'lmem_writebw',
        'result for sgemm_n:': 'sgemm_n',
        'result for dgemm_n:': 'dgemm_n',
    }

    @property
    def check_metrics(self):
        return False  # all metrics are not mandatory

    @property
    def metrics(self):
        """ The metrics to be extracted.
            This property can not be replaced, but can be mutated as required
        """
        return SHOCExtractor.METRICS

    @classmethod
    def extract_value(cls, line):
        value = cls.EXPR.search(line).group(1)
        return float(value)

    def extract_metrics(self, outdir, metas):
        metrics = {}
        # parse stdout and extract desired metrics
        with open(self.stdout(outdir)) as istr:
            for line in istr:
                for match, attr in SHOCExtractor.MATCHING_LINES.items():
                    if line.find(match) != -1:
                        metrics[attr] = self.extract_value(line)
                        break
        return metrics


class SHOC(Benchmark):
    """Benchmark wrapper for the SHOCbench utility
    """
    DEFAULT_DEVICE = '0'
    DEFAULT_EXECUTABLE = 'shocdriver'
    DEFAULT_OPTIONS = ['-s', '3']
    DEFAULT_BENCHMARK = "all"
    CATEGORY = 'gpu'

    def __init__(self):
        # locate `shocdriver` executable
        super(SHOC, self).__init__(
            attributes=dict(
                benchmark=SHOC.DEFAULT_BENCHMARK,
                device=SHOC.DEFAULT_DEVICE,
                executable=SHOC.DEFAULT_EXECUTABLE,
                options=SHOC.DEFAULT_OPTIONS,
            )
        )
    name = 'shoc'

    description = "Multiple benchmark of the GPU."

    @cached_property
    def executable(self):
        """Get absolute path to executable
        """
        return find_executable(self.attributes['executable'])

    def execution_matrix(self, context):
        del context  # unused
        yield dict(
            category=SHOC.CATEGORY,
            command=[self.executable, '-cuda'] + self.attributes['options'],
            metas=dict(
                benchmark=self.attributes['benchmark']
            ),
            environment=dict(
                CUDA_VISIBLE_DEVICES=str(self.attributes['device']),
            ),
        )

    @cached_property
    def metrics_extractors(self):
        return SHOCExtractor()
