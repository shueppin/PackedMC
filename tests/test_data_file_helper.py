import logging

from utils.data_file_helper import Data, SingleInstanceData, SingleModData, AdvancedArgumentsData, SettingsData, DEFAULT_INSTANCE_NAME

from . import fake_file_paths as paths
from .helpers import make_data_file_contents, make_instance_dict, make_mod_dict, read_json, write_data_file, write_json


def test_creating_data_without_a_file_creates_data_json_with_defaults():
    assert not paths.DATA_FILE_PATH.exists()

    data = Data(paths.DATA_FILE_PATH)

    assert paths.DATA_FILE_PATH.exists()
    stored = read_json(paths.DATA_FILE_PATH)
    assert stored['instances'] == {} and stored['mods'] == {} and stored['tags'] == [] and stored['last_played_instance'] == ''
    assert stored['settings'] == {'theme': 'green', 'invert_secondary': False, 'use_dark_theme': True, 'scale': 0, 'close_packedmc': True}
    assert data.settings == SettingsData()


def test_default_instance_name_and_minecraft_directory():
    assert DEFAULT_INSTANCE_NAME == 'Latest Release'
    assert SingleInstanceData().minecraft_directory == str(paths.MINECRAFT_DIRECTORY)


def test_existing_file_is_loaded_into_dataclasses():
    write_data_file(make_data_file_contents(
        instances={'Survival': make_instance_dict(type='Fabric', version='1.21.4', mods={'Fabric API': ['https://x/y.jar', 'y.jar', 5]}, is_favourite=True)},
        mods={'Fabric API': make_mod_dict(url='https://modrinth.com/mod/fabric-api', loaders=['Fabric'], supported_versions=['1.21.4'], tags=['Library'])},
        tags=['Library'],
        settings={'theme': 'blue', 'scale': 2, 'close_packedmc': False},
    ))

    data = Data(paths.DATA_FILE_PATH)

    assert data.last_played_instance == 'Survival'
    instance = data.instances['Survival']
    assert isinstance(instance, SingleInstanceData)
    assert (instance.type, instance.version, instance.is_favourite) == ('Fabric', '1.21.4', True)
    assert instance.mods == {'Fabric API': ['https://x/y.jar', 'y.jar', 5]}  # JSON has no tuples
    assert isinstance(instance.advanced_arguments, AdvancedArgumentsData)  # Missing in the file -> default values
    assert isinstance(data.mods['Fabric API'], SingleModData)
    assert data.mods['Fabric API'].tags == ['Library']
    assert data.tags == ['Library']
    assert (data.settings.theme, data.settings.scale, data.settings.close_packedmc) == ('blue', 2, False)
    assert data.settings.use_dark_theme is True  # Not in the file -> default


def test_nested_advanced_arguments_are_loaded():
    write_data_file(make_data_file_contents(instances={'A': make_instance_dict(advanced_arguments={'start_heap_size': 4, 'max_heap_size': 8, 'other_arguments': '-Dfoo=bar'})}))

    arguments = Data(paths.DATA_FILE_PATH).instances['A'].advanced_arguments

    assert isinstance(arguments, AdvancedArgumentsData)
    assert (arguments.start_heap_size, arguments.max_heap_size, arguments.other_arguments) == (4, 8, '-Dfoo=bar')


def test_old_xml_theme_names_are_replaced():
    write_data_file(make_data_file_contents(settings={'theme': 'dark_amber.xml'}))
    assert Data(paths.DATA_FILE_PATH).settings.theme == 'green'


def test_unknown_keys_in_the_file_are_ignored():
    write_data_file({'something_new': 1, 'instances': {}})
    data = Data(paths.DATA_FILE_PATH)
    assert not hasattr(data, 'something_new')


def test_changes_survive_save_and_reload():
    data = Data(paths.DATA_FILE_PATH)
    data.instances['New'] = SingleInstanceData(type='Release', version='1.20.1')
    data.mods['Mod'] = SingleModData(url='https://modrinth.com/mod/sodium', loaders=['Fabric'])
    data.settings.theme = 'pink'
    data.tags.append('Tag')
    data.save()

    reloaded = Data(paths.DATA_FILE_PATH)

    assert reloaded.instances['New'].version == '1.20.1'
    assert reloaded.mods['Mod'].loaders == ['Fabric']
    assert reloaded.settings.theme == 'pink'
    assert reloaded.tags == ['Tag']


def test_lists_are_written_on_a_single_line():
    data = Data(paths.DATA_FILE_PATH)
    data.mods['Mod'] = SingleModData(loaders=['Fabric', 'Quilt'])
    data.save()

    assert '"loaders": ["Fabric", "Quilt"]' in paths.DATA_FILE_PATH.read_text()


def test_corrupt_file_is_reported_and_defaults_are_used(caplog):
    paths.DATA_FILE_PATH.write_text('{ this is not json')

    with caplog.at_level(logging.ERROR):
        data = Data(paths.DATA_FILE_PATH)

    assert 'Error loading dictionary' in caplog.text
    assert data.instances == {} and data.settings == SettingsData()


def test_non_dictionary_for_a_dictionary_attribute_is_reported(caplog):
    write_data_file({'mods': ['not', 'a', 'dict'], 'instances': {}})

    with caplog.at_level(logging.WARNING):
        data = Data(paths.DATA_FILE_PATH)

    assert 'not a dictionary' in caplog.text
    assert data.mods == {}


def test_path_objects_are_saved_as_strings_with_a_warning(caplog):
    data = Data(paths.DATA_FILE_PATH)
    data.instances['A'] = SingleInstanceData(minecraft_directory=paths.MINECRAFT_DIRECTORY)  # Wrong type on purpose

    with caplog.at_level(logging.WARNING):
        data.save()

    assert 'is a pathlib.Path' in caplog.text
    assert read_json(paths.DATA_FILE_PATH)['instances']['A']['minecraft_directory'] == str(paths.MINECRAFT_DIRECTORY)


def test_load_replaces_the_in_memory_data():
    data = Data(paths.DATA_FILE_PATH)
    write_json(paths.DATA_FILE_PATH, make_data_file_contents(instances={'FromDisk': make_instance_dict()}))

    data.load()

    assert list(data.instances) == ['FromDisk']
