import collections
import sys

def strip_unicode(data):
    if sys.version_info.major >= 3:
        return data

    if isinstance(data, basestring):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(map(strip_unicode, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(strip_unicode, data))
    else:
        return data

def recursive_key_lookup(keys, obj):
    if not isinstance(keys, list):
        return obj.get(keys)

    for key in keys:
        if obj is not None:
            obj = obj.get(key)

    return obj


def convert_dict_by_key(original, key_map, fill_in=False, whitelist=[], blacklist=[]):
    converted = {}
    for converted_key in key_map:
        original_key = key_map[converted_key]

        converted[converted_key] = recursive_key_lookup(original_key, original)

    if fill_in:
        original_key_subset = []

        #ignore complex values in key map
        key_map_values = list(x for x in key_map.values() if not isinstance(x, list))

        if whitelist:
            original_key_subset.extend(list(set(whitelist) - set(key_map_values)))
        else:
            original_key_subset.extend(list(set(original.keys()) - set(blacklist) - set(key_map_values)))

        for original_key in original_key_subset:
            if original_key in original:
                converted[original_key] = original[original_key]

    return converted

def convert_list_by_key(original_list, key_map, fill_in=False, whitelist=[], blacklist=[]):
    converted_list = []
    for original in list(original_list):
        converted_list.append(
            convert_dict_by_key(original,
                                key_map,
                                fill_in=fill_in,
                                whitelist=whitelist,
                                blacklist=blacklist))

    return converted_list