import json


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


# support three types of files: single item json, search results json with
# multiple items in "results" property, and XML metadata with no item JSON
def find_items(file) -> list:
    if file.endswith(".json"):
        with open(file) as f:
            data = json.load(f)
            if data.get("results"):
                return data["results"]
            else:
                return [data]
    elif file.endswith(".xml"):
        with open(file) as f:
            xml = f.read()
            return [{"metadata": xml}]
    else:
        print(
            f'find_items: not sure what to do with "{file}" that is not .json or .xml, skipping'
        )
        return []
