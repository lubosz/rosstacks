# Software License Agreement (BSD License)
#
# Copyright (c) 2010, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import roslib; roslib.load_manifest('rosbag')

import optparse
import os
import signal
import subprocess
import sys
import time
import UserDict

from bag import Bag, Compression, ROSBagException, ROSBagFormatException
from migration import MessageMigrator, fixbag2

def print_trans(old, new, indent):
    from_txt = '%s [%s]' % (old._type, old._md5sum)
    if new is not None:
        to_txt= '%s [%s]' % (new._type, new._md5sum)
    else:
        to_txt = 'Unknown'
    print '    ' * indent + ' * From: %s' % from_txt
    print '    ' * indent + '   To:   %s' % to_txt

def record_cmd(argv):
    parser = optparse.OptionParser(usage="rosbag record TOPIC1 [TOPIC2 TOPIC3 ...]",
                                   description="Record a bag file with the contents of specified topics.",
                                   formatter=optparse.IndentedHelpFormatter())

    parser.add_option("-a", "--all",           dest="all",      default=False, action="store_true",        help="record all topics")
    parser.add_option("-e", "--regex",         dest="regex",    default=False, action="store_true",        help="match topics using regular expressions")
    parser.add_option("-q", "--quiet",         dest="quiet",    default=False, action="store_true",        help="suppress console output")
    parser.add_option("-o", "--output-prefix", dest="prefix",   default=None,  action="store",             help="prepend PREFIX to beginning of bag name (name will always end with date stamp)")
    parser.add_option("-O", "--output-name",   dest="name",     default=None,  action="store",             help="record to bag with namename NAME.bag")
    parser.add_option("--split",               dest="split",    default=0,     type='int', action="store", help="split bag into files of size SIZE", metavar="SIZE")
    parser.add_option("-b", "--buffsize",      dest="buffsize", default=256,   type='int', action="store", help="use in internal buffer of SIZE MB (Default: %default, 0 = infinite)", metavar="SIZE")
    parser.add_option("-l", "--limit",         dest="num",      default=0,     type='int', action="store", help="only record NUM messages on each topic")
    #parser.add_option("-z", "--zlib",          dest="zlib",     default=False, action="store_true",        help="use ZLIB compression")
    parser.add_option("-j", "--bz2",           dest="bz2",      default=False, action="store_true",        help="use BZ2 compression")

    (options, args) = parser.parse_args(argv)

    if len(args) == 0 and not options.all:
        parser.error("You must specify a topic name or else use the '-a' option.")

    if options.prefix is not None and options.name is not None:
        parser.error("Can't set both prefix and name.")

    cmd = ['rosrun', 'rosbag', 'record']

    cmd.extend(['-m', str(options.buffsize)])
    cmd.extend(['-c', str(options.num)])
    cmd.extend(['-S', str(options.split)])

    if options.prefix: cmd.extend(["-f", options.prefix])
    if options.name:   cmd.extend(["-F", options.name])
    if options.all:    cmd.extend(["-a"])
    if options.regex:  cmd.extend(["-e"])
    #if options.zlib:   cmd.extend(["-z"])
    if options.bz2:    cmd.extend(["-j"])

    cmd.extend(args)

    proc = subprocess.Popen(cmd)
    signal.signal(signal.SIGINT, signal.SIG_IGN)   # ignore sigint since we're basically just pretending to be the subprocess now
    res = proc.wait()
    sys.exit(res)

def info_cmd(argv):
    parser = optparse.OptionParser(usage='rosbag info BAGFILE1 [BAGFILE2 BAGFILE3 ...]',
                                   description='Summarize the contents of one or more bag files.')
    (options, args) = parser.parse_args(argv)

    if len(args) == 0:
        parser.error('You must specify at least 1 bag file.')

    for i, arg in enumerate(args):
        try:
            b = Bag(arg)
            print b
            b.close()
            if i < len(args) - 1:
                print '---'
            
        except ROSBagException, ex:
            print >> sys.stderr, 'ERROR reading %s: %s' % (arg, str(ex))
        except IOError, ex:
            print >> sys.stderr, 'ERROR reading %s: %s' % (arg, str(ex))
            
    print

