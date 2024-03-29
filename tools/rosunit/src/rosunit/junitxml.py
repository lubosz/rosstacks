#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
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

"""
Library for reading and manipulating Ant JUnit XML result files.
"""

from __future__ import print_function

import os
import sys
import cStringIO
import string
import codecs
import re

from xml.dom.minidom import parse, parseString
from xml.dom import Node as DomNode

import rospkg

class TestInfo(object):
    """
    Common container for 'error' and 'failure' results
    """
    
    def __init__(self, type_, text):
        """
        @param type_: type attribute from xml 
        @type  type_: str
        @param text: text property from xml
        @type  text: str
        """
        self.type = type_
        self.text = text

class TestError(TestInfo):
    """
    'error' result container        
    """
    def xml(self):
        return u'<error type="%s"><![CDATA[%s]]></error>'%(self.type, self.text)            

class TestFailure(TestInfo):
    """
    'failure' result container        
    """
    def xml(self):
        return u'<failure type="%s"><![CDATA[%s]]></failure>'%(self.type, self.text)            


class TestCaseResult(object):
    """
    'testcase' result container
    """
    
    def __init__(self, name):
        """
        @param name: name of testcase
        @type  name: str
        """
        self.name = name
        self.failures = []
        self.errors = []
        self.time = 0.0
        self.classname = ''
        
    def _passed(self):
        """
        @return: True if test passed
        @rtype: bool
        """
        return not self.errors and not self.failures
    ## bool: True if test passed without errors or failures
    passed = property(_passed)
    
    def _failure_description(self):
        """
        @return: description of testcase failure
        @rtype: str
        """
        if self.failures:
            tmpl = "[%s][FAILURE]"%self.name
            tmpl = tmpl + '-'*(80-len(tmpl))
            tmpl = tmpl+"\n%s\n"+'-'*80+"\n\n"
            return '\n'.join(tmpl%x.text for x in self.failures)
        return ''

    def _error_description(self):
        """
        @return: description of testcase error
        @rtype: str
        """
        if self.errors:
            tmpl = "[%s][ERROR]"%self.name
            tmpl = tmpl + '-'*(80-len(tmpl))
            tmpl = tmpl+"\n%s\n"+'-'*80+"\n\n"
            return '\n'.join(tmpl%x.text for x in self.errors)
        return ''

    def _description(self):
        """
        @return: description of testcase result
        @rtype: str
        """
        if self.passed:
            return "[%s][passed]\n"%self.name
        else:
            return self._failure_description()+\
                   self._error_description()                   
    ## str: printable description of testcase result
    description = property(_description)
    def add_failure(self, failure):
        """
        @param failure TestFailure
        """
        self.failures.append(failure)

    def add_error(self, error):
        """
        @param failure TestError        
        """
        self.errors.append(error)

    def xml(self):
        return u'  <testcase classname="%s" name="%s" time="%s">\n'%(self.classname, self.name, self.time)+\
               '\n    '.join([f.xml() for f in self.failures])+\
               '\n    '.join([e.xml() for e in self.errors])+\
               '  </testcase>'
        
class Result(object):
    __slots__ = ['name', 'num_errors', 'num_failures', 'num_tests', \
                 'test_case_results', 'system_out', 'system_err', 'time']
    def __init__(self, name, num_errors=0, num_failures=0, num_tests=0):
        self.name = name
        self.num_errors = num_errors
        self.num_failures = num_failures
        self.num_tests = num_tests
        self.test_case_results = []
        self.system_out = ''
        self.system_err = ''
        self.time = 0.0

    def accumulate(self, r):
        """
        Add results from r to this result
        @param r: results to aggregate with this result
        @type  r: Result
        """
        self.num_errors += r.num_errors
        self.num_failures += r.num_failures
        self.num_tests += r.num_tests
        self.time += r.time
        self.test_case_results.extend(r.test_case_results)
        if r.system_out:
            self.system_out += '\n'+r.system_out
        if r.system_err:
            self.system_err += '\n'+r.system_err

    def add_test_case_result(self, r):
        """
        Add results from a testcase to this result container
        @param r: TestCaseResult
        @type  r: TestCaseResult
        """
        self.test_case_results.append(r)

    def xml(self):
        """
        @return: document as unicode (UTF-8 declared) XML according to Ant JUnit spec
        """
        return u'<?xml version="1.0" encoding="utf-8"?>'+\
               '<testsuite name="%s" tests="%s" errors="%s" failures="%s" time="%s">'%\
               (self.name, self.num_tests, self.num_errors, self.num_failures, self.time)+\
               '\n'.join([tc.xml() for tc in self.test_case_results])+\
               '  <system-out><![CDATA[%s]]></system-out>'%self.system_out+\
               '  <system-err><![CDATA[%s]]></system-err>'%self.system_err+\
               '</testsuite>'

