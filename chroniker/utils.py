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
    def __init__(self, file):
        #super(TeeFile, self).__init__()
        StringIO.__init__(self)
        self.file = file

    def write(self, s):
        self.file.write(s)
        #super(TeeFile, self).write(s)
        StringIO.write(self, s)
        
    def flush(self):
        self.file.flush()
        #super(TeeFile, self).flush()
        StringIO.flush(self)
