# Copyright 2021 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import annotations

from dataclasses import dataclass

from pants.engine.fs import Digest, DigestEntries, DigestSubset, FileDigest, FileEntry, PathGlobs
from pants.engine.rules import Get, collect_rules, rule


@dataclass(frozen=True)
class ExtractFileDigest:
    digest: Digest
    file_path: str


@rule
async def digest_to_file_digest(request: ExtractFileDigest) -> FileDigest:
    digest = await Get(Digest, DigestSubset(request.digest, PathGlobs([request.file_path])))
    files_or_directories = await Get(DigestEntries, Digest, digest)
    digest_entries = [entry for entry in files_or_directories if isinstance(entry, FileEntry)]

    if len(digest_entries) == 0:
        raise Exception(f"ExtractFileDigest: '{request.file_path}' not found in {request.digest}.")
    elif len(digest_entries) > 1:
        raise Exception(
            f"ExtractFileDigest: Unexpected error: '{request.file_path}' found multiple times in {request.digest}"
        )

    file_info = digest_entries[0]
    return file_info.file_digest


def rules():
    return [*collect_rules()]
