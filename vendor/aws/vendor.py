"""
Vendor AWS Serverless Application.

This AWS Lambda function builds python wheels inside the lambda environment.
These wheels can then be extracted for use in your own lambda functions.
"""
import os
from os import path
import shutil
import subprocess
import tempfile

import boto3


def build(event, context):
    """Build takes a package name and builds python wheels for it and its dependencies."""
    package = event['pathParameters']['package']
    force = event['queryParameters'].get('force')
    bucket = os.environ['BUCKET']
    baseurl = os.environ.get('BUCKET_URL', 'https://{bucket}.s3.amazonaws.com/'.format(bucket=bucket))
    # First, ensure build environment is set up.
    subprocess.check_call(['sudo', 'yum', '-y', 'groupinstall', 'Developer tools'])
    subprocess.check_call(['sudo', 'pip', 'install', 'wheel'])
    # Then download package and build wheels.
    obj_list = []
    wdir = tempfile.mkdtemp()
    try:
        # Shame pip doesn't have an API...
        subprocess.check_call(['pip', 'download', package], cwd=wdir)
        for fname in os.listdir(wdir):
            if not fname.endswith('.whl'):
                if force or not s3exists(PackageInfo.parse(fname), bucket):
                    subprocess.check_call(['pip', 'wheel', fname], cwd=wdir)

        for fname in os.listdir(wdir):
            if fname.endswith('.whl'):
                wpath = path.join(wdir, fname)
                obj_list.append(s3upload(wpath, bucket, overwrite=force))
    finally:
        shutil.rmtree(wdir)

    return [baseurl + p for p in obj_list]


def s3exists(pkg, bucket_name):
    """Check if package exists in S3 bucket."""
    s3 = boto3.resource('s3')
    # TODO: Obviously this can produce false positives if the bucket is being
    #       cohabited. However, finding out the wheel name is not 100% easy.
    filter_prefix = '{pkg.name}/{pkg.name}-{pkg.version}-'.format(pkg=pkg)
    objs = s3.Bucket(bucket_name).objects.filter(Prefix=filter_prefix)
    for obj in objs:
        if obj.endswith('.whl'):
            return True

    return False


def s3upload(wheel_path, bucket_name, overwrite=False):
    """Upload list of wheels to S3 bucket."""
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    key = '{pkg.name}/{wheel_path}'.format(
        pkg=PackageInfo.parse(wheel_path),
        wheel_path=wheel_path,
    )
    obj = bucket.Object(key)
    if overwrite:
        obj.upload_file(wheel_path)
    else:
        try:
            obj.load()
        except:  # ...what exception?
            obj.upload_file(wheel_path)

    return key


class PackageInfo(object):
    """Information for a python package artifact."""

    def __init__(self, name, version, archs):
        self.name = name
        self.version = version
        self.archs = set(archs)

    @classmethod
    def parse(cls, filename):
        """Create a PackageInfo object by parsing an artifact filename."""
        filebase = path.splitext(path.basename(filename))[0]
        parts = filebase.split('-')
        name = parts[0]
        version = parts[1] if len(parts) > 1 else None
        archs = parts[2].split('.') if len(parts) > 2 else []
        return cls(name, version, archs)
