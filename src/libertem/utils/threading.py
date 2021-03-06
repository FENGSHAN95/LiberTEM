import logging
from contextlib import contextmanager

import threadpoolctl
try:
    import pyfftw
except ImportError:
    pyfftw = None
import numba


log = logging.getLogger(__name__)


if pyfftw:
    @contextmanager
    def set_fftw_threads(n):
        pyfftw_threads = pyfftw.config.NUM_THREADS
        try:
            pyfftw.config.NUM_THREADS = n
            yield
        finally:
            pyfftw.config.NUM_THREADS = pyfftw_threads
else:
    @contextmanager
    def set_fftw_threads(n):
        yield


@contextmanager
def set_numba_threads(n):
    numba_threads = numba.get_num_threads()
    try:
        numba.set_num_threads(n)
        yield
    finally:
        numba.set_num_threads(numba_threads)


@contextmanager
def set_num_threads(n):
    with threadpoolctl.threadpool_limits(n), set_fftw_threads(n), set_numba_threads(n):
        yield
