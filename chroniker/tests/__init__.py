import html.parser


# create a dummy class for Python 3.5+ where it's been removed
class HTMLParseError(Exception):
    pass


html.parser.HTMLParseError = HTMLParseError
