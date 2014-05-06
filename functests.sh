#!/bin/bash

SRC_DIR=$(dirname $0)

cd ${SRC_DIR}/test/functional
nosetests --exe $@
func1=$?
cd -

exit $((func1 + func2))
