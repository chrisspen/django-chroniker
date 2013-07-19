import warnings
from StringIO import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models
from django.db import connection
    
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
        try:
            #import chardet
            #encoding_opinion = chardet.detect(s)
            #encoding = encoding_opinion['encoding']
            #TODO:fix? not stripping out non-ascii characters result in error
            #'ascii' codec can't encode character ? in position ?: ordinal not in range(128)
            s = ''.join(_ for _ in s if ord(_) < 128)
            #s = s.encode(encoding, 'ignore')
        except ImportError:
            pass
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

# Based on:
# http://djangosnippets.org/snippets/833/
# http://www.shiningpanda.com/blog/2012/08/08/mysql-table-lock-django/
class LockingManager(models.Manager):
    """ Add lock/unlock functionality to manager.
    
    Example::
    
        class Job(models.Model):
        
            manager = LockingManager()
    
            counter = models.IntegerField(null=True, default=0)
    
            @staticmethod
            def do_atomic_update(job_id)
                ''' Updates job integer, keeping it below 5 '''
                try:
                    # Ensure only one HTTP request can do this update at once.
                    Job.objects.lock()
                    
                    job = Job.object.get(id=job_id)
                    # If we don't lock the tables two simultanous
                    # requests might both increase the counter
                    # going over 5
                    if job.counter < 5:
                        job.counter += 1                                        
                        job.save()
                
                finally:
                    Job.objects.unlock()
     
    
    """    

    def lock(self):
        """ Lock table. 
        
        Locks the object model table so that atomic update is possible.
        Simulatenous database access request pend until the lock is unlock()'ed.
        
        Note: If you need to lock multiple tables, you need to do lock them
        all in one SQL clause and this function is not enough. To avoid
        dead lock, all tables must be locked in the same order.
        
        See http://dev.mysql.com/doc/refman/5.0/en/lock-tables.html
        """
        cursor = connection.cursor()
        if 'mysql' in connection.settings_dict['ENGINE']:
            table = self.model._meta.db_table
            logger.debug("Locking table %s" % table)
            cursor.execute("LOCK TABLES %s WRITE" % table)
        else:
            warnings.warn(
                'Locking of database backend "%s" is not supported.'
                    % (connection.settings_dict['ENGINE'],),
                warnings.RuntimeWarning
            )
        #row = cursor.fetchone()
        #return row
        return cursor
        
    def unlock(self):
        """ Unlock the table. """
        cursor = connection.cursor()
        if 'mysql' in connection.settings_dict['ENGINE']:
            table = self.model._meta.db_table
            cursor.execute("UNLOCK TABLES")
        else:
            warnings.warn(
                '(Un)Locking of database backend "%s" is not supported.'
                    % (connection.settings_dict['ENGINE'],),
                warnings.RuntimeWarning
            )
        #row = cursor.fetchone()
        #return row
        return cursor
    