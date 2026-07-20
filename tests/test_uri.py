from pathlib import Path

from fsharp_lsp import uri_to_path


def test_plain_file_uri():
    assert uri_to_path("file:///home/u/Proj/Library.fs") == Path("/home/u/Proj/Library.fs")


def test_percent_encoded_space_is_decoded():
    assert uri_to_path("file:///home/u/My%20Proj/Library.fs") == Path("/home/u/My Proj/Library.fs")


def test_percent_encoded_hash_is_decoded():
    assert uri_to_path("file:///home/u/C%23Interop/Library.fs") == Path("/home/u/C#Interop/Library.fs")
