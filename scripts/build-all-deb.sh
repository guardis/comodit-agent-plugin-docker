#!/bin/bash

source config

PACKAGES=packages-dev
[[ $1 == "prod" ]] && PACKAGES=packages-prod

for tab in "${TABS[@]}"
do
  # Create distribution directory if not exist
  sudo mkdir -p /var/cache/pbuilder/$tab-amd64
  sudo mkdir -p /var/cache/pbuilder/$tab-i386

  # If it is a Debian distribution else it is Ubuntu
  if [ $tab = 'wheezy' ] || [ $tab = 'jessie' ] || [ $tab = 'stretch' ]; then
    # Create base.cow distribution 
    sudo HOME=/home/$USERNAME DIST=$tab /usr/sbin/cowbuilder --create --basepath /var/cache/pbuilder/$tab-amd64/base.cow --distribution $tab --debootstrapopts --arch --debootstrapopts amd64
    sudo HOME=/home/$USERNAME DIST=$tab /usr/sbin/cowbuilder --create --basepath /var/cache/pbuilder/$tab-i386/base.cow --distribution $tab --debootstrapopts --arch --debootstrapopts i386
  else
    sudo HOME=/home/$USERNAME DIST=$tab /usr/sbin/cowbuilder --create --basepath /var/cache/pbuilder/$tab-amd64/base.cow --distribution $tab --components "main universe" --debootstrapopts --arch --debootstrapopts amd64
    sudo HOME=/home/$USERNAME DIST=$tab /usr/sbin/cowbuilder --create --basepath /var/cache/pbuilder/$tab-i386/base.cow --distribution $tab --components "main universe" --debootstrapopts --arch --debootstrapopts i386
  fi

  # Build packages 
  sudo HOME=/home/$USERNAME DIST=$tab ARCH=amd64 /usr/sbin/cowbuilder --build ../comodit-agent-plugin-docker*.dsc 
  sudo HOME=/home/$USERNAME DIST=$tab ARCH=i386 /usr/sbin/cowbuilder --build ../comodit-agent-plugin-docker*.dsc
  
  mkdir -p /home/$USERNAME/$PACKAGES/$tab-amd64 /home/$USERNAME/$PACKAGES/$tab-i386

  sudo mv -f /var/cache/pbuilder/$tab-amd64/result/*deb /home/$USERNAME/$PACKAGES/$tab-amd64
  sudo mv -f /var/cache/pbuilder/$tab-i386/result/*deb /home/$USERNAME/$PACKAGES/$tab-i386
done  

sudo find /var/cache/pbuilder -name *.changes -exec rm -fr {} \;
sudo find /var/cache/pbuilder -name *.dsc -exec rm -fr {} \;

