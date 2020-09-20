"""Provides methods for manipulating and converting data."""


def convert_dict_by_key(original, key_map, fill_in=False, whitelist=[], blacklist=[]):
    """Use a key map to convert a dictionary to desired keys.

    Args:
        original (dict): Original dictionary to be converted.
        key_map (dict): Key map to use to convert dictionary.
        fill_in (dict): Whether the returned dictionary should contain
            keys and values from the original dictionary if not specified in the key map.
        whitelist: If fill_in is True, and whitelist isn't empty, only fill in the keys
            in the whitelist in the returned dictionary.
        blacklist: If fill_in is True, and blacklist isn't empty, fill in with all keys from
            the original dictionary besides those in the blacklist.

    Returns:
        A converted dictionary through the key map.
    """
    converted = {}
    for converted_key in key_map:
        original_key = key_map[converted_key]

        converted[converted_key] = recursive_key_lookup(original_key, original)

    if fill_in:
        original_key_subset = []

        # ignore complex values in key map
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
    """Apply a dictionary conversion for all dictionaries in original_list."""
    converted_list = []
    for original in list(original_list):
        converted_list.append(
            convert_dict_by_key(original, key_map, fill_in=fill_in, whitelist=whitelist, blacklist=blacklist)
        )

    return converted_list


def recursive_key_lookup(keys, obj):
    """Return obj[keys] if keys is actually a single key.
    Otherwise return obj[keys[0]][keys[1]]...[keys[n]] if keys is a list."""
    if not isinstance(keys, list):
        return obj.get(keys)

    for key in keys:
        if obj is not None:
            obj = obj.get(key)

    return obj