def play_cmd(argv):
    parser = optparse.OptionParser(usage="rosbag play BAGFILE1 [BAGFILE2 BAGFILE3 ...]",
                                   description="Play back the contents of one or more bag files in a time-synchronized fashion.")
    parser.add_option("-q", "--quiet",        dest="quiet",      default=False, action="store_true", help="suppress console output")
    parser.add_option("-i", "--immediate",    dest="immediate",  default=False, action="store_true", help="play back all messages without waiting")
    parser.add_option("--pause",              dest="pause",      default=False, action="store_true", help="start in paused mode")
    parser.add_option("--queue",              dest="queue",      default=0,     type='int', action="store", help="use an outgoing queue of size SIZE (defaults to %default)", metavar="SIZE")
    parser.add_option("--clock",              dest="clock",      default=False, action="store_true", help="publish the clock time")
    parser.add_option("--hz",                 dest="freq",       default=100,   type='float', action="store", help="use a frequency of HZ when publishing clock time (default: %default)", metavar="HZ")
    parser.add_option("-d", "--delay",        dest="delay",      default=0.2,   type='float', action="store", help="sleep SEC seconds after every advertise call (to allow subscribers to connect)", metavar="SEC")
    parser.add_option("-r", "--rate",         dest="rate",       default=1.0,   type='float', action="store", help="multiply the publish rate by FACTOR", metavar="FACTOR")
    parser.add_option("-s", "--start",        dest="sleep",      default=0.0,   type='float', action="store", help="start SEC seconds into the bag files", metavar="SEC")
    parser.add_option("--try-future-version", dest="try_future", default=False, action="store_true", help="still try to open a bag file, even if the version number is not known to the player")

    (options, args) = parser.parse_args(argv)

    if len(args) == 0:
        parser.error('You must specify at least 1 bag file to play back.')

    cmd = ['rosrun', 'rosbag', 'play']

    if options.quiet:      cmd.extend(["-n"])
    if options.pause:      cmd.extend(["-p"])
    if options.immediate:  cmd.extend(["-a"])
    if options.try_future: cmd.extend(["-T"])

    if options.clock:
        cmd.extend(["-b", str(options.freq)])

    cmd.extend(['-q', str(options.queue)])
    cmd.extend(['-r', str(options.rate)])
    cmd.extend(['-s', str(options.delay)])
    cmd.extend(['-t', str(options.sleep)])

    cmd.extend(args)

    proc = subprocess.Popen(cmd)
    signal.signal(signal.SIGINT, signal.SIG_IGN)   # ignore sigint since we're basically just pretending to be the subprocess now
    res = proc.wait()
    sys.exit(res)

def filter_cmd(argv):
    def expr_eval(expr):
        def eval_fn(topic, m, t):
            return eval(expr)
        return eval_fn

    parser = optparse.OptionParser(usage="""rosbag filter [options] INBAG OUTBAG EXPRESSION

EXPRESSION can be any Python-legal expression.

The following variables are available:
 * topic: name of topic
 * m: message
 * t: time of message (t.secs, t.nsecs)""",
                                   description='Filter the contents of the bag.')
    parser.add_option('-p', '--print', action='store', dest='verbose_pattern', default=None, metavar='PRINT-EXPRESSION', help='Python expression to print for verbose debugging. Uses same variables as filter-expression')

    options, args = parser.parse_args(argv)
    if len(args) == 0:
        parser.error('You must specify an in bag, an out bag, and an expression.')
    if len(args) == 1:
        parser.error('You must specify an out bag and an expression.')
    if len(args) == 2:
        parser.error("You must specify an expression.")
    if len(args) > 3:
        parser.error("Too many arguments.")

    inbag_filename, outbag_filename, expr = args

    if not os.path.isfile(inbag_filename):
        print >> sys.stderr, 'Cannot locate input bag file [%s]' % inbag_filename
        sys.exit(2)

    filter_fn = expr_eval(expr)

    outbag = Bag(outbag_filename, 'w')
    inbag  = Bag(inbag_filename)

    try:
        meter = ProgressMeter(outbag_filename, inbag.size)
        total_bytes = 0
    
        if options.verbose_pattern:
            verbose_pattern = expr_eval(options.verbose_pattern)
    
            for topic, raw_msg, t in inbag.read_messages(raw=True):
                msg_type, serialized_bytes, md5sum, pos, pytype = raw_msg
                msg = pytype()
                msg.deserialize(serialized_bytes)

                if filter_fn(topic, msg, t):
                    print 'MATCH', verbose_pattern(topic, msg, t)
                    outbag.write(topic, msg, t)
                else:
                    print 'NO MATCH', verbose_pattern(topic, msg, t)          

                total_bytes += len(serialized_bytes) 
                meter.step(total_bytes)
        else:
            for topic, raw_msg, t in inbag.read_messages(raw=True):
                msg_type, serialized_bytes, md5sum, pos, pytype = raw_msg
                msg = pytype()
                msg.deserialize(serialized_bytes)

                if filter_fn(topic, msg, t):
                    outbag.write(topic, msg, t)

                total_bytes += len(serialized_bytes)
                meter.step(total_bytes)
        
        meter.finish()

    finally:
        inbag.close()
        outbag.close()

