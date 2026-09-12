"""Offline contract tests for PRTS export discovery and model compatibility."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'ark-codex-skill/scripts/export_pet.py'
spec=importlib.util.spec_from_file_location('direct_export',SCRIPT)
export=importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def test_model_version_binary_and_json():
    assert export.model_version(b'\x04abc\x073.8.99')=='3.8.99'
    assert export.model_version(b'{"skeleton":{"spine":"4.1.0"}}')=='4.1.0'
    with pytest.raises(ValueError): export.model_version(b'\x7ftruncated')


def test_atlas_pages_preserve_exact_names():
    atlas='\nfirst.png\nsize: 512,512\nregion\n  rotate: false\n\ntextures/second.png\nsize: 512,512\n'
    assert export.atlas_pages(atlas)==['first.png','textures/second.png']
    with pytest.raises(ValueError): export.atlas_pages('../escape.png\nsize: 1,1')


def test_five_required_animations_and_optional_special():
    animations=[{'name':name,'duration':1} for name in export.STATES]
    assert len(export.selected_animations(animations))==5
    animations[1]['duration']=6.300000190734863
    selected=export.selected_animations(animations)
    assert next(a['count'] for a in selected if a['name']=='Interact')==126
    animations[1]['duration']=6.32
    selected=export.selected_animations(animations)
    assert next(a['count'] for a in selected if a['name']=='Interact')==127
    animations.append({'name':'Default','duration':0})
    assert len(export.selected_animations(animations))==5
    animations.append({'name':'Special','duration':12.8999996185})
    assert export.selected_animations(animations)[-1]['count']==258
    animations[-1]['duration']=0
    with pytest.raises(ValueError,match='Special'): export.selected_animations(animations)
    with pytest.raises(ValueError,match='Missing'): export.selected_animations([])


def test_runtime_files_match_recorded_checksums():
    assert export.verify_runtime(export.RUNTIME)['family']=='3.8'


def test_optional_special_validates_and_corruption_fails(make_pet,tmp_path):
    from ark_deskpet.manifest import validate_manifest, ManifestError
    from conftest import png_bytes
    pet=make_pet(tmp_path)
    assert 'special' not in validate_manifest(pet)['states']
    manifest=json.loads((pet/'manifest.json').read_text())
    manifest['states']['special']=dict(manifest['states']['idle'])
    (pet/'manifest.json').write_text(json.dumps(manifest))
    frames=pet/'frames/special'; frames.mkdir()
    (frames/'frame_0000.png').write_bytes(png_bytes())
    assert 'special' in validate_manifest(pet)['states']
    (frames/'frame_0000.png').write_bytes(b'broken')
    with pytest.raises(ManifestError): validate_manifest(pet)
