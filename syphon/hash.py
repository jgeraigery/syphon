"""syphon.hash.py

   Copyright Keithley Instruments, LLC.
   Licensed under MIT (https://github.com/tektronix/syphon/blob/master/LICENSE)

"""
import hashlib
from typing import Callable, Iterator, List, NamedTuple, Optional, Tuple

from _hashlib import HASH
from _io import _IOBase

from .errors import MalformedLineError

DEFAULT_HASH_TYPE: str = hashlib.sha256().name


SplitResult = NamedTuple(
    "SplitResult", [("hash", str), ("file", str), ("binary", bool)]
)


class HashEntry(object):
    def __init__(
        self, filepath: str, binary: bool = False, hash_type: Optional[str] = None
    ):
        """An object whose string value represents a valid hash entry.

        Args:
            filepath: The target of the hash operation.
            binary: Whether the target file should be read in binary mode. Defaults
                to False.
            hash_type: Name of a hash type supported by hashlib. Defaults to "sha256".

        Raises:
            ValueError: If the given hash type is unsupported by hashlib.
        """
        if hash_type is None:
            hash_type = DEFAULT_HASH_TYPE

        if hash_type not in hashlib.algorithms_available:
            raise ValueError('Unsupported hash type "{}"'.format(hash_type))

        super().__init__()
        self._hash_cache: str = ""
        self._hash_obj: HASH = hashlib.new(hash_type)
        # Used only when this object was generated by parsing a hash file.
        self._raw_entry: str = ""
        self.binary: bool = binary
        self.filepath: str = filepath

    def __str__(self) -> str:
        return " ".join(
            [self.hash, "{0}{1}".format("*" if self.binary else " ", self.filepath)]
        )

    @property
    def cached(self) -> bool:
        """Whether the hash has been cached.

        The cached hash is used to minimize the I/O overhead of multiple "hash"
        property accesses.
        """
        return self._hash_cache != ""

    @property
    def hash(self) -> str:
        """A hash calculated from the contents of the filepath.

        The initial property access caches the result of the hash operation. The cached
        value is used during subsequent accesses to minimize I/O overhead.

        Refer to the "cached" property to determine whether the cache will be used
        during the next access.
        """
        if len(self._hash_cache) > 0:
            return self._hash_cache

        new_hash = self._hash()
        self._hash_cache = new_hash
        return new_hash

    @property
    def hash_type(self) -> str:
        """The hash type used to calculate the hash.

        Type must be supported by hashlib.

        Raises:
            TypeError: If not set to a string type.
            ValueError: If the given string is not a hash supported by hashlib.
        """
        return self._hash_obj.name

    @hash_type.setter
    def hash_type(self, value: str):
        if not isinstance(value, str):
            raise TypeError("Expected {0}, received {1}".format(str, type(value)))

        if self._hash_obj.name == value:
            return

        try:
            self._hash_obj = hashlib.new(value)
        except ValueError:
            raise ValueError('Unsupported hash type "{}"'.format(value))

    def _hash(self) -> str:
        """Calculate a hash from the contents of the filepath."""
        if self.binary:
            with open(self.filepath, "rb") as binary:
                self._hash_obj.update(binary.read())
        else:
            with open(self.filepath, "rt") as text:
                self._hash_obj.update(bytes(text.read(), text.encoding))

        return self._hash_obj.hexdigest()

    @staticmethod
    def _default_line_split(line: str) -> Optional[SplitResult]:
        import re

        captures: List[Tuple[str, str]] = re.findall(
            r"^([a-fA-F0-9]+)\s+(.*)$", line.strip()
        )
        try:
            match_tuple: Tuple[str, str] = captures.pop(0)
            filepath: str = match_tuple[1]
            is_binary: bool = filepath.startswith("*")
            return SplitResult(
                hash=match_tuple[0],
                file=filepath[1:] if is_binary else filepath,
                binary=is_binary,
            )
        except IndexError:
            pass

        return None

    @staticmethod
    def from_str(
        entry: str,
        line_split: Optional[Callable[[str], Optional[SplitResult]]] = None,
        hash_type: Optional[str] = None,
    ) -> "HashEntry":
        """Create a HashEntry from a given entry string.

        Args:
            entry: The string parse into a HashEntry.
            line_split: A callable object that returns a SplitResult from a given line
                or None if the line is in an unexpected format. Returning None raises
                a MalformedLineError.
            hash_type: Name of a hash type supported by hashlib. Defaults to "sha256".

        Returns:
            HashEntry: An object wrapper for the matched hash entry.

        Raises:
            MalformedLineError: If there was trouble splitting the given entry.
        """
        if line_split is None:
            line_split = HashEntry._default_line_split

        split = line_split(entry)
        if split is None:
            raise MalformedLineError(entry.strip())

        result = HashEntry(split.file, binary=split.binary, hash_type=hash_type)
        result._hash_cache = split.hash
        result._raw_entry = entry
        return result


