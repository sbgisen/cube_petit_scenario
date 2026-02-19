from setuptools import setup
import os
from glob import glob

package_name = 'cube_petit_anima'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='your_email@example.com',
    description='Anima layer for CubePetit: internal motivational state and behavioral drift.',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'internal_state_node = cube_petit_anima.internal_state_node:main',
            'behavior_node = cube_petit_anima.behavior_node:main',
            'sensor_influence_node = cube_petit_anima.sensor_influence_node:main',
        ],
    },
)
