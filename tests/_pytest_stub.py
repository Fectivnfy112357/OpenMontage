"""Stub pytest module providing just `raises` for legacy test files.
Loaded via sys.modules['pytest'] so legacy tests can run without pytest installed.
"""
import sys
from typing import Optional, Type


class _RaisesCtx:
    def __init__(self, exc: Type[BaseException], match: Optional[str]):
        self.exc = exc
        self.match = match
        self._exc = None
        self._tb = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        self._exc = et
        self._ev = ev
        self._tb = tb
        if et is None:
            raise AssertionError(f"Expected {self.exc.__name__} but no exception was raised")
        if not issubclass(et, self.exc):
            return False  # let other exceptions propagate
        if self.match and self.match not in str(ev):
            raise AssertionError(
                f"Expected error matching {self.match!r}, got: {ev}"
            ) from ev
        return True


def raises(exc: Type[BaseException], match: Optional[str] = None) -> _RaisesCtx:
    return _RaisesCtx(exc, match)


# Provide a minimal `main` for `python -m pytest`-style invocations
def main(*args, **kwargs):  # pragma: no cover
    print("pytest stub: install real pytest to run this suite properly")
    sys.exit(1)