def fix_cmd(argv):
    parser = optparse.OptionParser(usage='rosbag fix INBAG OUTBAG [EXTRARULES1 EXTRARULES2 ...]')
    parser.add_option('-n', '--noplugins', action='store_true', dest='noplugins', help='do not load rulefiles via plugins')

    (options, args) = parser.parse_args(argv)

    if len(args) < 1:
        parser.error('You must pass input and output bag files.')
    if len(args) < 2:
        parser.error('You must pass an output bag file.')

    inbag_filename  = args[0]
    outbag_filename = args[1]
    rules           = args[2:]   

    ext = os.path.splitext(outbag_filename)[1]
    if ext == '.bmr':
        parser.error('Input file should be a bag file, not a rule file.')
    if ext != '.bag':
        parser.error('Output file must be a bag file.')

    outname = outbag_filename + '.tmp'

    if os.path.exists(outbag_filename):
        if not os.access(outbag_filename, os.W_OK):
            print >> sys.stderr, 'Don\'t have permissions to access %s' % outbag_filename
            sys.exit(1)
    else:
        try:
            file = open(outbag_filename, 'w')
            file.close()
        except IOError, e:
            print >> sys.stderr, 'Cannot open %s for writing' % outbag_filename
            sys.exit(1)

    if os.path.exists(outname):
        if not os.access(outname, os.W_OK):
            print >> sys.stderr, 'Don\'t have permissions to access %s' % outname
            sys.exit(1)
    else:
        try:
            file = open(outname, 'w')
            file.close()
        except IOError, e:
            print >> sys.stderr, 'Cannot open %s for writing' % outname
            sys.exit(1)

    if options.noplugins is None:
        options.noplugins = False

    migrator = MessageMigrator(rules, plugins=not options.noplugins)

    migrations = fixbag2(migrator, inbag_filename, outname)

    if len(migrations) == 0:
        print '%s %s' % (outname, outbag_filename)
        os.rename(outname, outbag_filename)
        print 'Bag migrated successfully.'
    else:
        print 'Bag could not be migrated.  The following migrations could not be performed:'
        for m in migrations:
            print_trans(m[0][0].old_class, m[0][-1].new_class, 0)
            
            if len(m[1]) > 0:
                print '    %d rules missing:' % len(m[1])
                for r in m[1]:
                    print_trans(r.old_class, r.new_class,1)
                    
        print 'Try running \'rosbag check\' to create the necessary rule files.'
        os.remove(outname)

def check_cmd(argv):
    parser = optparse.OptionParser(usage='rosbag check BAG [-g RULEFILE] [EXTRARULES1 EXTRARULES2 ...]')
    parser.add_option('-g', '--genrules',  action='store',      dest='rulefile', default=None, help='generate a rulefile named RULEFILE')
    parser.add_option('-a', '--append',    action='store_true', dest='append',                 help='append to the end of an existing rulefile after loading it')
    parser.add_option('-n', '--noplugins', action='store_true', dest='noplugins',              help='do not load rulefiles via plugins')
    (options, args) = parser.parse_args(argv)

    if len(args) == 0:
        parser.error('You must specify a bag file to check.')
    if options.append and options.rulefile is None:
        parser.error('Cannot specify -a without also specifying -g.')
    if options.rulefile is not None:
        rulefile_exists = os.path.isfile(options.rulefile)
        if rulefile_exists and not options.append:
            parser.error('The file %s already exists.  Include -a if you intend to append.' % options.rulefile)
        if not rulefile_exists and options.append:
            parser.error('The file %s does not exist, and so -a is invalid.' % options.rulefile)

    cmd = ['rosrun', 'rosbag', 'checkbag.py']
    if options.rulefile:  cmd.extend(['-g', options.rulefile])
    if options.append:    cmd.extend(['-a'])
    if options.noplugins: cmd.extend(['-n'])
    cmd.extend(args)

    proc = subprocess.Popen(cmd)
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # ignore sigint since we're basically just pretending to be the subprocess now
    res = proc.wait()
    sys.exit(res)

