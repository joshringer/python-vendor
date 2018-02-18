"""
Vendor AWS Serverless Application.

This AWS Lambda function builds python wheels inside the lambda environment.
These wheels can then be extracted for use in your own lambda functions.
"""
__version__ = '0.2.dev1'

import contextlib
import functools
import json
import logging
import os
import os.path
import re
import shutil
import string
import subprocess
import sys
import tempfile
import traceback

import boto3


# Required config
BUCKET = os.environ['BUCKET']
BUILD_PROXY_AMI = os.environ['BUILD_PROXY_AMI']
BUILD_PROXY_PROFILE = os.environ['BUILD_PROXY_PROFILE']
# Optional config
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

# Constants
BUILD_STARTED_MSG = 'Build under way. Once complete, download wheels from {bucket_url}.'
NOT_FOUND_MSG = 'Route not found.'
SERVER_ERROR_MSG = '''Something went wrong. Maybe the traceback will help?
Please include it in any issue you raise.

'''
PROXY_PARAM_RE = re.compile(r'\{(?P<key>\w+)\+\}')


logging.basicConfig(level=LOG_LEVEL)

log = logging.getLogger('vendor')


class APIError(Exception):
    """APIError signals an error response for apiproxy()."""

    def __init__(self, status_code, message):
        """
        Create new API Error instance.

        :param int status_code: HTTP Error Code
        :param str message: Error message
        """
        self.status_code = status_code
        self.message = message
        super(APIError, self).__init__(status_code, message)


class apiproxy(object):
    """Make API Gateway Lambda Proxy Integration even friendlier."""

    routes = {}

    @classmethod
    def dispatch(cls, event, context):
        """Call route according to event/context."""
        resource = event['resource']
        # Reverse sort means deeper routes come first
        for route in reversed(sorted(apiproxy.routes)):
            if resource.startswith(route):
                proxy = apiproxy.routes[route]
                break

        else:
            return cls._api_response(404, {'message': NOT_FOUND_MSG, 'resource': resource})

        return proxy(event, context)

    @classmethod
    def route(cls, *routes):
        """
        Register a function to be called for routes.

        This method can be used as a function decorator.
        """
        return functools.partial(cls, routes=routes)

    def __init__(self, function, routes):
        """
        Create new apiproxy routes.

        :param function function: The function called by the routes
        :param list[str] routes: The routes for which to call the function

        The function registered may have any JSON-serialisable arguments.
        Positional arguments should be listed as path paramters in the routes.
        The function should return a JSON-serialisable object.
        """
        self.function = function
        apiproxy.routes.update((r, self) for r in routes)

    def __call__(self, event, context):
        """
        Run incoming APIGateway proxy event through assigned function.

        Parses incoming request into a set of args and kwargs.
        Calls function with those args.
        Returns an API response, with the result of the function returned as a
        JSON-encoded object in the response body.
        """
        args = []
        kwargs = {}
        match = PROXY_PARAM_RE.search(event['resource'])
        if match:
            ppath = event['pathParameters'].pop(match.group('key'))
            args.extend(ppath.split('/'))

        if event['body']:
            kwargs.update(json.loads(event['body']))
        if event['queryStringParameters']:
            kwargs.update(event['queryStringParameters'])
        if event['pathParameters']:
            kwargs.update(event['pathParameters'])

        try:
            result = self.function(*args, **kwargs)
        except APIError as err:
            return self._api_response(err.status_code, {'message': err.message})
        except Exception:
            log.exception('Error executing %s', self.function)
            return self._api_response(500, {'message': SERVER_ERROR_MSG + traceback.format_exc()})

        return self._api_response(200, result)

    @staticmethod
    def _api_response(code, obj):
        return {
            'statusCode': code,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(obj),
        }


# AWS Lambda requires reference to a single function at module level
dispatch = apiproxy.dispatch


@apiproxy.route('/version')
def version():
    """Report the current API version."""
    return {'version': __version__}


@apiproxy.route('/3/vend', '/2/vend')
def vend(requirements, rebuild=False, minimal=False, bucketname=BUCKET):
    """Vend takes a package name and builds python wheels for it and its dependencies."""
    keys = []
    with download_packages(requirements) as packagepaths:
        for filepath in packagepaths:
            artifact = PackageArtifact(filepath)
            key = upload_artifact(artifact, bucketname, overwrite=rebuild)
            keys.append(key)
            if artifact.info.is_src():
                # TODO: Check for wheel, only overwrite if rebuild==True.
                build_wheel(key, sys.version_info, bucketname=bucketname)

    bucket_url = 'https://{bucketname}.s3.amazonaws.com/'.format(bucketname=bucketname)
    return {
        'message': BUILD_STARTED_MSG.format(bucket_url=bucket_url),
        'bucket_url': bucket_url,
        'artifacts': sorted(keys),
    }


