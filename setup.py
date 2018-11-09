import re
from setuptools import find_packages, setup

with open("pyntc/__init__.py") as pkg_init:
    # Create a dict of all dunder vars and their values in package __init__
    metadata = dict(re.findall("__(\w+)__\s*=\s*\"(\S+?)\"", pkg_init.read()))

name = "pyntc"
version = metadata["version"]
packages = find_packages()
package_data = {"pyntc": ["templates/*.template", "devices/tables/jnpr/*.yml"]}

install_requires = [
    "requests>=2.7.0",
    "jsonschema",
    "future",
    "netmiko",
    "paramiko",
    "pynxos>=0.0.3",
    "coverage",
    "mock>=1.3",
    "textfsm",
    "terminal",
    "f5-sdk",
    "bigsuds",
    "pyeapi",
    "junos-eznc",
    "scp",
]

dependency_links = []

author = "Network To Code"
author_email = "ntc@networktocode.com"
url = "https://github.com/networktocode/pyntc"
download_url = "https://github.com/networktocode/pyntc/tarball/{}".format(version)
description = "A multi-vendor library for managing network devices."

setup(
    name=name,
    version=version,
    packages=packages,
    package_data=package_data,
    install_requires=install_requires,
    dependency_links=dependency_links,
    url=url,
    download_url=download_url,
    author=author,
    author_email=author_email,
    description=description,
)
