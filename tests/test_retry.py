import firecrest as f7t
import httpx
import pytest

from multicluster.retry import is_retryable, with_retry


class _Flaky:
    def __init__(self, failures: int, error: Exception) -> None:
        self.calls = 0
        self._failures = failures
        self._error = error

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self._failures:
            raise self._error
        return "ok"


async def test_transient_errors_are_retried_until_success() -> None:
    call = _Flaky(failures=2, error=httpx.ConnectError("down"))
    assert await with_retry(call, delays=(0, 0, 0)) == "ok"
    assert call.calls == 3


async def test_retries_stop_after_the_last_delay() -> None:
    call = _Flaky(failures=10, error=httpx.ConnectError("down"))
    with pytest.raises(httpx.ConnectError):
        await with_retry(call, delays=(0, 0))
    assert call.calls == 3


async def test_permanent_errors_propagate_at_once() -> None:
    call = _Flaky(failures=1, error=ValueError("bad request"))
    with pytest.raises(ValueError, match="bad request"):
        await with_retry(call, delays=(0, 0))
    assert call.calls == 1


def test_transport_errors_are_retryable_but_others_are_not() -> None:
    assert is_retryable(httpx.ReadTimeout("slow"))
    assert not is_retryable(KeyError("jobId"))


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(503, True), (408, True), (429, True), (401, False), (404, False)],
)
def test_firecrest_status_decides_retryability(status: int, retryable: bool) -> None:
    exc = f7t.UnexpectedStatusException([httpx.Response(status)], expected_status_code=200)
    assert is_retryable(exc) is retryable
