"""Thin read-only client for the Tabbycat REST API.

Only the endpoints Compass needs are wrapped: listing tournaments and listing
a tournament's adjudicators (which, for a staff token, include `email` + `url_key`).
"""

import re

import httpx

# Tabbycat paginates with drf_link_header_pagination: the body is a JSON array
# and the next page (if any) is advertised in the HTTP `Link` header.
_LINK_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


class TabbycatError(Exception):
    """Any failure talking to a Tabbycat instance (network, auth, or HTTP)."""


class TabbycatClient:
    def __init__(self, base_url, token, timeout=20.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._client.close()

    def _get(self, url):
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            raise TabbycatError(f"Could not reach Tabbycat: {exc}") from exc
        if response.status_code in (401, 403):
            raise TabbycatError(
                f"Authentication failed ({response.status_code}). Check the API "
                "token and that its user can view private URLs and contacts."
            )
        if response.status_code >= 400:
            raise TabbycatError(
                f"HTTP {response.status_code} for {url}: {response.text[:200]}"
            )
        return response

    def _paged(self, path):
        """Yield every item across all pages for a list endpoint."""
        url = f"{self.base_url}{path}"
        while url:
            response = self._get(url)
            data = response.json()
            if isinstance(data, dict) and "results" in data:  # defensive
                yield from data["results"]
                url = data.get("next")
            else:
                yield from data
                match = _LINK_NEXT.search(response.headers.get("Link", ""))
                url = match.group(1) if match else None

    def tournaments(self):
        return list(self._paged("/api/v1/tournaments"))

    def adjudicators(self, slug):
        return list(self._paged(f"/api/v1/tournaments/{slug}/adjudicators"))
