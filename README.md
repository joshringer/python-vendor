# Python Vendor

This package provides an AWS Serverless API for building compiled Python
packages, ready for use in your own Lambda functions.


## Development

### Build toolchains

Because Lambda runs on a readonly filesystem, we must package up any build
tools required for compilation. Roughly speaking, this equates for now to the
"Development tools" group in amazon's yum repository, and also the relevant
python-devel package for Python headers.

The following process is the current method for gathering these build tools:

1. Launch an EC2 instance of the latest Lambda AMI. You can find the image
   in the documentation here:
   http://docs.aws.amazon.com/lambda/latest/dg/current-supported-versions.html

2. Run `yum` with the --installroot option to install the rpm into a separate
   directory.  
   Eg. `sudo yum -y --installroot=$(pwd) groupinstall "Development tools"`

3. Download that directory to the relevant directory in this repository.

This process generates way more than we need, as it includes all dependencies
all the way down to the base system(!). This will need to be improved, as
space limitations are also a concern for Lambda (see
http://docs.aws.amazon.com/lambda/latest/dg/limits.html). A yum download and
rpm install using prefix doesn't do it for us, because the development tools
are not relocatable packages it seems.

In order to support more packages, which may include other dependencies, we may
want to also include some common ones for building, eg. numpy. At some point it
would be a good idea to find a way for users to get any dependencies they need
into the build environment, but that sounds like a tough problem, in particular
since we are unable to call yum within the Lambda function.
