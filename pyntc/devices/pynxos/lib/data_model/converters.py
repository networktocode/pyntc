import sys
import collections

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

def convert_dict_by_key(original, key_map, fill_in=False, whitelist=[], blacklist=[]):
    converted = {}
    for converted_key in key_map:
        original_key = key_map[converted_key]
        if original_key in original:
            converted[converted_key] = original[original_key]
        else:
            converted[converted_key] = None

    if fill_in:
        original_key_subset = []

        if whitelist:
            original_key_subset.extend(list(set(whitelist) - set(key_map.values())))
        else:
            original_key_subset.extend(list(set(original.keys()) - set(blacklist) - set(key_map.values())))

        for original_key in original_key_subset:
            if original_key in original:
                converted[original_key] = original[original_key]

    return converted

def convert_list_by_key(original_list, key_map, fill_in=False, whitelist=[], blacklist=[]):
    converted_list = []
    for original in original_list:
        converted_list.append(
            convert_dict_by_key(original,
                                key_map,
                                fill_in=fill_in,
                                whitelist=whitelist,
                                blacklist=blacklist))

    return converted_list

def list_from_table(table, list_name):
    if table is None:
        return []

    table_key = u'TABLE_%s' % list_name
    row_key = u'ROW_%s' % list_name

    the_list = table[table_key][row_key]

    if not isinstance(the_list, list):
        the_list = [the_list]

    return the_list

def converted_list_from_table(table, list_name, key_map, fill_in=False, whitelist=[], blacklist=[]):
    from_table_list = list_from_table(table, list_name)
    converted_list = convert_list_by_key(from_table_list,
                                         key_map,
                                         fill_in=fill_in,
                                         whitelist=whitelist,
                                         blacklist=blacklist)

    return converted_list