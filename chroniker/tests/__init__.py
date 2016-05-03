
# Fix AttributeError caused by conflict between Django<1.7 and Python>3.
# http://stackoverflow.com/q/34827566/247542
from django.utils.six.moves import html_parser as _html_parser    
try:
    HTMLParseError = _html_parser.HTMLParseError
except AttributeError:
    # create a dummy class for Python 3.5+ where it's been removed
    class HTMLParseError(Exception):
        pass
    _html_parser.HTMLParseError = HTMLParseError
