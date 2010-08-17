# Software License Agreement (BSD License)
#
# Copyright (c) 2009, Willow Garage, Inc.
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
#
# Revision $Id$
# $Author$
from __future__ import with_statement

import codecs
import os
import sys
import traceback

import roslib.msgs
import roslib.rospack
import roslib.srvs
import roslib.stacks
import roslib.packages
import roslib.vcs

_api_url = "http://ros.org/doc/api/"
def package_link(package):
    return _api_url + package + "/html/"
def stack_link(stack):
    return _api_url + stack + "/html/"

def _generate_package_headers(ctx, p):
    import yaml
    m = ctx.manifests[p]
    m.description = m.description or ''
    d = {
        'brief': m.brief,
        'description': m.description.strip() or '',
        'license': m.license or '',
        'authors': m.author or '',
        'depends': [d.package for d in m.depends],
        'review_status': m.status or '',
        'review_notes': m.notes or '',
        'url': m.url,
        }
  
    if m.versioncontrol:
        d['version_control'] = m.versioncontrol.url
          
    siblings = []
    stack = roslib.stacks.stack_of(p) or ''
    if stack:
        d['stack'] = stack
        d['siblings'] = roslib.stacks.packages_of(stack)
  
    d['depends_on'] = roslib.rospack.rospack_depends_on_1(p)
      
    d['api_documentation'] = package_link(p)
  
    if p in ctx.external_docs:
        d['external_documentation'] = ctx.external_docs[p]
  
    d['msgs'] = roslib.msgs.list_msg_types(p, False)
    d['srvs'] = roslib.srvs.list_srv_types(p, False)        
  
    d['dependency_tree'] = package_link(p) + '%s_deps.pdf'%p
  
    # encode unicode entries. This is probably overkill, but it was hard
    # hunting the unicode encoding issues down
    d_copy = d.copy()
    for k, v in d_copy.iteritems():
        if isinstance(v, basestring):
            try:
                d[k] = v.encode("utf-8")
            except UnicodeDecodeError, e:
                print >> sys.stderr, "error: cannot encode value for key", k
                d[k] = ''
        elif type(v) == list:
            try:
                d[k] = [x.encode("utf-8") for x in v]
            except UnicodeDecodeError, e:
                print >> sys.stderr, "error: cannot encode value for key", k
                d[k] = []
                
    # Try to get VCS repo info
    vcs, repo = roslib.vcs.guess_vcs_uri(roslib.packages.get_pkg_dir(p))
    #  - if we have the repo map, use it instead for canonical
    #    URIs. There is the possibility that if there are two 'repos'
    #    mounted in the same SVN it will get confused, though the
    #    'guess_vcs_uri' technique is just as bad.
    if ctx.repos:
        for r_vcs, r_uri in ctx.repos.itervalues():
            if r_vcs == vcs and \
                    (r_uri.startswith(repo) or repo.starswith(r_uri)):
                repo = r_uri
                break

    if repo is not None:
        d['repository'] = repo
        d['vcs'] = vcs
  
    file_p = os.path.join(ctx.docdir, p, 'manifest.yaml')
    file_p_dir = os.path.dirname(file_p)
    if not os.path.isdir(file_p_dir):
        os.makedirs(file_p_dir)
    with codecs.open(file_p, mode='w', encoding='utf-8') as f:
        f.write(yaml.dump(d))
    
def generate_package_headers(ctx):
    """
    Generate manifest.yaml files for MoinMoin PackageHeader macro
    """
    try:
        import yaml
    except ImportError:
        print >> sys.stderr, "Cannot import yaml, will not generate MoinMoin PackageHeader files"
        return

    packages = ctx.packages
    for p in packages.iterkeys():
        if not ctx.should_document(p):
            continue
        try:
          #print "generating wiki files for", p
          _generate_package_headers(ctx, p)
        except Exception, e:
          traceback.print_exc()
          print >> sys.stderr, "Unable to generate manifest.yaml for "+p+str(e)
        
        
def _generate_stack_headers(ctx, s):
    import yaml
    m = ctx.stack_manifests[s]
    d = {
      'brief': m.brief,
      'description': m.description.strip() or '',
      'license': m.license or '',
      'authors': m.author or '',
      'depends': [d.stack for d in m.depends],
      'review_status': m.status or '',
      'review_notes': m.notes or '',
      'url': m.url,
      'packages': roslib.stacks.packages_of(s),
      'depends_on': roslib.rospack.rosstack_depends_on_1(s),
      }

    # Try to get VCS repo info
    vcs, repo = roslib.vcs.guess_vcs_uri(roslib.stacks.get_stack_dir(s))
    if repo is not None:
      d['repository'] = repo
      d['vcs'] = vcs

    # encode unicode entries
    d_copy = d.copy()
    for k, v in d_copy.iteritems():
        if isinstance(v, basestring):
            try:
                d[k] = v.encode("utf-8")
            except UnicodeDecodeError, e:
                print >> sys.stderr, "error: cannot encode value for key", k
                d[k] = ''
        elif type(v) == list:
            try:
                d[k] = [x.encode("utf-8") for x in v]
            except UnicodeDecodeError, e:
                print >> sys.stderr, "error: cannot encode value for key", k
                d[k] = []

    file_p = os.path.join(ctx.docdir, s, 'stack.yaml')
    file_p_dir = os.path.dirname(file_p)
    if not os.path.isdir(file_p_dir):
        os.makedirs(file_p_dir)
    print "writing stack properties to", file_p
    with codecs.open(file_p, mode='w', encoding='utf-8') as f:
        f.write(yaml.dump(d))
  

def generate_stack_headers(ctx):
    """
    Generate stack.yaml files for MoinMoin PackageHeader macro
    """
    try:
        import yaml
    except ImportError:
        print >> sys.stderr, "Cannot import yaml, will not generate MoinMoin StackHeader files"
        return

    stacks = ctx.stacks
    stack_dirs = set()
    for s in stacks.iterkeys():
        stack_dirs.add(s)
        try:
          #print "generating stack wiki files for", s
          _generate_stack_headers(ctx, s)
        except Exception, e:
          traceback.print_exc()
          print >> sys.stderr, "Unable to generate stack.yaml for "+s+str(e)


    return list(stack_dirs)