def compress_cmd(argv):
    parser = optparse.OptionParser(usage='rosbag compress [options] BAGFILE1 [BAGFILE2 ...]',
                                   description='Compress one or more bag files.')
    parser.add_option('-f', '--force', action='store_true', dest='force', help='force overwriting of backup file if it exists')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', help='suppress noncritical messages')

    (options, args) = parser.parse_args(argv)

    if len(args) < 1:
        parser.error('You must specify at least one bag file.')

    bag_op(args, lambda inbag, outbag, quiet: change_compression_op(inbag, outbag, Compression.BZ2, options.quiet), options.force, options.quiet)

def decompress_cmd(argv):
    parser = optparse.OptionParser(usage='rosbag decompress [options] BAGFILE1 [BAGFILE2 ...]',
                                   description='Decompress one or more bag files.')
    parser.add_option('-f', '--force', action='store_true', dest='force', help='force overwriting of backup file if it exists')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', help='suppress noncritical messages')

    (options, args) = parser.parse_args(argv)

    if len(args) < 1:
        parser.error('You must specify at least one bag file.')
    
    bag_op(args, lambda inbag, outbag, quiet: change_compression_op(inbag, outbag, Compression.NONE, options.quiet), options.force, options.quiet)
    
def bag_op(filenames, op, force=False, quiet=False):
    for inbag_filename in filenames:
        # Check we can read the file
        try:
            inbag = Bag(inbag_filename)
        except (ROSBagException, IOError), ex:
            print >> sys.stderr, 'ERROR reading %s: %s' % (inbag_filename, str(ex))
            continue
        inbag.close()

        # Rename the input bag to ###.orig.###, and open for reading
        (root, ext) = os.path.splitext(inbag_filename)
        backup_filename = '%s.orig%s' % (root, ext)
        
        if not force and os.path.exists(backup_filename):
            if not quiet:
                print >> sys.stderr, 'Skipping %s. Backup path %s already exists.' % (inbag_filename, backup_filename)
            continue

        try:
            os.rename(inbag_filename, backup_filename)
        except OSError, ex:
            print >> sys.stderr, 'ERROR moving %s to %s: %s' % (inbag_filename, backup_filename, str(ex))
            continue
        outbag_filename = inbag_filename

        try:
            inbag = Bag(backup_filename)

            # Open the output bag file for writing
            try:
                outbag = Bag(outbag_filename, 'w')
            except (ROSBagException, IOError), ex:
                print >> sys.stderr, 'ERROR writing %s: %s' % (outbag_filename, str(ex))
                inbag.close()
                continue
            
            # Perform the operation
            try:
                op(inbag, outbag, quiet=quiet)
            except ROSBagException, ex:
                print >> sys.stderr, 'ERROR operating on %s: %s' % (inbag_filename, str(ex))
                inbag.close()
                outbag.close()
                continue
                
            outbag.close()
            inbag.close()

        except KeyboardInterrupt:
            try:
                os.rename(backup_filename, inbag_filename)
            except OSError, ex:
                print >> sys.stderr, 'ERROR moving %s to %s: %s', (backup_filename, inbag_filename, str(ex))
                break
            
        except (ROSBagException, IOError), ex:
            print >> sys.stderr, 'ERROR operating on %s: %s' % (inbag_filename, str(ex))

def change_compression_op(inbag, outbag, compression, quiet):
    outbag.compression = compression

    if quiet:
        for topic, msg, t in inbag.read_messages(raw=True):
            outbag.write(topic, msg, t, raw=True)
    else:   
        meter = ProgressMeter(outbag.filename, inbag.size)
    
        total_bytes = 0
        for topic, msg, t in inbag.read_messages(raw=True):
            msg_type, serialized_bytes, md5sum, pos, pytype = msg
    
            outbag.write(topic, msg, t, raw=True)
            
            total_bytes += len(serialized_bytes) 
            meter.step(total_bytes)
        
        meter.finish()

