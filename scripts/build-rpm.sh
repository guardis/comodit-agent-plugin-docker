#!/bin/bash

# Exit on errors
set -e
source config

NAME="comodit-agent-plugin-docker"

if [ -z $1 ]
then
  # Get the latest tag on the current branch
  VERSION=`git describe --abbrev=0 --tags --match "*[^dev]" | awk -F"-" '{print $2}'`
else
  VERSION=$1
fi

if [ -z $2 ]
then
  RELEASE=1
else
  RELEASE=$2
fi

COMMIT=`git describe --long --match "release-${VERSION}" | awk -F"-" '{print $4}'`

sed "s/#VERSION#/${VERSION}/g" rpmbuild/SPECS/${NAME}.spec.template > rpmbuild/SPECS/${NAME}.spec
sed -i "s/#RELEASE#/${RELEASE}/g" rpmbuild/SPECS/${NAME}.spec
sed -i "s/#COMMIT#/${COMMIT}/g" rpmbuild/SPECS/${NAME}.spec

mkdir -p rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Do not tar directly in SOURCES directory to escape error
tar -cvzf ${NAME}-${VERSION}-${RELEASE}.tar.gz * \
--exclude *.spec \
--exclude *.template \
--exclude *.sh \
--exclude *.pyc \
--exclude *.pyo

mv ${NAME}-${VERSION}-${RELEASE}.tar.gz rpmbuild/SOURCES

rpmbuild --define "_topdir $(pwd)/rpmbuild" -ba rpmbuild/SPECS/${NAME}.spec

if [ -f "/usr/bin/mock" ]
then
  for platform in "${PLATFORMS[@]}"
  do
    /usr/bin/mock -r ${platform} --rebuild rpmbuild/SRPMS/${NAME}-${VERSION}-${RELEASE}*.src.rpm
    mkdir -p ${HOME}/packages/${platform}
    mv /var/lib/mock/${platform}/result/*.rpm ${HOME}/packages/${platform}
  done
fi
