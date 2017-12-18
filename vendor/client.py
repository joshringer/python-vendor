"""The client module contains the Vendor client for calling the remote Vendor service."""
import sys

import requests
import six


class VendorClient(object):
    """The Vendor client."""

    def __init__(self, service_url, http_session=None):
        """Create new instance of Vendor client."""
        self.service_url = service_url
        if http_session:
            self.session = http_session
        else:
            self.session = requests.Session()

    def _request(self, method, path, *a, **kw):
        parts = [self.service_url]
        if isinstance(path, six.string_types):
            parts.append(path)
        else:
            parts.extend(path)

        url = '/'.join(parts)
        response = self.session.request(method, url, *a, **kw)
        response.raise_for_status()
        return response.json()

    def version(self):
        """Get service version."""
        return self._request('get', 'version')

    def vend(self, requirements, python=sys.version_info.major):
        """Vend packages."""
        if str(python) not in {'2', '3'}:
            msg = 'Python value {} must be 2 or 3'
            raise ValueError(msg.format(python))

        return self._request('post', (str(python), 'vend', requirements))
