#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import glob
import subprocess

from setuptools import find_packages
from setuptools import setup

package_name = 'cube_petit_rsj_2025'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(),
    data_files=[
        ('share/' + package_name, ['package.xml']),
        (f'share/{package_name}/launch', glob.glob('./launch/*.launch.py')),
        (f'share/{package_name}/config', glob.glob('./config/*.txt')),
        (f'share/{package_name}/config', glob.glob('./config/*.md')),
        (f'share/{package_name}/config', glob.glob('./config/*.py')),
        (f'share/{package_name}/config', glob.glob('./config/*.yaml')),
    ],
    maintainer='gisen',
    maintainer_email='SBGRP-git@g.softbank.co.jp',
    description='cube_petit_rsj_2025 package',
    license='Apache License, Version2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            #   f'send_view_to_gpt = {package_name}.send_view_to_gpt:main',
            #   f'find_object = {package_name}.find_object:main',
        ],
    })
subprocess.Popen([f'{package_name}/fix_shebang.py'],
                 stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL,
                 stdin=subprocess.DEVNULL,
                 start_new_session=True)
