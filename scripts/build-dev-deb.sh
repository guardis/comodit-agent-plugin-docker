#!/bin/bash

NAME="comodit-agent-plugin-docker"
TMP_DIR=/tmp/comodit-agent-plugin-docker

cd `dirname $0`
cd ..

# Set version information
if [ -z $1 ]
then
  # Get the latest release*dev tag  
  VERSION=`git describe --long --match "release*dev" | awk -F"-" '{print $2}'`
else
  VERSION=$1
fi

if [ -z $2 ]
then
  # How much commit since last release*dev tag ?
  RELEASE=`git describe --long --match "release*dev" | awk -F"-" '{print $3}'`
else
  RELEASE=$2
fi

COMMIT=`git describe --long --match "release*dev" | awk -F"-" '{print $4}'`
MESSAGE="Release $VERSION-$RELEASE-$COMMIT"

debchange --newversion $VERSION-$RELEASE "$MESSAGE"

# Build package
DIST_DIR=${TMP_DIR}/dist
python setup.py sdist --dist-dir=${DIST_DIR}
mv ${DIST_DIR}/$NAME-$VERSION-$RELEASE.tar.gz $NAME\_$VERSION.$RELEASE.orig.tar.gz
dpkg-buildpackage -i -I -rfakeroot

# Clean-up
python setup.py clean
make -f debian/rules clean
find . -name '*.pyc' -delete
rm -rf *.egg-info
rm -f $NAME\_$VERSION.$RELEASE.orig.tar.gz
