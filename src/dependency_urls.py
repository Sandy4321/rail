"""
dependency_urls.py
Part of Rail-RNA

Defines URLs at which dependencies may be downloaded when installing Rail-RNA.
Increasing version numbers of dependencies should formally increase Rail-RNA's
version.

Note that bedGraphToBigWig is occasionally updated at 
http://hgdownload.cse.ucsc.edu/admin/exe/macOSX.x86_64/bedGraphToBigWig 
and
http://hgdownload.cse.ucsc.edu/admin/exe/linux.x86_64/bedGraphToBigWig
without forewarning, so the default URL for these is in Ben Langmead's CCB
space. The alternative URLs at Webfactional are Abhi Nellore's space.
"""
import os

linux_dependencies = {
    'bowtie1' : ['http://downloads.sourceforge.net/project/bowtie-bio/'
                 'bowtie/1.2.2/bowtie-1.2.2-linux-x86_64.zip',
                 'http://verve.webfactional.com/mirror/linux/'
                 'bowtie-1.2.2-linux-x86_64.zip'],
    'bowtie2' : ['https://downloads.sourceforge.net/project/bowtie-bio/'
                 'bowtie2/2.3.4.1/bowtie2-2.3.4.1-linux-x86_64.zip',
                 'http://verve.webfactional.com/mirror/linux/'
                 'bowtie2-2.3.4.1-linux-x86_64.zip'],
    'bedgraphtobigwig' : ['ftp://ftp.ccb.jhu.edu/pub/langmead/rail/'
                          'linux.x86_64/bedGraphToBigWig',
                          'http://verve.webfactional.com/mirror/linux/'
                          'bedGraphToBigWig'],
    'aws_cli' : ['http://s3.amazonaws.com/aws-cli/awscli-bundle.zip',
                 'http://verve.webfactional.com/mirror/linux/'
                 'awscli-bundle.zip'],
    'samtools' : ['http://downloads.sourceforge.net/project/samtools/samtools/'
                  '1.2/samtools-1.2.tar.bz2',
                  'http://verve.webfactional.com/mirror/linux/'
                  'samtools-1.2.tar.bz2'],
    'pypy' : ['https://bitbucket.org/squeaky/portable-pypy/downloads/'
              'pypy-5.10.0-linux_x86_64-portable.tar.bz2',
              'http://verve.webfactional.com/mirror/linux/'
              'pypy-5.10.0-linux_x86_64-portable.tar.bz2'],
    'ipython' : ['https://github.com/ipython/ipyparallel/archive/'
                 '6.0.2.zip',
                 'http://verve.webfactional.com/mirror/linux/'
                 'ipyparallel-6.0.2.zip'],
    'sra_tools' : ['https://ftp-trace.ncbi.nlm.nih.gov/sra/sdk/2.9.0/'
                   'sratoolkit.2.9.0-centos_linux64.tar.gz',
                   'http://verve.webfactional.com/mirror/linux/'
                   'sratoolkit.2.9.0-centos_linux64.tar.gz']
}

ec2_dependencies = {}
for dependency in linux_dependencies:
    ec2_dependencies[dependency] = [
            'http://s3.amazonaws.com/rail-emr/dependencies/'
            + os.path.basename(linux_dependencies[dependency][-1])
        ] + linux_dependencies[dependency]

mac_dependencies = {
    'bowtie1' : ['http://downloads.sourceforge.net/project/bowtie-bio/'
                 'bowtie/1.2.2/bowtie-1.2.2-macos-x86_64.zip',
                 'http://verve.webfactional.com/mirror/mac/'
                 'bowtie-1.2.2-macos-x86_64.zip'],
    'bowtie2' : ['https://downloads.sourceforge.net/project/bowtie-bio/'
                 'bowtie2/2.3.4.1/bowtie2-2.3.4.1-macos-x86_64.zip',
                 'http://verve.webfactional.com/mirror/mac/'
                 'bowtie2-2.3.4.1-macos-x86_64.zip'],
    'bedgraphtobigwig' : ['ftp://ftp.ccb.jhu.edu/pub/langmead/rail/'
                          'macOSX.x86_64/bedGraphToBigWig',
                          'http://verve.webfactional.com/mirror/mac/'
                          'bedGraphToBigWig'],
    'aws_cli' : ['http://s3.amazonaws.com/aws-cli/awscli-bundle.zip',
                 'http://verve.webfactional.com/mirror/mac/awscli-bundle.zip'],
    'samtools' : ['http://downloads.sourceforge.net/project/samtools/samtools/'
                  '1.2/samtools-1.2.tar.bz2',
                  'http://verve.webfactional.com/mirror/mac/'
                  'samtools-1.2.tar.bz2'],
    'pypy' : ['http://bitbucket.org/pypy/pypy/downloads/'
              'pypy-5.1.10-osx64.tar.bz2',
              'http://verve.webfactional.com/mirror/mac/'
              'pypy-5.1.10-osx64.tar.bz2'],
    'ipyparallel' : ['https://github.com/ipython/ipyparallel/archive/'
                     '6.0.2.zip',
                     'http://verve.webfactional.com/mirror/mac/'
                     'ipyparallel-6.0.2.zip'],
    'sra_tools' : ['http://ftp-trace.ncbi.nlm.nih.gov/sra/sdk/2.8.2/'
                   'sratoolkit.2.9.0-mac64.tar.gz',
                   'http://verve.webfactional.com/mirror/mac/'
                   'sratoolkit.2.9.0-mac64.tar.gz']
}
