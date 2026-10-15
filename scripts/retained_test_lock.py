"""Prevent concurrent suites from changing the shared test API's schema routing."""
from contextlib import contextmanager
import os
from parking_tools import ROOT


@contextmanager
def retained_test_lock():
    folder=ROOT/'.tools/test-runs'
    folder.mkdir(parents=True,exist_ok=True)
    handle=(folder/'active.lock').open('a+b')
    if handle.seek(0,2)==0:
        handle.write(b'0'); handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('A retained parking test suite is already running. Wait for it to finish; no records were changed.') from None
    try:
        yield
    finally:
        handle.seek(0)
        if os.name=='nt':
            msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()
