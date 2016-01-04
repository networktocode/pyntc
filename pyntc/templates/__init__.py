import os
import textfsm

TEMPLATE_PATH_ENV_VAR = 'NTC_TEMPLATES'

def get_template_dir():
    return os.environ[TEMPLATE_PATH_ENV_VAR]

def get_structured_data(template, rawtxt):
    """Returns structured data given raw text using
    TextFSM templates
    """

    # return os.getcwd()
    # return os.path.abspath(__file__)

    fsm = textfsm.TextFSM(open(template))

    # an object is what is being extracted
    # based on the template, it may be one object or multiple
    # as is the case with neighbors, interfaces, etc.
    objects = fsm.ParseText(rawtxt)

    structured_data = []
    for each in objects:
        index = 0
        temp = {}
        for template_value in each:
            temp[fsm.header[index].lower()] = str(template_value)
            index += 1
        structured_data.append(temp)

    return structured_data