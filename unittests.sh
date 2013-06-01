#!/bin/bash

cd $(dirname $0)/test/unit
nosetests -v --exe --with-coverage --cover-package gluster --cover-erase --cover-html --cover-branches $@

saved_status=$?
rm -f .coverage
exit $saved_status
