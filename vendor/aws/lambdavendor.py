"""
Vendor AWS Serverless Application.

This AWS Lambda function builds python wheels inside the lambda environment.
These wheels can then be extracted for use in your own lambda functions.
"""
import contextlib
import functools
import json
import logging
import os
from os import path
import re
import shutil
import subprocess
import tempfile

import boto3


log = logging.getLogger(__name__)

BUCKET = os.environ['BUCKET']
PROXY_PARAM_RE = re.compile(r'\{(?P<key>\w+)\+\}')


def apiproxy(function):
    """Make API Gateway Lambda Proxy Integration even friendlier."""
    @functools.wraps(function)
    def proxy(event, context):
        args = []
        kwargs = {}
        match = PROXY_PARAM_RE.search(event['resource'])
        if match:
            ppath = event['pathParameters'].pop(match.group('key'))
            args.extend(ppath.split('/'))

        if event['body']:
            kwargs.update(json.loads(event['body']))

        kwargs.update(event['queryStringParameters'])
        kwargs.update(event['pathParameters'])
        result = function(*args, **kwargs)
        response = {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result),
        }
        return response

    return proxy


@apiproxy
def lambda_vend(requirements, rebuild=False, minimal=False, bucketname=BUCKET):
    """Vend takes a package name and builds python wheels for it and its dependencies."""
    keys = clone_packages(requirements, bucketname, overwrite=rebuild)
    s3 = boto3.client('s3')
    baseurl = 'https://{bucketname}.s3.amazonaws.com/'.format(bucketname=bucketname)
    urls = []
    for key in keys:
        fname = key.rsplit('/', 1)[-1]
        # We assume successful parse as it happened in clone_packages already.
        pi = PackageInfo.parse(fname)
        if pi.is_src():
            # TODO: Check for wheel, only overwrite if rebuild==True.
            with tempdir() as wdir:
                dest = path.join(wdir, fname)
                s3.download_file(bucketname, key, dest)
                bkeys = build_wheel(dest, bucketname)
                urls.extend(baseurl + k for k in bkeys)
        elif not minimal:
            urls.append(baseurl + key)

    return urls


def clone_packages(requirements, bucketname, overwrite=False):
    """Download packages from pypi, then upload to S3 bucket."""
    rlist = requirements.split() if hasattr(requirements, 'split') else requirements
    with tempdir() as wdir:
        subprocess.check_call(['pip', 'download'] + rlist, cwd=wdir)
        return upload_artifacts(wdir, bucketname)


def build_wheel(srcpath, bucketname):
    """Build a wheel from provided source, then upload to S3 bucket."""
    # First, ensure build environment is set up.
    tdir = path.abspath(os.getcwd())
    subprocess.check_call(['yum', '--installroot', tdir, '-y', 'groupinstall', 'Developer tools'])
    newpath = '{tdir}/usr/local/bin:{tdir}/usr/bin:{tdir}/bin'.format(tdir=tdir)
    if 'PATH' in os.environ:
        os.environ['PATH'] = ':'.join([newpath, os.environ['PATH']])
    else:
        os.environ['PATH'] = newpath

    subprocess.check_call(['pip', 'install', 'wheel'])
    # Then build the wheel.
    with tempdir() as wdir:
        subprocess.check_call(['pip', 'wheel', srcpath], cwd=wdir)
        return upload_artifacts(wdir, bucketname, overwrite=True)


def upload_artifacts(dirpath, bucketname, overwrite=False):
    """Upload a directory of artifacts to S3 bucket."""
    keys = set()
    # TODO: Potentially run in parallel?
    for fname in os.listdir(dirpath):
        fpath = path.join(dirpath, fname)
        try:
            key = upload_artifact(fpath, bucketname, overwrite=overwrite)
        except Exception:
            log.warning('Failed to upload %s', fname, exc_info=True)
        else:
            keys.add(key)

    return keys


def upload_artifact(filepath, bucketname, overwrite=False):
    """Upload a package artifact to S3 bucket."""
    filename = path.basename(filepath)
    key = '{pkg.distribution}/{filename}'.format(
        pkg=PackageInfo.parse(filename),
        filename=filename,
    )
    s3 = boto3.resource('s3')
    obj = s3.Object(bucketname, key)
    if overwrite:
        obj.upload_file(filepath)
    else:
        try:
            obj.load()
        except:  # ...what exception?
            obj.upload_file(filepath)

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
                return cls(match.groupdict())

        raise ParseError('Unable to parse filename: ' + filename)

    def is_src(self):
        return self.ext != '.whl'

    def is_whl(self):
        return self.ext == '.whl'


class ParseError(ValueError):
    """Error raised when unable to parse a string."""


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
