"""Installation metadata must agree with the provider code and catalogue."""

import importlib
import json
from pathlib import Path

from rom_hub.manifest import SUPPORTED_CONFIG_TYPES, load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.toml"


def test_the_host_can_parse_this_manifest():
    load_manifest(MANIFEST)


def test_config_defaults_match_their_declared_types():
    expected = {
        "str": lambda value: isinstance(value, str),
        "int": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "bool": lambda value: isinstance(value, bool),
        "list[str]": lambda value: isinstance(value, list)
        and all(isinstance(item, str) for item in value),
    }
    for key, spec in load_manifest(MANIFEST).config_schema.items():
        assert spec["type"] in SUPPORTED_CONFIG_TYPES
        if "default" in spec:
            assert expected[spec["type"]](spec["default"]), key


def test_every_capability_entrypoint_resolves_to_a_class():
    for capability, entrypoint in load_manifest(MANIFEST).capabilities.items():
        module_name, _, attribute = entrypoint.partition(":")
        target = getattr(importlib.import_module(module_name), attribute, None)
        assert isinstance(target, type), capability


def test_catalog_matches_the_installable_manifest():
    manifest = load_manifest(MANIFEST)
    entry = json.loads((ROOT / "catalog" / "plugins.json").read_text(
        encoding="utf-8"))["plugins"][0]
    assert entry["slug"] == manifest.slug
    assert entry["version"] == manifest.version
    assert entry["rpp_version"] == manifest.rpp_version
    assert sorted(entry["capabilities"]) == sorted(manifest.capabilities)
    assert sorted(entry["network"]) == sorted(manifest.network)