def build_wheel(src_key, python_version, bucketname=BUCKET):
    """Build a wheel from provided source, then upload to S3 bucket."""
    fpath, fname = src_key.rsplit('/', 1)
    env = {
        'PYTHON_VERSION': '{v.major}{v.minor}'.format(v=python_version),
        'S3_BASE': 's3://{}/{}'.format(bucketname, fpath),
        'ARCHIVE_NAME': fname,
    }
    # Construct build script
    tplfn = os.path.join(os.path.dirname(__file__), 'build.sh')
    with open(tplfn, encoding='utf8') as tplfp:
        tpl = string.Template(tplfp.read())

    script = tpl.safe_substitute(env)
    # Launch EC2 instance to perform the build in
    launch_params = {
        'ImageId': BUILD_PROXY_AMI,
        'InstanceType': 't2.micro',  # Free tier default
        'MaxCount': 1,
        'MinCount': 1,
        'UserData': script,
        'IamInstanceProfile': {
            'Name': BUILD_PROXY_PROFILE,
        },
        'InstanceInitiatedShutdownBehavior': 'terminate',
    }
    ec2 = boto3.resource('ec2')
    ec2.create_instances(**launch_params)


@contextlib.contextmanager
def download_packages(requirements):
    """Download packages from pypi into temp folder."""
    rlist = requirements.split() if hasattr(requirements, 'split') else requirements
    cdir = os.path.abspath('/tmp/pipcache')
    try:  # exist_ok=True not available in Python 2.7
        os.makedirs(cdir)
    except OSError:
        pass

    with tempdir() as wdir:
        subprocess.check_call(['pip', 'download', '--cache-dir', cdir] + rlist, cwd=wdir)
        yield [os.path.join(wdir, fname) for fname in os.listdir(wdir)]


def upload_artifact(artifact, bucketname=BUCKET, overwrite=False):
    """Upload a package artifact to S3 bucket."""
    key = '{info.distribution}/{filename}'.format(
        info=artifact.info,
        filename=artifact.filename,
    )
    s3 = boto3.resource('s3')
    obj = s3.Object(bucketname, key)
    if overwrite:
        obj.upload_file(artifact.filepath)
    else:
        try:
            obj.load()
        except s3.meta.client.exceptions.ClientError:
            obj.upload_file(artifact.filepath)

    return key


class PackageInfo(object):
    """
    Information for a python package artifact.

    See PEP 425 https://www.python.org/dev/peps/pep-0425/
    """

    src_re = re.compile(
        r'(?P<distribution>[^-]+)-(?P<version>[^-]+)'
        r'(?P<ext>\.tar\.[bgx]z|\.zip)'
    )
    whl_re = re.compile(
        r'(?P<distribution>[^-]+)-(?P<version>[^-]+)'
        r'(-(?P<build>\d[^-]*))?'
        r'-(?P<python>[^-]+)-(?P<abi>[^-]+)-(?P<platform>[^-]+)'
        r'(?P<ext>\.whl)'
    )

    def __init__(self, distribution, version, ext, build='', python='', abi='none', platform='any'):
        """Create new PackageInfo object."""
        self.distribution = distribution
        self.version = version
        self.build_tag = build
        self.python_tags = set(python.split('.')) if python else None
        self.abi_tags = set(abi.split('.'))
        self.platform_tags = set(platform.split('.'))
        self.ext = ext

    @classmethod
    def parse(cls, filename):
        """Create a PackageInfo object by parsing an artifact filename."""
        for rgx in (cls.src_re, cls.whl_re):
            match = rgx.match(filename)
            if match:
                return cls(**match.groupdict())

        raise ParseError('Unable to parse filename: ' + filename)

    def is_src(self):
        """Test if this package is source code."""
        return self.ext != '.whl'

    def is_whl(self):
        """Test if this package is a wheel."""
        return self.ext == '.whl'


class ParseError(ValueError):
    """Error raised when unable to parse a string."""


class PackageArtifact(object):
    """Class representing an individual artifact for a Python package."""

    def __init__(self, filepath):
        """Create artifact, extracting information from filepath."""
        self.filepath = filepath
        # Keep because they're used frequently
        self.dirname, self.filename = os.path.split(filepath)
        self.info = PackageInfo.parse(self.filename)


@contextlib.contextmanager
def tempdir():
    """
    Construct a self-destructing temporary directory.

    Usage:
    >>> with tempdir() as tdir:
    ...     # Do stuff.
    """
    wdir = tempfile.mkdtemp()
    yield wdir
    shutil.rmtree(wdir)
