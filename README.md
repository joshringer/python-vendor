# Python Vendor

This package provides an AWS Serverless API for building compiled Python
packages, ready for use in your own Lambda functions.


## Installation

### Manual Deployment

First, deploy the Vendor-deployment stack to prepare a bucket for Serverless
artifacts.
```
aws cloudformation deploy --stack-name Vendor-deployment --template-file vendor/aws/vendor-deployment.yml
```
The deployment bucket name can be found from the stack outputs.
```
aws cloudformation describe-stacks --stack-name Vendor-deployment
```

Next we can package and deploy the Vendor service.
```
aws cloudformation package --template-file vendor/aws/vendor.yml --s3-bucket {Vendor-deployment.BucketName} --output-template-file /tmp/vendorpk.yml
aws cloudformation deploy --stack-name Vendor --template-file /tmp/vendorpk.yml --capabilities CAPABILITY_IAM
```
Again, the service URL can be found from the stack outputs.
```
aws cloudformation describe-stacks --stack-name Vendor
```


## Development

### Build toolchains

Because Lambda runs on a readonly filesystem, building is hard as the build
tools are not available on the system. Therefore, we have cheated a little and
instead spawn our own 'Lambda' on a self-destructing EC2 instance. This is done
by passing a script into the EC2 user-data and setting the instance to
terminate on shutdown, which the script does on exit.
