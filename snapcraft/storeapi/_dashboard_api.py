# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2016-2021 Canonical Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import os
import urllib.parse
from typing import List, Optional

import requests
from simplejson.scanner import JSONDecodeError

from . import _macaroon_auth, _metadata, constants, errors, logger
from .v2 import channel_map, releases
from ._client import Client
from ._status_tracker import StatusTracker


class DashboardAPI(Client):
    """The Dashboard API is used to publish and manage snaps.

    This is an interface to query that API which is documented
    at https://dashboard.snapcraft.io/docs/.
    """

    def __init__(self, conf):
        super().__init__(
            conf, os.environ.get("STORE_DASHBOARD_URL", constants.STORE_DASHBOARD_URL),
        )

    def get_macaroon(self, acls, packages=None, channels=None, expires=None):
        data = {"permissions": acls}
        if packages is not None:
            data.update({"packages": packages})
        if channels is not None:
            data.update({"channels": channels})
        if expires is not None:
            data.update({"expires": expires})
        headers = {"Accept": "application/json"}
        response = self.post("/dev/api/acl/", json=data, headers=headers)
        if response.ok:
            return response.json()["macaroon"]
        else:
            raise errors.StoreAuthenticationError("Failed to get macaroon", response)

    @staticmethod
    def _is_needs_refresh_response(response):
        return (
            response.status_code == requests.codes.unauthorized
            and response.headers.get("WWW-Authenticate") == "Macaroon needs_refresh=1"
        )

    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        if self._is_needs_refresh_response(response):
            raise errors.StoreMacaroonNeedsRefreshError()
        return response

    def verify_acl(self):
        auth = _macaroon_auth(self.conf)
        response = self.post(
            "/dev/api/acl/verify/",
            json={"auth_data": {"authorization": auth}},
            headers={"Accept": "application/json"},
        )
        if response.ok:
            return response.json()
        else:
            raise errors.StoreAccountInformationError(response)

    def get_account_information(self):
        auth = _macaroon_auth(self.conf)
        response = self.get(
            "/dev/api/account",
            headers={"Authorization": auth, "Accept": "application/json"},
        )
        if response.ok:
            return response.json()
        else:
            raise errors.StoreAccountInformationError(response)

    def register_key(self, account_key_request):
        data = {"account_key_request": account_key_request}
        auth = _macaroon_auth(self.conf)
        response = self.post(
            "/dev/api/account/account-key",
            data=json.dumps(data),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if not response.ok:
            raise errors.StoreKeyRegistrationError(response)

    def register(
        self, snap_name: str, *, is_private: bool, series: str, store_id: str
    ) -> None:
        auth = _macaroon_auth(self.conf)
        data = dict(snap_name=snap_name, is_private=is_private, series=series)
        if store_id is not None:
            data["store"] = store_id
        response = self.post(
            "/dev/api/register-name/",
            data=json.dumps(data),
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )
        if not response.ok:
            raise errors.StoreRegistrationError(snap_name, response)

    def snap_upload_precheck(self, snap_name):
        data = {"name": snap_name, "dry_run": True}
        auth = _macaroon_auth(self.conf)
        response = self.post(
            "/dev/api/snap-push/",
            data=json.dumps(data),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if not response.ok:
            raise errors.StoreUploadError(snap_name, response)

    def snap_upload_metadata(
        self,
        snap_name,
        updown_data,
        delta_format=None,
        delta_hash=None,
        source_hash=None,
        target_hash=None,
        built_at=None,
        channels: Optional[List[str]] = None,
    ) -> StatusTracker:
        data = {
            "name": snap_name,
            "series": constants.DEFAULT_SERIES,
            "updown_id": updown_data["upload_id"],
            "binary_filesize": updown_data["binary_filesize"],
            "source_uploaded": updown_data["source_uploaded"],
        }
        if delta_format:
            data["delta_format"] = delta_format
            data["delta_hash"] = delta_hash
            data["source_hash"] = source_hash
            data["target_hash"] = target_hash
        if built_at is not None:
            data["built_at"] = built_at
        if channels is not None:
            data["channels"] = channels
        auth = _macaroon_auth(self.conf)
        response = self.post(
            "/dev/api/snap-push/",
            data=json.dumps(data),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if not response.ok:
            raise errors.StoreUploadError(data["name"], response)

        return StatusTracker(response.json()["status_details_url"])

    def upload_metadata(self, snap_id, snap_name, metadata, force):
        """Upload the metadata to SCA."""
        metadata_handler = _metadata.StoreMetadataHandler(
            self, _macaroon_auth(self.conf), snap_id, snap_name
        )
        metadata_handler.upload(metadata, force)

    def upload_binary_metadata(self, snap_id, snap_name, metadata, force):
        """Upload the binary metadata to SCA."""
        metadata_handler = _metadata.StoreMetadataHandler(
            self, _macaroon_auth(self.conf), snap_id, snap_name
        )
        metadata_handler.upload_binary(metadata, force)

    def snap_release(
        self,
        snap_name,
        revision,
        channels,
        delta_format=None,
        progressive_percentage: Optional[int] = None,
    ):
        data = {"name": snap_name, "revision": str(revision), "channels": channels}
        if delta_format:
            data["delta_format"] = delta_format
        if progressive_percentage is not None:
            data["progressive"] = {
                "percentage": progressive_percentage,
                "paused": False,
            }
        auth = _macaroon_auth(self.conf)
        response = self.post(
            "/dev/api/snap-release/",
            data=json.dumps(data),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if not response.ok:
            raise errors.StoreReleaseError(data["name"], response)

        response_json = response.json()

        return response_json

    def push_assertion(self, snap_id, assertion, endpoint, force):
        if endpoint == "validations":
            data = {"assertion": assertion.decode("utf-8")}
        elif endpoint == "developers":
            data = {"snap_developer": assertion.decode("utf-8")}
        auth = _macaroon_auth(self.conf)

        url = "/dev/api/snaps/{}/{}".format(snap_id, endpoint)

        # For `snap-developer`, revoking developers will require their uploads
        # to be invalidated.
        if force:
            url = url + "?ignore_revoked_uploads"

        response = self.put(
            url,
            data=json.dumps(data),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        if not response.ok:
            raise errors.StoreValidationError(snap_id, response)
        try:
            response_json = response.json()
        except JSONDecodeError:
            message = (
                "Invalid response from the server when pushing validations: {} {}"
            ).format(response.status_code, response)
            logger.debug(message)
            raise errors.StoreValidationError(
                snap_id, response, message="Invalid response from the server"
            )

        return response_json

    def get_assertion(self, snap_id, endpoint, params=None):
        auth = _macaroon_auth(self.conf)
        response = self.get(
            "/dev/api/snaps/{}/{}".format(snap_id, endpoint),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            params=params,
        )
        if not response.ok:
            raise errors.StoreValidationError(snap_id, response)
        try:
            response_json = response.json()
        except JSONDecodeError:
            message = "Invalid response from the server when getting {}: {} {}".format(
                endpoint, response.status_code, response
            )
            logger.debug(message)
            raise errors.StoreValidationError(
                snap_id, response, message="Invalid response from the server"
            )

        return response_json

    def push_snap_build(self, snap_id, snap_build):
        url = "/dev/api/snaps/{}/builds".format(snap_id)
        data = json.dumps({"assertion": snap_build})
        headers = {
            "Authorization": _macaroon_auth(self.conf),
            "Content-Type": "application/json",
        }
        response = self.post(url, data=data, headers=headers)
        if not response.ok:
            raise errors.StoreSnapBuildError(response)

    def snap_status(self, snap_id, series, arch):
        qs = {}
        if series:
            qs["series"] = series
        if arch:
            qs["architecture"] = arch
        url = "/dev/api/snaps/" + snap_id + "/state"
        if qs:
            url += "?" + urllib.parse.urlencode(qs)
        auth = _macaroon_auth(self.conf)
        response = self.get(
            url,
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if not response.ok:
            raise errors.StoreSnapStatusError(response, snap_id, series, arch)

        response_json = response.json()

        return response_json

    def close_channels(self, snap_id, channel_names):
        url = "/dev/api/snaps/{}/close".format(snap_id)
        data = {"channels": channel_names}
        headers = {"Authorization": _macaroon_auth(self.conf)}
        response = self.post(url, json=data, headers=headers)
        if not response.ok:
            raise errors.StoreChannelClosingError(response)

        try:
            results = response.json()
            return results["closed_channels"], results["channel_map_tree"]
        except (JSONDecodeError, KeyError):
            logger.debug(
                "Invalid response from the server on channel closing:\n"
                "{} {}\n{}".format(
                    response.status_code, response.reason, response.content
                )
            )
            raise errors.StoreChannelClosingError(response)

    def sign_developer_agreement(self, latest_tos_accepted=False):
        auth = _macaroon_auth(self.conf)
        data = {"latest_tos_accepted": latest_tos_accepted}
        response = self.post(
            "/dev/api/agreement/",
            data=json.dumps(data),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        if not response.ok:
            raise errors.DeveloperAgreementSignError(response)
        return response.json()

    def get_snap_channel_map(self, *, snap_name: str) -> channel_map.ChannelMap:
        url = f"/api/v2/snaps/{snap_name}/channel-map"
        auth = _macaroon_auth(self.conf)
        response = self.get(
            url,
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        if not response.ok:
            raise errors.StoreSnapChannelMapError(snap_name=snap_name)

        return channel_map.ChannelMap.unmarshal(response.json())

    def get_snap_releases(self, *, snap_name: str) -> releases.Releases:
        url = f"/api/v2/snaps/{snap_name}/releases"
        auth = _macaroon_auth(self.conf)
        response = self.get(
            url,
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        if not response.ok:
            raise errors.StoreSnapChannelMapError(snap_name=snap_name)

        return releases.Releases.unmarshal(response.json())
