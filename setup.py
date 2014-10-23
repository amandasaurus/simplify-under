from setuptools import setup

setup(
    name="simplify_under",
    version="1.0.0",
    author="Rory McCann",
    author_email="rory@technomancy.org",
    py_modules=['simplify_under'],
    platforms=['any',],
    requires=[],
    entry_points={
        'console_scripts': [
            'simplify_under = simplify_under:main',
        ]
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
    ],
)