class RosbagCmds(UserDict.UserDict):
    def __init__(self):
        UserDict.UserDict.__init__(self)

        self['help'] = self.help_cmd

    def get_valid_cmds(self):
        str = "Available subcommands:\n"
        for k in sorted(self.keys()):
            str += "   %s\n" % k

        return str

    def help_cmd(self,argv):
        argv = [a for a in argv if a != '-h' and a != '--help']

        if len(argv) == 0:
            print 'Usage: rosbag <subcommand> [options] [args]'
            print
            print self.get_valid_cmds()
            print 'For additional information, see http://code.ros.org/wiki/rosbag/'
            print
            return

        cmd = argv[0]
        if cmd in self:
            self[cmd](['-h'])
        else:
            print >> sys.stderr, "Unknown command: '%s'" % cmd
            print >> sys.stderr
            print >> sys.stderr, self.get_valid_cmds()

class ProgressMeter:
    def __init__(self, path, bytes_total, refresh_rate=1.0):
        self.path           = path
        self.bytes_total    = bytes_total
        self.refresh_rate   = refresh_rate
        
        self.elapsed        = 0.0
        self.update_elapsed = 0.0
        self.bytes_read     = 0.0

        self.start_time     = time.time()

        self._update_progress()

    def step(self, bytes_read, force_update=False):
        self.bytes_read = bytes_read
        self.elapsed    = time.time() - self.start_time
        
        if force_update or self.elapsed - self.update_elapsed > self.refresh_rate:
            self._update_progress()
            self.update_elapsed = self.elapsed

    def _update_progress(self):
        max_path_len = self.terminal_width() - 37
        path = self.path
        if len(path) > max_path_len:
            path = '...' + self.path[-max_path_len + 3:]

        bytes_read_str  = self._human_readable_size(float(self.bytes_read))
        bytes_total_str = self._human_readable_size(float(self.bytes_total))
        
        if self.bytes_read < self.bytes_total:
            complete_fraction = float(self.bytes_read) / self.bytes_total
            pct_complete      = int(100.0 * complete_fraction)

            if complete_fraction > 0.0:
                eta = self.elapsed * (1.0 / complete_fraction - 1.0)
                eta_min, eta_sec = eta / 60, eta % 60
                if eta_min > 99:
                    eta_str = '--:--'
                else:
                    eta_str = '%02d:%02d' % (eta_min, eta_sec)
            else:
                eta_str = '--:--'

            progress = '%-*s %3d%% %8s / %8s %s ETA' % (max_path_len, path, pct_complete, bytes_read_str, bytes_total_str, eta_str)
        else:
            progress = '%-*s 100%% %19s %02d:%02d    ' % (max_path_len, path, bytes_total_str, self.elapsed / 60, self.elapsed % 60)

        print '\r', progress,
        sys.stdout.flush()
        
    def _human_readable_size(self, size):
        multiple = 1024.0
        for suffix in ['KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']:
            size /= multiple
            if size < multiple:
                return '%.1f %s' % (size, suffix)
    
        raise ValueError('number too large')

    def finish(self):
        self.step(self.bytes_total, force_update=True)
        print

    @staticmethod
    def terminal_width():
        """Estimate the width of the terminal"""
        width = 0
        try:
            import struct, fcntl, termios
            s     = struct.pack('HHHH', 0, 0, 0, 0)
            x     = fcntl.ioctl(1, termios.TIOCGWINSZ, s)
            width = struct.unpack('HHHH', x)[1]
        except IOError:
            pass
        if width <= 0:
            try:
                width = int(os.environ['COLUMNS'])
            except:
                pass
        if width <= 0:
            width = 80
    
        return width

def rosbagmain(argv=None):
    cmds = RosbagCmds()
    cmds['record']     = record_cmd
    cmds['info']       = info_cmd
    cmds['play']       = play_cmd
    cmds['check']      = check_cmd
    cmds['fix']        = fix_cmd
    cmds['filter']     = filter_cmd
    cmds['compress']   = compress_cmd
    cmds['decompress'] = decompress_cmd

    if argv is None:
        argv = sys.argv

    if '-h' in argv or '--help' in argv:
        argv = [a for a in argv if a != '-h' and a != '--help']
        argv.insert(1, 'help')

    if len(argv) > 1:
        cmd = argv[1]
    else:
        cmd = 'help'

    try:
        if cmd in cmds:
            cmds[cmd](argv[2:])
        else:
            cmds['help']([cmd])
    except KeyboardInterrupt:
        pass
    