from StringIO import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
    
def get_admin_change_url(obj):
    ct = ContentType.objects.get_for_model(obj)
    change_url_name = 'admin:%s_%s_change' % (ct.app_label, ct.model)
    return reverse(change_url_name, args=(obj.id,))

def get_admin_changelist_url(obj):
    ct = ContentType.objects.get_for_model(obj)
    list_url_name = 'admin:%s_%s_changelist' % (ct.app_label, ct.model)
    return reverse(list_url_name)

class TeeFile(StringIO):
    """
    A helper class for allowing output to be stored in a StringIO instance
    while still be directed to a second file object, such as sys.stdout.
    """
    def __init__(self, file, auto_flush=False):
        #super(TeeFile, self).__init__()
        StringIO.__init__(self)
        self.file = file
        self.auto_flush = auto_flush
        self.length = 0

    def write(self, s):
        self.length += len(s)
        self.file.write(s)
        #super(TeeFile, self).write(s)
        StringIO.write(self, s)
        if self.auto_flush:
            self.file.flush()
        
    def flush(self):
        self.file.flush()
        #super(TeeFile, self).flush()
        StringIO.flush(self)
