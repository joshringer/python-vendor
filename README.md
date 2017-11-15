# Python Vendor

This package provides an AWS Serverless API for building compiled Python
packages, ready for use in your own Lambda functions.


## Development

### Build toolchains

Because Lambda runs on a readonly filesystem, we must package up any build
tools required for compilation. Roughly speaking, this equates for now to the
relevant python-devel package for Python headers.

The following process is the current method for gathering these build tools:

1. Launch an EC2 instance of the latest Lambda AMI. You can find the image
   in the documentation here:
   http://docs.aws.amazon.com/lambda/latest/dg/current-supported-versions.html

2. Run `yum` with the --downloadonly option to fetch the rpm archives into a
   separate directory.  
   ```
   mkdir rpms
   sudo yum -y --downloadonly --downloaddir="$(pwd)/rpms" install gcc python27-devel python36-devel
   ```
   You may get many for one request as it will also fetch dependencies.

3. Run the `rpm2cpio` and `cpio` as following to extract the artifacts from the
   rpm archives.  
   ```
   mkdir toolchain && cd toolchain
   for r in ../rpms/*.rpm; do rpm2cpio "$r" | cpio -idm; done
   ```

4. Because the rpms have only been unpacked install scripts are not run, so you
   must manually add a few missing pieces such as general softlinks for a
   number of the binaries.
   ```
   ln -s gcc48 usr/bin/gcc
   ```

5. You may at this point want to test the setup. Add the relevant directories
   to your path, and try a pip build.

6. Once comfortable, download that directory to vendor/aws/vendor in this
   repository.

In order to support more packages, which may include other dependencies, we may
want to also include some common ones for building, eg. numpy. At some point it
would be a good idea to find a way for users to get any dependencies they need
into the build environment, but that sounds like a tough problem, in particular
since we are unable to call yum within the Lambda function.
