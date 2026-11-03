import asyncio

import httpx

from multicluster.errors import describe_error
from multicluster.profiles import ProfileError
from tests.fakes import status_error


def test_auth_failures_point_at_the_oidc_client() -> None:
    assert "OIDC client" in describe_error(status_error(401))


def test_unlisted_statuses_are_reported_verbatim() -> None:
    assert describe_error(status_error(418)) == "FirecREST answered 418"


def test_transport_and_timeout_errors_are_named() -> None:
    assert describe_error(httpx.ConnectError("x")) == "unreachable: ConnectError"
    assert describe_error(asyncio.TimeoutError()) == "timed out"


def test_profile_errors_keep_their_message() -> None:
    assert describe_error(ProfileError("cluster 'b': set ID")) == "cluster 'b': set ID"
