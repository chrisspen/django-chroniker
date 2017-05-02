from __future__ import print_function

import sys
from optparse import make_option

import django
from django.core.management.base import BaseCommand

from chroniker.models import Job, JobDependency

from criticalpath import Node

class Command(BaseCommand):
    help = 'Calculates the total time a series of chained jobs will take.'

    option_list = getattr(BaseCommand, 'option_list', ()) + (
        make_option('--samples',
            default=20,
            help='The number of log samples to use when estimating mean job run time.'),
        )

    def create_parser(self, prog_name, subcommand):
        """
        For ``Django>=1.10``
        Create and return the ``ArgumentParser`` which extends ``BaseCommand`` parser with
        chroniker extra args and will be used to parse the arguments to this command.
        """
        from distutils.version import StrictVersion # pylint: disable=E0611
        parser = super(Command, self).create_parser(prog_name, subcommand)
        version_threshold = StrictVersion('1.10')
        current_version = StrictVersion(django.get_version(django.VERSION))
        if current_version >= version_threshold:
            parser.add_argument('root_job_id')
            parser.add_argument('--samples',
                default=20,
                help='The number of log samples to use when estimating mean job run time.')
            self.add_arguments(parser)
        return parser

    def handle(self, root_job_id, **options):
        root_job = Job.objects.get(id=int(root_job_id))
        samples = int(options['samples'])

        # Add all system task nodes.
        system = Node('system')
        system.add(Node(root_job.id, duration=root_job.get_run_length_estimate(samples=samples)))
        print('%s takes about %s seconds' \
            % (root_job, root_job.get_run_length_estimate(samples=samples)))
        chain = root_job.get_chained_jobs()
        for job in chain:
            print('%s takes about %s seconds' \
                % (job, job.get_run_length_estimate(samples=samples)))
            node = Node(job.id, duration=job.get_run_length_estimate(samples=samples))
            node.description = job.name
            system.add(node)

        # Add all links between task nodes.
        print('-'*80)
        for job in chain:
            if not job.enabled:
                continue
            dependees = JobDependency.objects.filter(dependent=job, dependee__enabled=True)
            dependees = dependees.values_list('dependee_id', flat=True)
            print(job, dependees)
            for dependee in dependees:
                # Link dependent job to dependee.
                assert job.id != 1
                system.link(from_node=dependee, to_node=job.id)

        root_node = system.lookup_node(1)
        print('root_node:', root_node, root_node.to_nodes, root_node.incoming_nodes)
        system.add_exit()
        sys.stdout.flush()

        #return
        print('Updating values...')
        system.update_all()

        critical_path = system.get_critical_path()
        print('critical_path:', critical_path)
        system.print_times()

        print('min hours:', system.duration*(1/60.)*(1/60.))
