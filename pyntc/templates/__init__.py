import os
import textfsm

TEMPLATE_PATH_ENV_VAR = 'NTC_TEMPLATES'


def get_template_dir():
    try:
        return os.environ[TEMPLATE_PATH_ENV_VAR]
    except KeyError:
        return os.path.realpath(os.path.dirname(__file__))


def get_template(template_name):
    template_dir = get_template_dir()
    return os.path.join(template_dir, template_name)


def get_structured_data(template_name, rawtxt):
    """Returns structured data given raw text using
    TextFSM templates
    """
    template = get_template(template_name)
    fsm = textfsm.TextFSM(open(template))
    table = fsm.ParseText(rawtxt)

    structured_data = []
    for row in table:
        temp_dict = {}
        for index, element in enumerate(row):
            temp_dict[fsm.header[index].lower()] = element
        structured_data.append(temp_dict)

    return structured_data
