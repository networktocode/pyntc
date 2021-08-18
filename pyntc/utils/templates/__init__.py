"""Module to use NTC_TEMPLATES."""
import os
import textfsm


TEMPLATE_PATH_ENV_VAR = "NTC_TEMPLATES"


def get_structured_data(template_name, rawtxt):
    """Return structured data given raw text using TextFSM templates.

    Args:
        template_name (str): Name of template to use.
        rawtxt (str): Raw output from device.

    Returns:
        list: A dict per entry returned by TextFSM.
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
    """Path to the template passed in.

    Args:
        template_name (str): Name of the template.

    Returns:
        str: Path to the template.
    """
    template_dir = get_template_dir()
    return os.path.join(template_dir, template_name)


def get_template_dir():
    """Get directory of NTC_TEMPLATE os environment.

    Returns:
        str: Path to NTC_TEMPLATES environment variable if set. Otherwise, path to this file.
    """
    try:
        return os.environ[TEMPLATE_PATH_ENV_VAR]
    except KeyError:
        return os.path.realpath(os.path.dirname(__file__))
