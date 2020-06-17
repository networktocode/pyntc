import os
import textfsm


TEMPLATE_PATH_ENV_VAR = "NTC_TEMPLATES"


def get_structured_data(template_name, rawtxt):
    """Returns structured data given raw text using
    TextFSM templates
    """
    template_file = get_template(template_name)
    with open(template_file) as template:
        fsm = textfsm.TextFSM(template)
        table = fsm.ParseText(rawtxt)

        structured_data = []
        for row in table:
            entry = {fsm.header[index].lower(): element for index, element in enumerate(row)}
            structured_data.append(entry)

    return structured_data


def get_template(template_name):
    template_dir = get_template_dir()
    return os.path.join(template_dir, template_name)


def get_template_dir():
    try:
        return os.environ[TEMPLATE_PATH_ENV_VAR]
    except KeyError:
        return os.path.realpath(os.path.dirname(__file__))
