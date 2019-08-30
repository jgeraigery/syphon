"""syphon.init.test_init.py

   Copyright Keithley Instruments, LLC.
   Licensed under MIT (https://github.com/tektronix/syphon/blob/master/LICENSE)

"""
from json import loads
from os.path import join
from typing import Optional

import pytest
from _pytest.fixtures import FixtureRequest
from py._path.local import LocalPath
from sortedcontainers import SortedDict

from syphon import Context
from syphon.init import init


@pytest.fixture(
    params=[
        {"0": "column1"},
        {"0": "column2", "1": "column4"},
        {"0": "column1", "1": "column3", "2": "column4"},
    ]
)
def init_schema_fixture(request: FixtureRequest) -> SortedDict:
    return SortedDict(request.param)


@pytest.fixture
def init_context_fixture(
    archive_dir: LocalPath, init_schema_fixture: SortedDict, overwrite: bool
) -> Context:
    context = Context()
    context.archive = str(archive_dir)
    context.schema = init_schema_fixture
    context.overwrite = overwrite
    return context


def test_init(init_context_fixture: Context):
    init(init_context_fixture)

    assert init_context_fixture.archive is not None
    schema_path = join(init_context_fixture.archive, init_context_fixture.schema_file)
    actual: Optional[SortedDict] = None
    with open(schema_path, "r") as f:
        actual = SortedDict(loads(f.read()))

    assert actual == init_context_fixture.schema


def test_init_fileexistserror(archive_dir: LocalPath, init_schema_fixture: SortedDict):
    context = Context()
    context.archive = str(archive_dir)
    context.overwrite = False
    context.schema = init_schema_fixture

    with open(str(archive_dir.join(context.schema_file)), mode="w") as f:
        f.write("content")

    with pytest.raises(FileExistsError):
        init(context)
