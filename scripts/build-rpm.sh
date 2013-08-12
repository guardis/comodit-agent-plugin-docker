#!/bin/bash
NAME="comodit-agent-plugin-docker"
platforms=(epel-6-i386 fedora-17-i386 fedora-18-i386 fedora-19-i386)

cd `dirname $0`
cd ..

# Set version information
. scripts/build-pkg-functions
set_version $1 $2

sed "s/#VERSION#/${VERSION}/g" ${NAME}.spec.template > ${NAME}.spec
sed -i "s/#RELEASE#/${RELEASE}/g" ${NAME}.spec
sed -i "s/#COMMIT#/${COMMIT}/g" ${NAME}.spec

tar -cvzf $HOME/rpmbuild/SOURCES/${NAME}-${VERSION}-${RELEASE}.tar.gz * \
--exclude *.spec \
--exclude *.template \
--exclude *.sh \
--exclude *.pyc \
--exclude *.pyo

rpmbuild -ba ${NAME}.spec


for platform in "${platforms[@]}"
do
    /usr/bin/mock -r ${platform} --rebuild $HOME/rpmbuild/SRPMS/${NAME}-${VERSION}-${RELEASE}*.src.rpm
done
