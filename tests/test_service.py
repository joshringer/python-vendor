"""Tests for vendor.service module."""
import json
import os.path

from vendor import service


def data_filepath(filename):
    """Get path to data file."""
    return os.path.join(os.path.dirname(__file__), 'data', filename)


def test_parse_stack_outputs():
    """Test parse_stack_outputs function."""
    with open(data_filepath('describe-stacks-vendor.json')) as fp:
        example = json.load(fp)['Stacks'][0]

    output = service.parse_stack_outputs(example)
    expected = {
        'Version': '0.1',
        'ServiceURL': 'https://abcdef1234.execute-api.region.amazonaws.com/api/',
    }
    assert output == expected
