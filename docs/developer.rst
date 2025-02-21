=======================
   Development Setup
=======================

The development workflow is still being worked on, but this page covers the current state of the world.

You will see ``pip install -e .`` frequently in the documentation. Please see the `pip documentation`_ for an explanation on what this does.

.. note:: All current development versions of LedFx now require Python >=3.9

------------------------------

-------------------------
   Backend Development
-------------------------

.. _win-dev:

Windows
-------

  - Install Python 3.9
  - Install Git.
  - Using "Build Tools for Visual Studio 2019" installer:

    - https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2019
    - You require the mandatory selected build tools, and the following optional tools;

        - Windows 10 SDK (or your equivalent Windows Version)
        - C++ CMAKE tools for Windows
        - MSVC v142 (or above) - VS 2019 C++ x64/x86 build tools

    - Default install options are appropriate.

  - Reboot


.. code:: console

    $ python -m venv C:\ledfx
    $ cd C:\ledfx
    $ .\Scripts\activate.bat
    $ pip install pipwin
    $ pip install wheel
    $ pipwin refresh
    $ pipwin install pyaudio
    $ pip install pywin32
    $ python .\Scripts\pywin32_postinstall.py -install
    $ git clone -b dev https://github.com/LedFx/LedFx .\ledfx-git
    $ cd .\ledfx-git
    $ python setup.py develop
    $ ledfx --open-ui

**1.** To develop, open up a terminal and activate the ledfx virtual environment

.. code:: console

    $ C:\ledfx\Scripts\activate.bat

**2.** Make changes to LedFx's files in C:/ledfx/ledfx-git. Your changed files will be run when you run LedFx

.. code:: console

    $ ledfx --open-ui

You can keep the ledfx virtual environment open and keep making changes then running ledfx.
No need to reactivate the virtual environment between changes.

.. _linux-dev:

Linux
-------

**1.** Clone the dev branch from the LedFx Github repository:

.. code:: console

    $ git clone https://github.com/LedFx/LedFx.git -b dev
    $ cd LedFx

**2.** Install system dependencies via ``apt install``:

.. code:: console

    $ sudo apt install libatlas3-base \
          libavformat58 \
          portaudio19-dev \
          pulseaudio

**3.** Install LedFx in development mode:

.. code:: console

    $ python setup.py develop

**4.** This will let you run LedFx directly from your Git repository via:

.. code:: console

    $ ledfx --open-ui

.. _macos-dev:

macOS
-------

**1.** Clone the dev branch from the LedFx Github repository:

.. code:: console

    $ git clone https://github.com/LedFx/LedFx.git -b dev
    $ cd ./LedFx

**2.** Create a python venv for LedFx with python>=3.9 and install dependencies:

.. code:: console

    $ python3 -m venv ~/ledfx-venv
    $ source ~/ledfx-venv/bin/activate
    $ brew install portaudio pulseaudio

**3.** Install LedFx and its requirements using pip:

.. code:: console

    $ python setup.py develop

**4.** This will let you run LedFx directly from your Git repository via:

.. code:: console

    $ ledfx --open-ui

------------------------------

--------------------------
   Frontend Development
--------------------------

Building the LedFx frontend is different from how the core backend is built. The frontend is based on React.js and thus
uses yarn as the core package management.

.. note:: LedFx will need to be running in development mode for everything to work. To enable development mode,
          open the ``config.yaml`` file in the ``.ledfx`` folder and set ``dev_mode: true``)

.. _linux-frontend:

Linux
-------

.. note:: The following instructions assume you have already followed the steps above to :ref:`install the LedFx dev environment <linux-dev>`

To get started, first install yarn and all the requirements:

**1.** Start in the LedFx repo directory:

.. code:: console

    $ pip install yarn
    $ cd frontend
    $ yarn

The easiest way to test and validate your changes is to run a watcher that will automatically rebuild as you save and then
just leave LedFx running in a separate command window.

**2.** Start LedFx in development mode and start the watcher:

.. code:: console

    $ python3 ledfx
    $ yarn start

At that point any change you make to the frontend will be recompiled and after a browser refresh LedFx will pick up the
new files. After development and testing you will need to run a full build to generate the appropriate distribution files
prior to submitting any changes.

**3.** When you are finished with your changes, build the frontend:

.. code:: console

    $ yarn build

.. _macos-frontend:

macOS
-------

.. note:: The following instructions assume you have already followed the steps above to :ref:`install the LedFx dev environment <macos-dev>`

**1.** Install nodejs and yarn requirements using `homebrew`_:

.. code:: console

    $ brew install nodejs
    $ brew install yarn
    $ cd ~/frontend
    $ yarn

**2.** Start LedFx in developer mode and start the yarn watcher:

.. code:: console

    $ python3 ledfx
    $ yarn start

**3.** When you are finished with your changes, build the frontend:

.. code:: console

    $ yarn build

------------------------------

.. include:: README.rst

.. Links Down Here

.. _`pip documentation`: https://pip.pypa.io/en/latest/reference/pip_install/#editable-installs
.. _`homebrew`: https://docs.brew.sh/Installation