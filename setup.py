from setuptools import setup, find_packages

with open('README.md') as readme_file:
    README = readme_file.read()

setup(
    name='wpcraft',
    version='1.2.1',
    description='A CLI for fetching wallpapers from WallpapersCraft',
    long_description=README,
    long_description_content_type="text/markdown",

    url='https://github.com/rafalcieslak/wpcraft',
    author='Rafał Cieślak',
    author_email='rafalcieslak256@gmail.com',

    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Topic :: Desktop Environment',
        'Topic :: Utilities',
    ],
    keywords='cli wallpaper desktop',

    python_requires='>=3.6',
    install_requires=['python-crontab>=2.2'],

    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'wpcraft = wpcraft.wpcraft:main',
        ],
    },
)
