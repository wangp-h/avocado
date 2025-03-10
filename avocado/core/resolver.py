# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2019
# Authors: Cleber Rosa <crosa@redhat.com>

"""
Test resolver module.
"""

import glob
import os
import stat
from enum import Enum

from avocado.core.enabled_extension_manager import EnabledExtensionManager
from avocado.core.exceptions import JobTestSuiteReferenceResolutionError
from avocado.core.output import LOG_UI


class ReferenceResolutionAssetType(Enum):
    #: The actual test file.  Spawners may use this as the entry point
    #: to run the tests.  Usually only one of this is given, and the
    #: behavior with either a single or multiple items given is spawner
    #: dependent.
    TEST_FILE = "test_file"
    #: Auxiliary data file placed alongside the test in a ".data"
    #: directory
    DATA_FILE = "data_file"


class ReferenceResolutionResult(Enum):
    #: Given test reference was properly resolved
    SUCCESS = object()
    #: Given test reference might be resolved, but it is corrupted.
    CORRUPT = object()
    #: Given test reference was not properly resolved
    NOTFOUND = object()
    #: Internal error in the resolution process
    ERROR = object()


class ReferenceResolutionAction(Enum):
    #: Stop trying to resolve the reference
    RETURN = object()
    #: Continue to resolve the given reference
    CONTINUE = object()


class ReferenceResolution:
    """
    Represents one complete reference resolution

    Note that the reference itself may result in many resolutions, or
    none.
    """

    def __init__(self, reference, result, resolutions=None, info=None, origin=None):
        """
        :param reference: a specification that can eventually be resolved
                          into a test (in the form of a
                          :class:`avocado.core.nrunner.Runnable`)
        :type reference: str
        :param result: if the complete resolution was a success,
                       failure or error
        :type result: :class:`ReferenceResolutionResult`
        :param resolutions: the runnable definitions resulting from the
                            resolution
        :type resolutions: list of :class:`avocado.core.nrunner.Runnable`
        :param info: free form information the resolver may add
        :type info: str
        :param origin: the name of the resolver that performed the resolution
        :type origin: str
        """
        self.reference = reference
        self.result = result
        if resolutions is None:
            resolutions = []
        self.resolutions = resolutions
        self.info = info
        self.origin = origin

    def __repr__(self):
        fmt = (
            '<ReferenceResolution reference="{}" result="{}" '
            'resolutions="{}" info="{}" origin="{}">'
        )
        return fmt.format(
            self.reference, self.result, self.resolutions, self.info, self.origin
        )


class Resolver(EnabledExtensionManager):
    """
    Main test reference resolution utility.

    This performs the actual resolution according to the active
    resolver plugins and a resolution policy.
    """

    PLUGIN_DESCRIPTION = "Plugins that resolve test references (resolver)"

    DEFAULT_POLICY = {
        ReferenceResolutionResult.SUCCESS: ReferenceResolutionAction.RETURN,
        ReferenceResolutionResult.CORRUPT: ReferenceResolutionAction.RETURN,
        ReferenceResolutionResult.NOTFOUND: ReferenceResolutionAction.CONTINUE,
        ReferenceResolutionResult.ERROR: ReferenceResolutionAction.CONTINUE,
    }

    def __init__(self, config=None):
        super().__init__("avocado.plugins.resolver", invoke_kwds={"config": config})

    def resolve(self, reference):
        resolution = []
        for ext in self.extensions:
            try:
                result = ext.obj.resolve(reference)
                if not result.origin:
                    result.origin = ext.name
            except Exception as exc:  # pylint: disable=W0703
                result = ReferenceResolution(
                    reference,
                    ReferenceResolutionResult.ERROR,
                    info=exc,
                    origin=ext.name,
                )
            resolution.append(result)
            action = self.DEFAULT_POLICY.get(
                result.result, ReferenceResolutionAction.CONTINUE
            )
            if action == ReferenceResolutionAction.RETURN:
                break
        return resolution


class Discoverer(EnabledExtensionManager):
    """
    Secondary test reference resolution utility.

    When the user didn't provide any test references, Discoverer will discover
    tests from different data according to active discoverer plugins.
    """

    PLUGIN_DESCRIPTION = "Plugins that discover tests without references (discoverer)"

    def __init__(self, config=None):
        super().__init__("avocado.plugins.discoverer", invoke_kwds={"config": config})

    def discover(self):
        resolutions = []
        for ext in self.extensions:
            try:
                results = ext.obj.discover()
            except Exception as exc:  # pylint: disable=W0703
                results = [
                    ReferenceResolution(
                        "", ReferenceResolutionResult.ERROR, info=exc, origin=ext.name
                    )
                ]
            for result in results:
                if not result.origin:
                    result.origin = ext.name
                resolutions.append(result)

        return resolutions


