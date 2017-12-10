"""Vendor provides an AWS service API for building binary Python packages for use in Lambda functions."""
import os.path

from setuptools import find_packages, setup


def read_package_meta():
    """Read metadata from __about__ file."""
    filepath = os.path.join(os.path.dirname(__file__), 'vendor', '__about__.py')
    data = {}
    with open(filepath) as fp:
        exec(fp.read(), {}, data)

    return data


def read_readme():
    """Read readme file."""
    filepath = os.path.join(os.path.dirname(__file__), 'README.rst')
    with open(filepath) as fp:
        return fp.read()


if __name__ == '__main__':
    meta = read_package_meta()
    setup(
        name='vendor',
        version=meta['__version__'],

        description=__doc__,
        long_description=read_readme(),
        long_description_content_type='text/x-rst; charset=utf8',

        url=meta['__url__'],

        author=meta['__author__'],
        author_email=meta['__author_email__'],

        license=meta['__license__'],

        classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: Console',
            'Intended Audience :: Developers',
            'License :: Public Domain',
            'Natural Language :: English',
            'Operating System :: POSIX',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3.6',
            'Topic :: Software Development',
        ],

        keywords='aws lambda vendor build binary package wheel',

        packages=find_packages(),

        install_requires=[
            'boto3>=1.4.4',
            'packaging',
            'requests',
            'six',
        ],

        python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, !=3.5.*',

        package_data={
            'vendor': ['aws/*.yml', 'aws/vendor/*.py', 'aws/vendor/build.sh'],
        },

        zip_safe=False,
    )
