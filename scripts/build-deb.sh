#!/bin/bash

NAME="comodit-agent-plugin-docker"
TMP_DIR=/tmp/comodit-agent-plugin-docker

cd `dirname $0`
cd ..

# Set version information
VERSION=`git describe --tags --long  | awk -F"-" '{print $2}'`
RELEASE=`git describe --tags --long | awk -F"-" '{print $3}'`
COMMIT=`git describe --tags --long | awk -F"-" '{print $4}'`
MESSAGE="Release $VERSION-$RELEASE-$COMMIT"

# Set version information
. scripts/build-pkg-functions
set_version $1 $2

echo $MESSAGE

export DEBEMAIL
export DEBFULLNAME

debchange --newversion $VERSION-$RELEASE "$MESSAGE"

unset DEBEMAIL
unset DEBFULLNAME

# Build package
DIST_DIR=${TMP_DIR}/dist
#python setup.py sdist --dist-dir=${DIST_DIR}
#mv ${DIST_DIR}/$NAME-$VERSION.tar.gz $NAME\_$VERSION.$RELEASE.orig.tar.gz
dpkg-buildpackage -i -I -rfakeroot

# Clean-up
python setup.py clean
make -f debian/rules clean
find . -name '*.pyc' -delete
rm -rf *.egg-info
rm -f $NAME\_$VERSION.$RELEASE.orig.tar.gz