def check_file(
    path,
    reference,
    suffix=".py",
    type_check=os.path.isfile,
    type_name="regular file",
    access_check=os.R_OK,
    access_name="readable",
):
    if suffix is not None:
        if not path.endswith(suffix):
            return ReferenceResolution(
                reference,
                ReferenceResolutionResult.NOTFOUND,
                info=f'File name "{path}" does not end with suffix "{suffix}"',
            )

    if not type_check(path):
        return ReferenceResolution(
            reference,
            ReferenceResolutionResult.NOTFOUND,
            info=f'File "{path}" does not exist or is not a {type_name}',
        )

    st = os.stat(path)

    user_permissions = st.st_mode & (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    # Initialize required permissions to 0, indicating no permissions are needed yet
    required_permissions = 0

    # Build the required permissions based on access_check
    if access_check & os.R_OK:
        # If read access needs to be checked, set the corresponding user read permission bit
        required_permissions |= stat.S_IRUSR
    if access_check & os.W_OK:
        # If write access needs to be checked, set the corresponding user write permission bit
        required_permissions |= stat.S_IWUSR
    if access_check & os.X_OK:
        # If execute access needs to be checked, set the corresponding user execute permission bit
        required_permissions |= stat.S_IXUSR

    # Check if the user has the required permissions
    if (user_permissions & required_permissions) != required_permissions:
        # If the bitwise AND of user permissions and required permissions is not equal to required permissions,
        # it means the user is missing some permissions
        return ReferenceResolution(
            reference,
            ReferenceResolutionResult.NOTFOUND,
            info=f'File "{path}" does not have the required {access_name} permissions',
        )

    return True


def get_file_assets(test_file_path):
    """Gets asset files from the test file and its the ".data" directory

    :param test_file_path: the filesystem location of the test file
    :type test_file_path: str
    :returns: list of tuples with (asset type, path)
    """
    file_assets = [(ReferenceResolutionAssetType.TEST_FILE, test_file_path)]
    for data_file in glob.glob(os.path.join(f"{test_file_path}.data", "*")):
        file_assets.append((ReferenceResolutionAssetType.DATA_FILE, data_file))
    return file_assets


def _extend_directory(path):
    if not os.path.isdir(path):
        return [path]
    paths = []
    # no error handling so far
    for dirpath, dirs, filenames in os.walk(path):
        dirs.sort()
        for file_name in sorted(filenames):
            # does it make sense to ignore hidden files here?
            if file_name.startswith("."):
                continue
            pth = os.path.join(dirpath, file_name)
            paths.append(pth)
    if not paths:
        paths = [path]
    return paths


def resolve(references, hint=None, ignore_missing=True, config=None):
    resolutions = []
    hint_references = {}

    if hint:
        hint_references = {r.reference: r for r in hint.get_resolutions()}

    if not references and hint_references:
        references = list(hint_references.keys())

    if references:
        # should be initialized with args, to define the behavior
        # of this instance as a whole
        resolver = Resolver(config)
        extended_references = []
        for reference in references:
            # a reference extender is not (yet?) an extensible feature
            # here it walks directories if one is given, and extends
            # the original reference into final file paths
            extended_references.extend(_extend_directory(reference))
        for reference in extended_references:
            if reference in hint_references:
                resolutions.append(hint_references[reference])
            else:
                resolutions.extend(resolver.resolve(reference))
    else:
        discoverer = Discoverer(config)
        resolutions.extend(discoverer.discover())

    for res in resolutions:
        if res.result == ReferenceResolutionResult.CORRUPT:
            LOG_UI.warning(
                "Reference %s might be resolved by %s resolver, but the file is corrupted: %s",
                res.reference,
                res.origin,
                res.info or "",
            )
    # This came up from a previous method and can be refactored to improve
    # performance since that we could merge with the loop above.
    if not ignore_missing:
        missing = []
        for reference in references:
            results = [res.result for res in resolutions if res.reference == reference]
            if ReferenceResolutionResult.SUCCESS not in results:
                missing.append(reference)
        # directories are automatically expanded, and thus they can
        # not be considered a reference that needs to exist after the
        # resolution process
        missing = [_ for _ in missing if not os.path.isdir(_)]
        if missing:
            msg = (
                f"No tests found for given test references: {', '.join(missing)}\n"
                f"Try 'avocado -V list {' '.join(missing)}' for details"
            )
            raise JobTestSuiteReferenceResolutionError(msg)

    return resolutions
