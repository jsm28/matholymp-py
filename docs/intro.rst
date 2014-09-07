Introduction and prerequisites
==============================

Matholymp is software for creating and maintaining websites for
mathematical olympiads, with online registration and support for
various associated administrative functions.

Matholymp is free software, written in `Python
<https://www.python.org/>`_ and available under the `GNU General
Public License, version 3 <https://www.gnu.org/licenses/gpl.html>`_.

Matholymp is written and maintained by `Joseph Myers
<http://www.polyomino.org.uk/>`_.  It was originally developed for the
`European Girls' Mathematical Olympiad <https://www.egmo.org/>`_.  The
following events are known to use matholymp; please let me know if
you're using it for your event and I'll add it to the list.

* `European Girls' Mathematical Olympiad <https://www.egmo.org/>`_.

The following prerequisite software should be installed to use
matholymp:

* `Python <https://www.python.org/>`_, version 2.7.x (not Python 3).
  (The command-line parts of matholymp should also work with Python
  3.2.x or later, although this is not well-tested.)

* `PyICU <https://pypi.python.org/pypi/PyICU>`_ (which in turn
  requires `ICU <http://site.icu-project.org/>`_).

* `Roundup <http://roundup-tracker.org/>`_ (used to provide a web
  interface for editing databases for the online registration system;
  the issue-tracking parts of Roundup, and the email interface, are
  not used; Roundup is not needed if the online registration system is
  not used).  (Roundup does not yet support Python 3, which is why
  Python 3 is not supported for online registration.)  Use of the
  current version of Roundup, 1.5.0 as of this writing, is
  recommended.  Versions before 1.4.20 have known bugs, fixed in
  1.4.20, that are relevant to some uses of matholymp.  Some such bugs
  are still present in 1.5.0, so you should consider applying the
  patches in the :file:`roundup-patches/` directory in the matholymp
  source distribution before installing Roundup.  See
  :ref:`roundup-patches` for more details of those patches.

* `PyPDF2 <http://mstamy2.github.io/PyPDF2/>`_ or the older `pyPdf
  <http://pybrary.net/pyPdf/>`_ (used in generating PDF documents from
  registration system data; not needed if that part of matholymp is
  not used).

* `LaTeX <http://latex-project.org/>`_; specifically, the
  :command:`pdflatex` command (used in generating PDF documents from
  registration system data; not needed if that part of matholymp is
  not used).

* A web server such as Apache, and a database server (MySQL or
  PostgreSQL), are also recommended for use with the online
  registration system.  (For testing purposes, you can use Roundup's
  built-in web server and its support for Python's :py:mod:`anydbm`.)

* To generate the formatted documentation, `Sphinx
  <http://sphinx-doc.org/>`_ is needed.  This is not needed simply to
  use matholymp.  If you are reading this document online, note that
  it relates to version |release|; if you are using a different
  matholymp version (including if you are using the current
  development sources), you may wish to format the documentation for
  that version using Sphinx, which can be done with the provided
  :command:`mo-sphinx-build` script, or read the documentation sources
  in the :file:`docs/` directory of the source distribution directly.
  (Run :command:`mo-sphinx-build` with an empty working directory; it
  generates its output in the current directory.)

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

The current development sources of matholymp are available using `Git
<http://git-scm.com/>`_::

   git clone git://git.ukmt.org.uk/git/matholymp-py.git

The matholymp code can be used directly from its source directory; no
installation is required.  If you run the provided scripts from the
source directory, they will automatically find the Python modules in
the :file:`matholymp/` directory.  However, you will need to ensure
these modules can be found when the Roundup registration system is run
(for example, by creating a symbolic link from the
:file:`site-packages/` directory where Roundup was installed to the
:file:`matholymp/` directory, or by setting :envvar:`PYTHONPATH`
appropriately).

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
