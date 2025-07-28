import os
import subprocess
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Serve Vue.js SSR application alongside Django'

    def add_arguments(self, parser):
        parser.add_argument(
            '--port',
            type=int,
            default=3000,
            help='Port for Vue.js SSR server (default: 3000)'
        )
        parser.add_argument(
            '--build',
            action='store_true',
            help='Build the Vue.js application before serving'
        )

    def handle(self, *args, **options):
        port = options['port']
        should_build = options['build']
        
        # Get the project root directory
        project_root = settings.BASE_DIR
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting Vue.js SSR server on port {port}...')
        )
        
        try:
            # Change to project root directory
            os.chdir(project_root)
            
            # Install dependencies if node_modules doesn't exist
            if not os.path.exists('node_modules'):
                self.stdout.write('Installing npm dependencies...')
                subprocess.run(['npm', 'install'], check=True)
            
            # Build the application if requested
            if should_build:
                self.stdout.write('Building Vue.js application...')
                subprocess.run(['npm', 'run', 'build:ssr'], check=True)
            
            # Start the SSR server
            self.stdout.write(f'Starting SSR server on http://localhost:{port}')
            subprocess.run(['npm', 'run', 'serve:ssr'], check=True)
            
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to start Vue.js SSR server: {e}')
            )
            sys.exit(1)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\nVue.js SSR server stopped.')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Unexpected error: {e}')
            )
            sys.exit(1) 