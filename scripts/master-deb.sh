#!/bin/bash

set -e

[[ $1 == dev ]] && scripts/build-dev-deb.sh 
[[ $1 == prod ]] && scripts/build-deb.sh 

scripts/build-all-deb.sh $1