class _OpenHashFile(object):
    def __init__(self, file_obj: _IOBase, hash_type: str):
        self._file_obj: _IOBase = file_obj
        self.hash_type: str = hash_type
        self.line_split: Optional[Callable[[str], Optional[SplitResult]]] = None

    def __iter__(self) -> Iterator[HashEntry]:
        return self.entries()

    def append(self, entry: HashEntry):
        """Update the given hash.

        Returns the stream to its position before this method was called.

        Args:
            entry: A new entry.

        Raises:
            ValueError: If the given entry's hash type does not match this object's
                hash type.
        """
        if entry.hash_type != self.hash_type:
            raise ValueError(
                "Expected hash type {0}, but received {1}".format(
                    self.hash_type, entry.hash_type
                )
            )

        initial_position = self.tell()

        # You could compress the next 2 commands into `...seek(-1, 2)` but
        # Windows doesn't support "nonzero end-relative seeks".
        self._file_obj.seek(0, 2)
        add_newline = False
        here = self.tell()
        # Don't want to seek before position 0 nor start the file with a blank line.
        if here != 0:
            self._file_obj.seek(here - 1)
            add_newline = self._file_obj.read() != "\n"
        self._file_obj.write("{0}{1}\n".format("\n" if add_newline else "", str(entry)))

        self._file_obj.seek(initial_position)

    def close(self) -> None:
        self._file_obj.close()

    def entries(self) -> Iterator[HashEntry]:
        """Iterate through all file entries."""
        while True:
            line = self._file_obj.readline()
            if len(line) == 0:
                break
            yield HashEntry.from_str(line, self.line_split, self.hash_type)

    def tell(self) -> int:
        """Return the current stream position."""
        return self._file_obj.tell()

    def update(self, entry: HashEntry):
        """Update the given hash or append it if an existing entry is not found.

        Returns the stream to its position before this method was called.

        Args:
            entry: An existing entry with a new hash value.

        Raises:
            ValueError: If the given entry's hash type does not match this object's
                hash type.
        """
        if entry.hash_type != self.hash_type:
            raise ValueError(
                "Expected hash type {0}, but received {1}".format(
                    self.hash_type, entry.hash_type
                )
            )

        initial_position = self.tell()

        previous_position = initial_position
        for found in self.entries():
            if entry.filepath == found.filepath:
                self._file_obj.seek(previous_position)
                self._file_obj.write(entry.hash)
                break
            previous_position = self.tell()
        else:
            self.append(entry)

        self._file_obj.seek(initial_position)


class HashFile(object):
    def __init__(self, filepath: str, hash_type: Optional[str] = None):
        """A hash file context manager for use in with-blocks.

        Args:
            filepath: Path to a file containing hash entries.
            hash_type: Name of a hash type supported by hashlib. Defaults to "sha256".

        Raises:
            ValueError: If the given hash type is unsupported by hashlib.
        """
        if hash_type is None:
            hash_type = DEFAULT_HASH_TYPE

        if hash_type not in hashlib.algorithms_available:
            raise ValueError('Unsupported hash type "{}"'.format(hash_type))

        super().__init__()
        self._count: int = 0
        self._file: Optional[_OpenHashFile] = None
        self._hash_type: str = hash_type
        self.filepath: str = filepath

    def __enter__(self, *args, **kwargs) -> _OpenHashFile:
        self._count += 1
        if self._file is not None:
            return self._file
        self._file = _OpenHashFile(open(self.filepath, "r+t"), self._hash_type)
        return self._file

    def __exit__(self, *args, **kwargs) -> None:
        if self._file is not None:
            self._count -= 1
            if self._count == 0:
                self._file.close()
                self._file = None
        return None