def _text(tag):
    return reduce(lambda x, y: x + y, [c.data for c in tag.childNodes if c.nodeType in [DomNode.TEXT_NODE, DomNode.CDATA_SECTION_NODE]], "").strip()

def _load_suite_results(test_suite_name, test_suite, result):
    nodes = [n for n in test_suite.childNodes \
             if n.nodeType == DomNode.ELEMENT_NODE]
    for node in nodes:
        name = node.tagName
        if name == 'testsuite':
            # for now we flatten this hierarchy
            _load_suite_results(test_suite_name, node, result)
        elif name == 'system-out':
            if _text(node):
                system_out = "[%s] stdout"%test_suite_name + "-"*(71-len(test_suite_name))
                system_out += '\n'+_text(node)
                result.system_out += system_out
        elif name == 'system-err':
            if _text(node):
                system_err = "[%s] stderr"%test_suite_name + "-"*(71-len(test_suite_name))
                system_err += '\n'+_text(node)
                result.system_err += system_err
        elif name == 'testcase':
            name = node.getAttribute('name') or 'unknown'
            classname = node.getAttribute('classname') or 'unknown'

            # mangle the classname for some sense of uniformity
            # between rostest/unittest/gtest
            if '__main__.' in classname:
              classname = classname[classname.find('__main__.')+9:]
            if classname == 'rostest.rostest.RosTest':
              classname = 'rostest'
            elif not classname.startswith(result.name):
              classname = "%s.%s"%(result.name,classname)
              
            time = float(node.getAttribute('time')) or 0.0
            tc_result = TestCaseResult("%s/%s"%(test_suite_name,name))
            tc_result.classname = classname
            tc_result.time = time            
            result.add_test_case_result(tc_result)
            for d in [n for n in node.childNodes \
                      if n.nodeType == DomNode.ELEMENT_NODE]:
                # convert 'message' attributes to text elements to keep
                # python unittest and gtest consistent
                if d.tagName == 'failure':
                    message = d.getAttribute('message') or ''
                    text = _text(d) or message
                    x = TestFailure(d.getAttribute('type') or '', text)
                    tc_result.add_failure(x)
                elif d.tagName == 'error':
                    message = d.getAttribute('message') or ''
                    text = _text(d) or message                    
                    x = TestError(d.getAttribute('type') or '', text)
                    tc_result.add_error(x)

## #603: unit test suites are not good about screening out illegal
## unicode characters. This little recipe I from http://boodebr.org/main/python/all-about-python-and-unicode#UNI_XML
## screens these out
RE_XML_ILLEGAL = u'([\u0000-\u0008\u000b-\u000c\u000e-\u001f\ufffe-\uffff])' + \
                 u'|' + \
                 u'([%s-%s][^%s-%s])|([^%s-%s][%s-%s])|([%s-%s]$)|(^[%s-%s])' % \
                 (unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff),
                  unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff),
                  unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff))
_safe_xml_regex = re.compile(RE_XML_ILLEGAL)

def _read_file_safe_xml(test_file):
    """
    read in file, screen out unsafe unicode characters
    """
    f = None
    try:
        # this is ugly, but the files in question that are problematic
        # do not declare unicode type.
        if not os.path.isfile(test_file):
            raise Exception("test file does not exist")
        try:
            f = codecs.open(test_file, "r", "utf-8" )
            x = f.read()
        except:
            if f is not None:
                f.close()
            f = codecs.open(test_file, "r", "iso8859-1" )
            x = f.read()        

        for match in _safe_xml_regex.finditer(x):
            x = x[:match.start()] + "?" + x[match.end():]
        return x.encode("utf-8")
    finally:
        if f is not None:
            f.close()

