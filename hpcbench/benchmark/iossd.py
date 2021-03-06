"""IO SSD Bandwidth measurement using linux tool
   WRITE: sync; dd if=/dev/zero of=tempfile bs=1M count=1024; sync
   FLASH THE CASH: sudo /sbin/sysctl -w vm.drop_caches=3
   READ: dd if=tempfile of=/dev/null bs=1M count=1024

"""
from __future__ import division

import os
import re
import stat
import textwrap

from cached_property import cached_property

from hpcbench.api import (
    Benchmark,
    Metrics,
    MetricsExtractor,
)


class IOSSDExtractor(MetricsExtractor):
    """Ignore stdout until this line"""
    STDOUT_IGNORE_PRIOR = "1024+0 records out"
    METRICS = dict(
        bandwidth=Metrics.MegaBytesPerSecond,
    )
    METRICS_NAMES = set(METRICS)

    BANDWIDTH_OSX_RE = \
        re.compile(r'^\s*\d+\s\w+\s\w+\s\w+\s\d*\.?\d+\s\w+\s[(](\d+)')

    def __init__(self):
        self.s_bandwidth = set()

    @property
    def metrics(self):
        """ The metrics to be extracted.
            This property can not be replaced, but can be mutated as required
        """
        return self.METRICS

    def extract_metrics(self, outdir, metas):
        # parse stdout and extract desired metrics
        with open(self.stderr(outdir)) as istr:
            for line in istr:
                if line.strip() == self.STDOUT_IGNORE_PRIOR:
                    break
            for line in istr:
                self.process_line(line.strip())
        return self.epilog()

    def process_line(self, line):
        search = self.BANDWIDTH_OSX_RE.search(line)
        if search:
            self.s_bandwidth.add(float(int(search.group(1)) / (1024 * 1024)))
        else:
            # Linux?
            tokens = line.rsplit('s, ', 2)
            if len(tokens) == 2:
                value, unit = tokens[1].split(' ', 2)
                value = float(value)
                bandwidth = IOSSDExtractor.parse_bandwidth_linux(
                    value, unit
                )
                self.s_bandwidth.add(bandwidth)

    @classmethod
    def parse_bandwidth_linux(cls, value, unit):
        if unit == 'bytes/s':
            value /= 1024
            unit = 'KB/s'
        if unit == 'KB/s':
            value /= 1024
            unit = 'MB/s'
        if unit == 'MB/s':
            return value
        if unit == 'GB/s':
            return value * 1024
        raise Exception('Unexpected unit: "{}"'.format(unit))

    def epilog(self):
        return dict(bandwidth=max(self.s_bandwidth))


class IOSSDWriteExtractor(IOSSDExtractor):
    pass


class IOSSDReadExtractor(IOSSDExtractor):
    pass


class IOSSD(Benchmark):
    """Benchmark wrapper for the SSDIObench utility
    """

    name = 'iossd'

    description = "Provides SSD bandwidth"

    SSD_READ = 'Read'
    SSD_WRITE = 'Write'
    DEFAULT_CATEGORIES = [
        SSD_WRITE,
        SSD_READ,
    ]

    SCRIPT_NAME = 'iossd.sh'
    SCRIPT = textwrap.dedent("""\
    #!/bin/bash -e
    #mac: 1m, linux 1M

    case `uname -s` in
        Darwin)
            MB=m
            WCONV=sync
            ;;
        *)
            MB=M
            WCONV=fdatasync
    esac

    function benchmark_write {
        echo "Writing benchmark"
        sync; dd conv=$WCONV if=/dev/zero of=tempfile bs=1$MB count=1024; sync
    }

    function benchmark_read {
        echo "Reading benchmark"
        # flash the ddr to be sure we are using the IO
        # /sbin/sysctl -w vm.drop_caches=3;
        dd if=tempfile of=/dev/null bs=1$MB count=1024
    }

    if [ $1 = "Write" ]; then
        benchmark_write
    else
        benchmark_write >/dev/null 2>&1
        sudo sysctl vm.drop_caches=3 >/dev/null 2>&1
        benchmark_read
    fi
    rm -f tempfile
    """)

    def __init__(self):
        super(IOSSD, self).__init__(
            attributes=dict(
                categories=[
                    IOSSD.SSD_WRITE,
                    IOSSD.SSD_READ,
                ],
            )
        )

    def execution_matrix(self, context):
        del context  # unused
        for category in self.attributes['categories']:
            yield dict(
                category=category,
                command=['./' + IOSSD.SCRIPT_NAME, category],
            )

    @cached_property
    def metrics_extractors(self):
        return {
            IOSSD.SSD_READ: IOSSDReadExtractor(),
            IOSSD.SSD_WRITE: IOSSDWriteExtractor(),
        }

    def pre_execute(self, execution):
        del execution  # unused
        with open(IOSSD.SCRIPT_NAME, 'w') as ostr:
            ostr.write(IOSSD.SCRIPT)
        st = os.stat(IOSSD.SCRIPT_NAME)
        os.chmod(IOSSD.SCRIPT_NAME, st.st_mode | stat.S_IEXEC)
