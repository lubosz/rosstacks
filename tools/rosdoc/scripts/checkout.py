#!/usr/bin/env python

USAGE = 'checkout.py <rosbrowse_repos_list> <rosdoc_repos_list>'

import fileinput
import sys
import os
import traceback

import roslib.vcs

def load_rosbrowse_list(fn):
  f_rosbrowse = fileinput.input(fn)
  all_repos = {}
  for l in f_rosbrowse:
    if l.startswith('#'):
      continue
    lsplit = l.split()
    if len(lsplit) != 3:
      continue
    key, vcs, uri = lsplit
    all_repos[key] = (vcs, uri)
  return all_repos

def load_rosdoc_list(fn, all_repos):
  f_rosdoc = fileinput.input(fn)
  repos = {}
  for l in f_rosdoc:
    if l.startswith('#'):
      continue
    lsplit = l.split()
    key = lsplit[0].strip()
    if key == 'ros':
      continue
    if key not in all_repos:
      continue
    repos[key] = all_repos[key]
  return repos

def checkout_repos(repos):
  for key in repos:
    vcs, url = repos[key]
    try:
      roslib.vcs.checkout(vcs, url, key)
    except:
      # soft-fail. This happens way too often with so many diverse
      # repos. Failure in this case usually just means that the
      # checkout is stale as there is often already a copy
      traceback.print_exc()

def write_setup_file(repos):
  str = 'export ROS_PACKAGE_PATH='
  for key in repos:
    str += os.path.abspath(key) + ':'
  f = open(os.path.abspath('setup.bash'), 'w')
  f.write('%s\n'%str)
  f.close()

def main(argv):
  if len(argv) != 3:
    print USAGE
    sys.exit(1)
  rosbrowse = argv[1]
  rosdoc = argv[2]

  all_repos = load_rosbrowse_list(rosbrowse)
  repos = load_rosdoc_list(rosdoc, all_repos)
  if repos:
    checkout_repos(repos)
    write_setup_file(repos)
  
if __name__ == "__main__":
  main(sys.argv)