def read(test_file, test_name):
    """
    Read in the test_result file
    @param test_file: test file path
    @type  test_file: str
    @param test_name: name of test                    
    @type  test_name: str
    @return: test results
    @rtype: Result
    """
    try:
        xml_str = _read_file_safe_xml(test_file)
        if not xml_str.strip():
            print("WARN: test result file is empty [%s]"%(test_file))
            return Result(test_name, 0, 0, 0)
        test_suites = parseString(xml_str).getElementsByTagName('testsuite')
    except Exception as e:
        print("WARN: cannot read test result file [%s]: %s"%(test_file, str(e)))
        return Result(test_name, 0, 0, 0)
    if not test_suites:
        print("WARN: test result file [%s] contains no results"%(test_file))
        return Result(test_name, 0, 0, 0)

    results = Result(test_name, 0, 0, 0)
    for test_suite in test_suites:
        #test_suite = test_suite[0]
        vals = [test_suite.getAttribute(attr) for attr in ['errors', 'failures', 'tests']]
        vals = [v or 0 for v in vals]
        err, fail, tests = [string.atoi(val) for val in vals]

        result = Result(test_name, err, fail, tests)
        result.time = float(test_suite.getAttribute('time')) or 0.0    

        # Create a prefix based on the test result filename. The idea is to
        # disambiguate the case when tests of the same name are provided in
        # different .xml files.  We use the name of the parent directory
        test_file_base = os.path.basename(os.path.dirname(os.path.abspath(test_file)))
        fname = os.path.basename(test_file)
        if fname.startswith('TEST-'):
            fname = fname[5:]
        if fname.endswith('.xml'):
            fname = fname[:-4]
        test_file_base = "%s.%s"%(test_file_base, fname)
        _load_suite_results(test_file_base, test_suite, result)
        results.accumulate(result)
    return results

def read_all(filter_=[]):
    """
    Read in the test_results and aggregate into a single Result object
    @param filter_: list of packages that should be processed
    @type filter_: [str]
    @return: aggregated result
    @rtype: L{Result}
    """
    dir_ = rospkg.get_test_results_dir()
    root_result = Result('ros', 0, 0, 0)
    if not os.path.exists(dir_):
        return root_result
    for d in os.listdir(dir_):
        if filter_ and not d in filter_:
            continue
        subdir = os.path.join(dir_, d)
        if os.path.isdir(subdir):
            for filename in os.listdir(subdir):
                if filename.endswith('.xml'):
                    filename = os.path.join(subdir, filename)
                    result = read(filename, os.path.basename(subdir))
                    root_result.accumulate(result)
    return root_result


def test_failure_junit_xml(test_name, message, stdout=None):
    """
    Generate JUnit XML file for a unary test suite where the test failed
    
    @param test_name: Name of test that failed
    @type  test_name: str
    @param message: failure message
    @type  message: str
    @param stdout: stdout data to include in report
    @type  stdout: str
    """
    if not stdout:
      return """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="1" failures="1" time="1" errors="0" name="%s">
  <testcase name="test_ran" status="run" time="1" classname="Results">
  <failure message="%s" type=""/>
  </testcase>
</testsuite>"""%(test_name, message)
    else:
      return """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="1" failures="1" time="1" errors="0" name="%s">
  <testcase name="test_ran" status="run" time="1" classname="Results">
  <failure message="%s" type=""/>
  </testcase>
  <system-out><![CDATA[[
%s
]]></system-out>
</testsuite>"""%(test_name, message, stdout)

def test_success_junit_xml(test_name):
    """
    Generate JUnit XML file for a unary test suite where the test succeeded.
    
    @param test_name: Name of test that passed
    @type  test_name: str
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="1" failures="0" time="1" errors="0" name="%s">
  <testcase name="test_ran" status="run" time="1" classname="Results">
  </testcase>
</testsuite>"""%(test_name)

def print_summary(junit_results, runner_name='ROSUNIT'):
    """
    Print summary of junitxml results to stdout.
    """
    # we have two separate result objects, which can be a bit
    # confusing. 'result' counts successful _running_ of tests
    # (i.e. doesn't check for actual test success). The 'r' result
    # object contains results of the actual tests.
    
    buff = cStringIO.StringIO()
    buff.write("[%s]"%runner_name+'-'*71+'\n\n')
    for tc_result in junit_results.test_case_results:
        buff.write(tc_result.description)

    buff.write('\nSUMMARY\n')
    if (junit_results.num_errors + junit_results.num_failures) == 0:
        buff.write("\033[32m * RESULT: SUCCESS\033[0m\n")
    else:
        buff.write("\033[1;31m * RESULT: FAIL\033[0m\n")

    # TODO: still some issues with the numbers adding up if tests fail to launch

    # number of errors from the inner tests, plus add in count for tests
    # that didn't run properly ('result' object).
    buff.write(" * TESTS: %s\n"%junit_results.num_tests)
    num_errors = junit_results.num_errors
    if num_errors:
        buff.write("\033[1;31m * ERRORS: %s\033[0m\n"%num_errors)
    else:
        buff.write(" * ERRORS: 0\n")
    num_failures = junit_results.num_failures
    if num_failures:
        buff.write("\033[1;31m * FAILURES: %s\033[0m\n"%num_failures)
    else:
        buff.write(" * FAILURES: 0\n")

    print(buff.getvalue())

