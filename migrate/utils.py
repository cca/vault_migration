def mklist(x) -> list:
    # ensure value is a list
    if type(x) == list:
        return x
    elif type(x) == str or type(x) == dict:
        return [x]
    elif x is None:
        return []
    else:
        raise TypeError(f"mklist: invalid type: {type(x)}")
