

def suite_roots():
    """Return a dict of suite saving root path
    """
    from collections import OrderedDict as odict
    from sweet import util
    return odict([
        ("local", util.normpath("~/rez/sweet/local")),
        ("release", util.normpath("~/rez/sweet/release")),
    ])


def on_suite_saved_callback(suite, suite_dir):
    """A callback that runs after suite saved

    Args:
        suite (sweet._rezapi.SweetSuite): A live suite object
        suite_dir (str): suite saved path

    Returns:
        None

    """
    print("Suite saved: %s\n" % suite_dir)
    suite.print_tools()


sweet = {
    # default suite saving root
    "default_root": "local",

    # suite saving root paths
    "suite_roots": suite_roots,

    # callback
    "on_suite_saved_callback": on_suite_saved_callback,

}

# wip:
#   If not empty, internal package version will be omitted
#   in package versions' auto completion list.
omit_internal_version = ""
