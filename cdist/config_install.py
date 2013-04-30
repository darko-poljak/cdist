#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# 2010-2013 Nico Schottelius (nico-cdist at schottelius.org)
#
# This file is part of cdist.
#
# cdist is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cdist is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cdist. If not, see <http://www.gnu.org/licenses/>.
#
#

import logging
import os
import stat
import shutil
import sys
import tempfile
import time
import itertools
import pprint

import cdist
from cdist import core
from cdist import resolver


class ConfigInstall(object):
    """Cdist main class to hold arbitrary data"""

    def __init__(self, context):

        self.context = context
        self.log = logging.getLogger(self.context.target_host)

        # Initialise local directory structure
        self.context.local.create_files_dirs()
        # Initialise remote directory structure
        self.context.remote.create_files_dirs()

        self.explorer = core.Explorer(self.context.target_host, self.context.local, self.context.remote)
        self.manifest = core.Manifest(self.context.target_host, self.context.local)
        self.code = core.Code(self.context.target_host, self.context.local, self.context.remote)

        # Add switch to disable code execution
        self.dry_run = False

    def cleanup(self):
        # FIXME: move to local?
        destination = os.path.join(self.context.local.cache_path, self.context.target_host)
        self.log.debug("Saving " + self.context.local.out_path + " to " + destination)
        if os.path.exists(destination):
            shutil.rmtree(destination)
        shutil.move(self.context.local.out_path, destination)

    def deploy_to(self):
        """Mimic the old deploy to: Deploy to one host"""

        # Old Code
        # self.stage_prepare()
        # self.stage_run()

        # New Code
        self.run()

    def deploy_and_cleanup(self):
        """Do what is most often done: deploy & cleanup"""
        start_time = time.time()
        self.deploy_to()
        self.cleanup()
        self.log.info("Finished successful run in %s seconds",
            time.time() - start_time)

    ###################################################################### 
    # New code for running on object priority (not stage priority)
    #

    def run(self):
        """The main runner"""
        self.explorer.run_global_explorers(self.context.local.global_explorer_out_path)
        self.manifest.run_initial_manifest(self.context.initial_manifest)
        self.iterate_until_finished()

    def object_list(self):
        """Short name for object list retrieval"""
        for cdist_object in core.CdistObject.list_objects(self.context.local.object_path,
                                                         self.context.local.type_path):
            yield cdist_object

    def iterate_until_finished(self):
        # Continue process until no new objects are created anymore

        objects_changed = True

        while objects_changed:
            objects_changed  = False

            for cdist_object in self.object_list():
                if not cdist_object.requirements_satisfied(cdist_object.requirements):
                    """We cannot do anything for this poor object"""
                    continue

                if cdist_object.state == core.CdistObject.STATE_UNDEF:
                    """Prepare the virgin object"""

                    self.object_prepare(cdist_object)
                    objects_changed = True

                if not cdist_object.requirements_satisfied(cdist_object.autorequire):
                    """The previous step created objects we depend on - wait for them"""
                    continue

                if cdist_object.state == core.CdistObject.STATE_PREPARED:
                    self.object_run(cdist_object)

        # Check whether all objects have been finished
        unfinished_object_names = []
        for cdist_object in self.object_list():
            if not cdist_object.state == cdist_object.STATE_DONE:
                unfinished_object_names.append(cdist_object.name)

        if unfinished_object_names:
            raise cdist.Error("The following objects could not be resolved: %s" %
                (" ".join(unfinished_object_names)))

    ###################################################################### 
    # Stages based code
    #

    def stage_prepare(self):
        """Do everything for a deploy, minus the actual code stage"""
        self.explorer.run_global_explorers(self.context.local.global_explorer_out_path)
        self.manifest.run_initial_manifest(self.context.initial_manifest)

        self.log.info("Running object manifests and type explorers")

        # Continue process until no new objects are created anymore
        new_objects_created = True
        while new_objects_created:
            new_objects_created = False
            for cdist_object in core.CdistObject.list_objects(self.context.local.object_path,
                                                         self.context.local.type_path):

                if cdist_object.state == core.CdistObject.STATE_PREPARED:
                    self.log.debug("Skipping re-prepare of object %s", cdist_object)
                    continue
                else:
                    self.object_prepare(cdist_object)
                    new_objects_created = True

    def object_prepare(self, cdist_object):
        """Prepare object: Run type explorer + manifest"""
        self.log.info("Running manifest and explorers for " + cdist_object.name)
        self.explorer.run_type_explorers(cdist_object)
        self.manifest.run_type_manifest(cdist_object)
        cdist_object.state = core.CdistObject.STATE_PREPARED

    def object_run(self, cdist_object, dry_run=False):
        """Run gencode and code for an object"""
        self.log.debug("Trying to run object " + cdist_object.name)
        if cdist_object.state == core.CdistObject.STATE_DONE:
            raise cdist.Error("Attempting to run an already finished object: %s", cdist_object)

        cdist_type = cdist_object.cdist_type

        # Generate
        self.log.info("Generating and executing code for " + cdist_object.name)
        cdist_object.code_local = self.code.run_gencode_local(cdist_object)
        cdist_object.code_remote = self.code.run_gencode_remote(cdist_object)
        if cdist_object.code_local or cdist_object.code_remote:
            cdist_object.changed = True

        # Execute
        if not dry_run:
            if cdist_object.code_local:
                self.code.run_code_local(cdist_object)
            if cdist_object.code_remote:
                self.code.transfer_code_remote(cdist_object)
                self.code.run_code_remote(cdist_object)

        # Mark this object as done
        self.log.debug("Finishing run of " + cdist_object.name)
        cdist_object.state = core.CdistObject.STATE_DONE

    def stage_run(self):
        """The final (and real) step of deployment"""
        self.log.info("Generating and executing code")

        objects = core.CdistObject.list_objects(
            self.context.local.object_path,
            self.context.local.type_path)

        dependency_resolver = resolver.DependencyResolver(objects)
        self.log.debug(pprint.pformat(dependency_resolver.dependencies))

        for cdist_object in dependency_resolver:
            self.log.debug("Run object: %s", cdist_object)
            self.object_run(cdist_object)
