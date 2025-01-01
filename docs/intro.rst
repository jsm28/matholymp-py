.. Matholymp documentation introduction.
   Copyright 2014-2025 Joseph Samuel Myers.

   This program is free software; you can redistribute it and/or
   modify it under the terms of the GNU General Public License as
   published by the Free Software Foundation; either version 3 of the
   License, or (at your option) any later version.

   This program is distributed in the hope that it will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see
   <https://www.gnu.org/licenses/>.

   Additional permission under GNU GPL version 3 section 7:

   If you modify this program, or any covered work, by linking or
   combining it with the OpenSSL project's OpenSSL library (or a
   modified version of that library), containing parts covered by the
   terms of the OpenSSL or SSLeay licenses, the licensors of this
   program grant you additional permission to convey the resulting
   work.  Corresponding Source for a non-source form of such a
   combination shall include the source code for the parts of OpenSSL
   used as well as that of the covered work.

Introduction, prerequisites and downloads
=========================================

Matholymp is software for creating and maintaining websites for
mathematical olympiads, with online registration and support for
various associated administrative functions.

Matholymp is free software, written in `Python
<https://www.python.org/>`_ and available under the `GNU General
Public License, version 3 <https://www.gnu.org/licenses/gpl.html>`_.

Matholymp is written and maintained by `Joseph Myers
<https://www.polyomino.org.uk/>`_.  It was originally developed for the
`European Girls' Mathematical Olympiad <https://www.egmo.org/>`_.  The
following events are known to use matholymp; please let me know if
you're using it for your event and I'll add it to the list.

* `European Girls' Mathematical Olympiad <https://www.egmo.org/>`_.

The following prerequisite software should be installed to use
matholymp:

* `Python <https://www.python.org/>`_, version 3.5 or later.

* `PyICU <https://pypi.org/project/PyICU/>`_ (which in turn
  requires `ICU <http://site.icu-project.org/>`_).

* `Roundup <http://roundup-tracker.org/>`_ (used to provide a web
  interface for editing databases for the online registration system;
  the issue-tracking parts of Roundup, and the email interface, are
  not used; Roundup is not needed if the online registration system is
  not used).  Use of the current version of Roundup, 2.4.0 as of this
  writing, is recommended; older versions will not work because of
  Roundup API changes.  Some bugs relevant to some uses of matholymp
  are still present in 2.4.0, so you should consider applying the
  patches in the :file:`roundup-patches/` directory in the matholymp
  source distribution before installing Roundup.  See
  :ref:`roundup-patches` for more details of those patches.

* `PyPDF2 <https://mstamy2.github.io/PyPDF2/>`_ (used in generating
  PDF documents from registration system data, and also required in
  the registration system whether document generation is used or not;
  not needed if those parts of matholymp are not used).

* `Pillow <https://python-pillow.org/>`_, built with support for JPEG
  and PNG files.

* `LaTeX <https://www.latex-project.org/>`_; specifically, the
  :command:`pdflatex` command (used in generating PDF documents from
  registration system data; not needed if that part of matholymp is
  not used).

* A web server such as Apache, and a database server (MySQL or
  PostgreSQL), are also recommended for use with the online
  registration system.  (For testing purposes, you can use Roundup's
  built-in web server and its support for Python's :py:mod:`dbm`.)

* To generate the formatted documentation, `Sphinx
  <https://www.sphinx-doc.org/>`_ is needed.  This is not needed simply to
  use matholymp.  If you are reading this document online, note that
  it relates to version |release|; if you are using a different
  matholymp version (including if you are using the current
  development sources), you may wish to format the documentation for
  that version using Sphinx, which can be done with the provided
  :command:`mo-sphinx-build` script, or read the documentation sources
  in the :file:`docs/` directory of the source distribution directly.
  (Run :command:`mo-sphinx-build` with an empty working directory; it
  generates its output in the current directory.)

* To run automated tests of the registration system, `MechanicalSoup
  <https://mechanicalsoup.readthedocs.io/>`_ (which in turn has some
  other dependencies) is needed.  Those tests are only expected to
  work on Unix-like operating systems.

* To measure the code coverage of the automated tests, `Coverage.py
  <https://coverage.readthedocs.io/en/latest/>`_ is needed.  This is
  only relevant for developing matholymp, not for using it.  The
  ``--coverage`` option to :command:`mo-run-tests` is used for
  measuring coverage.

The matholymp code is intended to be independent of the operating
system used.  However, it has only been tested on GNU/Linux
(specifically, various versions of Ubuntu) and so it is likely you
will need to debug portability issues if not using it on a Unix-like
operating system.  (Other Unix-like operating systems are unlikely to
be a problem.  They may vary in the extent to which the prerequisites
listed above are available prepackaged or have to be locally built.  I
have no recommendations regarding whether you should use packaged
versions where available or build these prerequisites locally; that is
a matter of personal preference.)

Releases of matholymp are available for download:

* 2020.07.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2020.07.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2020.07.0.tar.gz.sig>`_).

* 2018.02.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2018.02.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2018.02.0.tar.gz.sig>`_).

* 2017.05.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2017.05.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2017.05.0.tar.gz.sig>`_).

* 2017.01.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2017.01.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2017.01.0.tar.gz.sig>`_).

* 2016.05.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2016.05.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2016.05.0.tar.gz.sig>`_).

* 2016.01.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2016.01.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2016.01.0.tar.gz.sig>`_).

* 2015.04.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2015.04.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2015.04.0.tar.gz.sig>`_).

* 2015.01.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2015.01.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2015.01.0.tar.gz.sig>`_).

* 2014.09.0 (`sources
  <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2014.09.0.tar.gz>`_,
  `GPG signature <https://www.polyomino.org.uk/mathematics/olympiad-software/matholymp-2014.09.0.tar.gz.sig>`_).

The current development sources of matholymp are available using `Git
<https://git-scm.com/>`_::

   git clone https://git.ukmt.org.uk/matholymp-py.git

There is also a `mirror on GitHub
<https://github.com/jsm28/matholymp-py>`_.

The matholymp code can be used directly from its source directory; no
installation is required.  If you run the provided scripts from the
source directory, they will automatically find the Python modules in
the :file:`matholymp/` directory.  However, you will need to ensure
these modules can be found when the Roundup registration system is run
(for example, by creating a symbolic link from the
:file:`site-packages/` directory where Roundup was installed to the
:file:`matholymp/` directory, or by setting :envvar:`PYTHONPATH`
appropriately).  Some parts of the matholymp code have a testsuite,
which can be run with :command:`mo-run-tests`; all tests should pass.

The matholymp functionality falls into three main areas.  Although the
software is designed as an integrated whole, you can also choose to
use only parts of the functionality.  Whichever parts of the system
you use, you will be maintaining directories containing configuration
files and other content such as photos on the static site and LaTeX
and HTML templates.  It is a good idea to maintain these directories
in a version control system such as Git in case any problems arise and
you need to undo a change made.  You will also need to ensure that all
these directories are included in your system's backup arrangements,
and ensure that databases for the registration system are backed up as
well (which typically means the backup process running database dumps
to ensure the backup contains a consistent state, rather than backing
up the raw files containing the database).

* :ref:`static-site`.
* :ref:`online-registration`.
* :ref:`document-generation`.
