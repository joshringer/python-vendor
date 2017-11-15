#!/bin/bash

### Variables ###
echo "PYTHON_VERSION=$PYTHON_VERSION"
echo "EXTRAS=$EXTRAS"
echo "S3_BASE=$S3_BASE"
echo "ARCHIVE_NAME=$ARCHIVE_NAME"


### Definitions ###
function terminate {
  echo 'Terminating' >&2
  shutdown -h
}
trap terminate EXIT

pipcmd="pip$PYTHON_VERSION"
wheeldir="wheels"


### Install dependencies ###
yum -y groupinstall "Development tools"
yum -y install "python${PYTHON_VERSION}-devel"
if [ -n "$EXTRAS" ]
then
  yum -y install "$EXTRAS"
fi
$pipcmd install wheel


### Fetch archive ###
aws s3 cp "$S3_BASE/$ARCHIVE_NAME" .


### Perform build ###
mkdir "$wheeldir"
$pipcmd wheel -d "$wheeldir" "$ARCHIVE_NAME"


### Upload wheels ###
cd "$wheeldir"
aws s3 cp --recursive . "$S3_BASE"
