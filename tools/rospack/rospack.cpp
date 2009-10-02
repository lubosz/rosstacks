/*
 * Copyright (C) 2008, Morgan Quigley and Willow Garage, Inc.
 * 
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *   * Redistributions of source code must retain the above copyright notice,
 *     this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright
 *     notice, this list of conditions and the following disclaimer in the
 *     documentation and/or other materials provided with the distribution.
 *   * Neither the names of Stanford University or Willow Garage, Inc. nor the names of its
 *     contributors may be used to endorse or promote products derived from
 *     this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

/* Author: Morgan Quigley, Brian Gerkey */

#include <cstdlib>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <string>
#include <vector>
#include <stack>
#include <queue>
#include <cassert>
#include <unistd.h>
#include <dirent.h>
#include <stdexcept>
#include <sys/time.h>
#include <sys/file.h>
#include <time.h>
#include <sstream>
#include <iterator>

#include <libgen.h>

#include "tinyxml-2.5.3/tinyxml.h"
#include "rospack/rospack.h"
using namespace std;

//#define VERBOSE_DEBUG
const double DEFAULT_MAX_CACHE_AGE = 60.0; // rebuild cache every minute

#include <sys/stat.h>
#ifndef S_ISDIR 
#define S_ISDIR(x) (((x) & S_IFMT) == S_IFDIR) 
#endif

namespace rospack
{

#ifdef __APPLE__
const string g_ros_os("osx");
#else
const string g_ros_os("linux");
#endif

//////////////////////////////////////////////////////////////////////////////
// Global storage for --foo options
// --deps-only
bool g_deps_only = false;
// --lang=
string g_lang;
// --attrib=
string g_attrib;
// --length=
string g_length;
// --top=
string g_top;
// The package name
string g_package;
// the number of entries to list in the profile table
int g_profile_length = 0;
// only display zombie directories in profile?
bool g_profile_zombie_only = false;

//////////////////////////////////////////////////////////////////////////////

const char *fs_delim = "/"; // ifdef this for windows

string deduplicate_tokens(const string& s);

Package::Package(string _path) : path(_path), 
        deps_calculated(false), direct_deps_calculated(false),
        descendants_calculated(false), manifest_loaded(false)
{
  vector<string> name_tokens;
  string_split(path, name_tokens, fs_delim);
  name = name_tokens.back();
}
bool Package::is_package(string path)
{
  return file_exists(path + string(fs_delim) + "manifest.xml");
}
bool Package::is_no_subdirs(string path)
{
  return file_exists(path + string(fs_delim) + "rospack_nosubdirs");
}
const VecPkg &Package::deps1()
{
  return direct_deps();
}
const VecPkg &Package::deps(traversal_order_t order, int depth)
{
  if (depth > 1000)
  {
    fprintf(stderr,"[rospack] woah! expanding the dependency tree made it blow "
                   "up.\n There must be a circular dependency somewhere.\n");
    throw runtime_error(string("circular dependency"));
  }
  if (deps_calculated)
    return _deps;
  // postorder traversal of the dependency tree
  VecPkg my_dd = direct_deps();
  for (VecPkg::iterator i = my_dd.begin(); i != my_dd.end(); ++i)
  {
    VecPkg d = (*i)->deps(order, depth+1); // recurse on direct dependencies
    if (order == PREORDER)
      _deps.push_back(*i);
    for (VecPkg::iterator j = d.begin(); j != d.end(); ++j)
    {
      // don't add things twice, but if you have something already
      // and we're doing a quasi-preorder traversal, bump it to the back
      bool have = false;
      VecPkg::iterator prior_loc;
      for (VecPkg::iterator k = _deps.begin(); k != _deps.end() && !have; ++k)
        if ((*k) == (*j))
        {
          prior_loc = k;
          have = true;
        }
      if (have && order == PREORDER)
      {
        _deps.erase(prior_loc);
        _deps.push_back(*j);
      }
      else if (!have)
        _deps.push_back(*j);
    }
    if (order == POSTORDER)
    {
      // only stuff it to the end if it isn't there already
      bool have = false;
      for (VecPkg::iterator k = _deps.begin(); k != _deps.end() && !have; ++k)
        if ((*k) == (*i))
          have = true;
      if (!have)
        _deps.push_back(*i);
    }
  }
  deps_calculated = true;
  return _deps;
}
string Package::manifest_path()
{
  return path + string(fs_delim) + "manifest.xml";
}
string Package::flags(string lang, string attrib)
{
  VecPkg d = deps(PREORDER);
  string s;
  // Conditionally include this package's exported flags, depending on
  // whether --deps-only was given
  if(!g_deps_only)
    s += this->direct_flags(lang, attrib) + string(" ");
  for (VecPkg::iterator i = d.begin(); i != d.end(); ++i)
  {
    string f = (*i)->direct_flags(lang, attrib);
    if (f.length())
      s += f + string(" ");
  }
  return s;
}

string Package::rosdep()
{
  string sd;
  TiXmlElement *mroot = manifest_root();
  for(TiXmlElement *sd_ele = mroot->FirstChildElement("rosdep");
      sd_ele;
      sd_ele = sd_ele->NextSiblingElement("rosdep"))
  {
    const char *att_str;
    if((att_str = sd_ele->Attribute("name")))
      sd += string("name: ") + string(att_str);
    sd += string("\n");
  }

  return sd;
}

string Package::versioncontrol()
{
  string sd;
  TiXmlElement *mroot = manifest_root();
  for(TiXmlElement *sd_ele = mroot->FirstChildElement("versioncontrol");
      sd_ele;
      sd_ele = sd_ele->NextSiblingElement("versioncontrol"))
  {
    const char *att_str;
    if((att_str = sd_ele->Attribute("type")))
      sd += string("type: ") + string(att_str);
    if((att_str = sd_ele->Attribute("url")))
      sd += string("\turl: ") + string(att_str);
    sd += string("\n");
  }

  return sd;
}

vector<pair<string, string> > Package::plugins()
{
  vector<pair<string, string> > plugins;

  VecPkg deplist;
  // If --top=foo was given, then restrict the search to packages that are
  // dependencies of foo, plus foo itself
  if(g_top.size())
  {
    Package* gtp = g_get_pkg(g_top);
    deplist = gtp->deps(Package::POSTORDER);
    deplist.push_back(gtp);
  }

  VecPkg desc1 = descendants1();
  desc1.push_back(this);
  VecPkg::iterator it = desc1.begin();
  VecPkg::iterator end = desc1.end();
  for (; it != end; ++it)
  {
    // If we're restricting the search, make sure this package is in the
    // deplist.  This could be made more efficient.
    if(deplist.size())
    {
      bool found = false;
      for(VecPkg::const_iterator dit = deplist.begin();
          dit != deplist.end();
          dit++)
      {
        if((*dit)->name == (*it)->name)
        {
          found = true;
          break;
        }
      }
      if(!found)
        continue;
    }
    std::string flags = (*it)->direct_flags(name, g_attrib);
    if (!flags.empty())
    {
      plugins.push_back(make_pair((*it)->name, flags));
    }
  }

  return plugins;
}


VecPkg Package::descendants1()
{
  VecPkg children;
  for (VecPkg::iterator p = pkgs.begin(); p != pkgs.end(); ++p)
  {
    // We catch exceptions here, because we don't care if some 
    // unrelated packages in the system have invalid manifests
    try
    {
      if ((*p)->has_parent(name))
        children.push_back(*p);
    }
    catch (runtime_error &e)
    {
    }
  }
  return children;
}

const vector<Package *> &Package::descendants(int depth)
{
  if (depth > 100)
  {
    fprintf(stderr, "[rospack] woah! circular dependency in the ros tree! aaaaaa!\n");
    throw runtime_error(string("circular dependency"));
  }
  if (descendants_calculated)
    return _descendants;
  VecPkg desc_with_dups;
  for (VecPkg::iterator p = pkgs.begin(); p != pkgs.end(); ++p)
  {
    // We catch exceptions here, because we don't care if some 
    // unrelated packages in the system have invalid manifests
    try
    {
      if ((*p)->has_parent(name))
      {
        desc_with_dups.push_back(*p);
        const VecPkg &p_desc = (*p)->descendants(depth+1);
        for (VecPkg::const_iterator q = p_desc.begin();
             q != p_desc.end(); ++q)
          desc_with_dups.push_back(*q);
      }
    }
    catch (runtime_error &e)
    {
    }
  }
  assert(_descendants.size() == 0);
  for (VecPkg::iterator p = desc_with_dups.begin();
       p != desc_with_dups.end(); ++p)
  {
    bool found = false;
    for (VecPkg::iterator q = _descendants.begin();
         q != _descendants.end() && !found; ++q)
      if ((*q)->name == (*p)->name)
        found = true;
    if (!found)
      _descendants.push_back(*p);
  }
  descendants_calculated = true;
  return _descendants;
}


bool Package::has_parent(string pkg)
{
  vector<Package *> parents = direct_deps(true);
  for (VecPkg::iterator i = parents.begin(); i != parents.end(); ++i)
    if ((*i)->name == pkg)
      return true;
  return false;
}

const vector<Package *> &Package::direct_deps(bool missing_package_as_warning)
{
  if (direct_deps_calculated)
    return _direct_deps;
#ifdef VERBOSE_DEBUG
  printf("calculating direct deps for package [%s]\n", name.c_str());
#endif
  TiXmlElement *mroot = manifest_root();
  TiXmlNode *dep_node = 0;
  while ((dep_node = mroot->IterateChildren(string("depend"), dep_node)))
  {
    TiXmlElement *dep_ele = dep_node->ToElement();
    assert(dep_ele);
    const char *dep_pkgname = dep_ele->Attribute("package");
    if (!dep_pkgname)
    {
      fprintf(stderr,"[rospack] bad depend syntax (no 'package' attribute) in [%s]\n", 
              manifest_path().c_str());
      throw runtime_error(string("invalid manifest"));
    }
    // Must make a copy here, because the call to g_get_pkg() below might
    // cause a recrawl, which blows aways the accumulated data structure.
    char* dep_pkgname_copy = strdup(dep_pkgname);
#ifdef VERBOSE_DEBUG
    printf("direct_deps: pkg %s has dep %s\n", name.c_str(), dep_pkgname_copy);
#endif 
    try
    {
      _direct_deps.push_back(g_get_pkg(dep_pkgname_copy));
    }
    catch (runtime_error &e)
    {
      if (missing_package_as_warning)
        fprintf(stderr, "[rospack] warning: couldn't find dependency [%s] of [%s]\n",
                dep_pkgname_copy, name.c_str());
      else
      {
        fprintf(stderr, "[rospack] couldn't find dependency [%s] of [%s]\n",
                dep_pkgname_copy, name.c_str());
        free(dep_pkgname_copy);
        throw runtime_error(string("missing dependency"));
      }
    }
    free(dep_pkgname_copy);
  }
  direct_deps_calculated = true;
  return _direct_deps;
}

string Package::direct_flags(string lang, string attrib)
{
  TiXmlElement *mroot = manifest_root();
  TiXmlElement *export_ele = mroot->FirstChildElement("export");
  if (!export_ele)
    return string("");
  TiXmlElement *best_usage = NULL;
  for (TiXmlElement *lang_ele = export_ele->FirstChildElement(lang); 
       lang_ele; lang_ele = lang_ele->NextSiblingElement(lang))
  {
    if (!best_usage)
      best_usage = lang_ele;
    const char *os_str;
    if ((os_str = lang_ele->Attribute("os")))
    {
      if (g_ros_os == string(os_str))
      {
        best_usage = lang_ele;
        break;
      }
    }
  }
  if (!best_usage)
    return string();
  const char *cstr = best_usage->Attribute(attrib.c_str());
  if (!cstr)
    return string();
  string s(cstr);
  while (1) // every decent C program has a while(1) in it
  {
    int i = s.find(string("${prefix}"));
    if (i < 0)
      break; // no more occurrences
    s.replace(i, string("${prefix}").length(), path);
  }

  // Do backquote substitution.  E.g.,  if we find this string:
  //   `pkg-config --cflags gdk-pixbuf-2.0`
  // We replace it with the result of executing the command
  // contained within the backquotes (reading from its stdout), which
  // might be something like:
  //   -I/usr/include/gtk-2.0 -I/usr/include/glib-2.0 -I/usr/lib/glib-2.0/include  

  // Construct and execute the string
  // We do the assignment first to ensure that if backquote expansion (or
  // anything else) fails, we'll get a non-zero exit status from pclose().
  string cmd = string("ret=\"") + s + string("\" && echo $ret");

  // Remove embedded newlines
  string token("\n");
  for (string::size_type s = cmd.find(token); s != string::npos;
       s = cmd.find(token, s))
  {
    cmd.replace(s,token.length(),string(" "));
  }

  FILE* p;
  if(!(p = popen(cmd.c_str(), "r")))
  {
    fprintf(stderr, "[rospack] warning: failed to execute backquote "
                    "expression \"%s\" in [%s]\n",
            cmd.c_str(), manifest_path().c_str());
    string errmsg = string("error in backquote expansion for ") + g_package;
    throw runtime_error(errmsg);
  }
  else
  {
    char buf[8192];
    memset(buf,0,sizeof(buf));
    // Read the command's output
    const char *fgets_ret = fgets(buf,sizeof(buf)-1,p);
    assert(fgets_ret);
    // Close the subprocess, checking exit status
    if(pclose(p) != 0)
    {
      fprintf(stderr, "[rospack] warning: got non-zero exit status from executing backquote expression \"%s\" in [%s]\n",
              cmd.c_str(), manifest_path().c_str());
      string errmsg = string("error in backquote expansion for ") + g_package;
      throw runtime_error(errmsg);
    }
    else
    {
      // Strip newline produced by many pkg-config style programs
      if(buf[strlen(buf)-1] == '\n')
        buf[strlen(buf)-1] = '\0';
      // Replace the backquote expression with the new text
      s = string(buf);
    }
  }

  return s;
}

void Package::load_manifest()
{
  if (manifest_loaded)
    return;
  if (!manifest.LoadFile(manifest_path()))
  {
    string errmsg = string("error parsing manifest file at [") + manifest_path().c_str() + string("]");
    fprintf(stderr, "[rospack] warning: error parsing manifest file at [%s]\n",
            manifest_path().c_str());
    // Only want this warning printed once.
    manifest_loaded = true;
    throw runtime_error(errmsg);
  }
}

TiXmlElement *Package::manifest_root()
{
  load_manifest();
  TiXmlElement *ele = manifest.RootElement();
  if (!ele)
  {
    string errmsg = string("error parsing manifest file at [") + manifest_path().c_str() + string("]");
    throw runtime_error(errmsg);
  }
  return ele;
}

VecPkg Package::pkgs;
VecPkg Package::deleted_pkgs;

//////////////////////////////////////////////////////////////////////////////

ROSPack *g_rospack = NULL; // singleton

ROSPack::ROSPack() : ros_root(NULL), cache_lock_failed(false), crawled(false)
{
  g_rospack = this;
  Package::pkgs.reserve(500); // get some space to avoid early recopying...
  ros_root = getenv("ROS_ROOT");
  if (!ros_root)
  {
    fprintf(stderr,"[rospack] ROS_ROOT is not defined in the environment.\n");
    throw runtime_error(string("no ROS_ROOT"));
  }
  if (!file_exists(ros_root))
  {
    fprintf(stderr,"[rospack] the path specified as ROS_ROOT is not " 
                   "accessible. Please ensure that this environment variable "
                   "is set and is writeable by your user account.\n");
    throw runtime_error(string("no ROS_ROOT"));
  }

  createROSHomeDirectory();

  crawl_for_packages();
}

ROSPack::~ROSPack() 
{ 
  for (VecPkg::iterator p = Package::pkgs.begin(); 
       p != Package::pkgs.end(); ++p)
    delete (*p);
  Package::pkgs.clear();
  for (VecPkg::iterator p = Package::deleted_pkgs.begin(); 
       p != Package::deleted_pkgs.end(); ++p)
    delete (*p);
  Package::deleted_pkgs.clear();
}

const char* ROSPack::usage()
{
  return "USAGE: rospack [options] <command> [package]\n"
          "  Allowed commands:\n"
          "    help\n"
          "    find [package]\n"
          "    list\n"
          "    list-names\n"
          "    langs\n"
          "    depends [package] (alias: deps)\n"
          "    depends-manifests [package] (alias: deps-manifests)\n"
          "    depends1 [package] (alias: deps1)\n"
          "    depends-indent [package] (alias: deps-indent)\n"
          "    rosdep [package] (alias: rosdeps)\n"
          "    rosdep0 [package] (alias: rosdeps0)\n"
          "    vcs [package]\n"
          "    vcs0 [package]\n"
          "    depends-on [package]\n"
          "    depends-on1 [package]\n"
          "    export [--deps-only] --lang=<lang> --attrib=<attrib> [package]\n"
          "    plugins --attrib=<attrib> [--top=<toppkg>] [package]\n"
          "    cflags-only-I [--deps-only] [package]\n"
          "    cflags-only-other [--deps-only] [package]\n"
          "    libs-only-L [--deps-only] [package]\n"
          "    libs-only-l [--deps-only] [package]\n"
          "    libs-only-other [--deps-only] [package]\n"
          "    profile [--length=<length>] [--zombie-only]\n\n"
          " If [package] is omitted, the current working directory\n"
          " is used (if it contains a manifest.xml).\n\n";
}

Package *ROSPack::get_pkg(string pkgname)
{
  for (VecPkg::iterator p = Package::pkgs.begin(); 
       p != Package::pkgs.end(); ++p)
  {
    if ((*p)->name == pkgname)
    {
      if(!crawled)
      {
        // Answer come from the cache; check that the path is valid, and
        // contains a manifest (#1115).
        std::string manifest_path = (*p)->path + fs_delim + "manifest.xml";
        struct stat s;
        if(stat(manifest_path.c_str(), &s) == 0)
        {
          // Answer looks good
          return (*p);
        }
        else
        {
          // Bad cache.  Warn and fall through to the recrawl below.
          fprintf(stderr, "[rospack] warning: invalid cached location %s for package %s; forcing recrawl\n",
                  (*p)->path.c_str(),
                  (*p)->name.c_str());
          break;
        }
      }
      else
      {
        // Answer came from a fresh crawl; no further checking needed.
        return (*p);
      }
    }
  }
  if (!crawled) // maybe it's a brand-new package. force a crawl.
  {
    crawl_for_packages(true); // will set the crawled flag; recursion is safe
    return get_pkg(pkgname);
  }
  string errmsg = string("couldn't find package [") + pkgname + string("]");
  throw runtime_error(errmsg);
  return NULL; // or not
}
  
int ROSPack::cmd_depends_on(bool include_indirect)
{
  // Explicitly crawl for packages, to ensure that we get newly added
  // dependent packages.  We also avoid the possibility of a recrawl
  // happening within the loop below, which could invalidate the pkgs 
  // vector as we loop over it.
  crawl_for_packages(true);

  Package* p;
  try
  {
    p = get_pkg(g_package);
  }
  catch(runtime_error)
  {
    fprintf(stderr, "[rospack] warning: package %s doesn't exist\n", 
            g_package.c_str());
    p = new Package(g_package);
    Package::pkgs.push_back(p);
  }
  assert(p);
  const VecPkg descendants = include_indirect ? p->descendants() 
          : p->descendants1();
  for (VecPkg::const_iterator p = descendants.begin(); 
       p != descendants.end(); ++p)
    printf("%s\n", (*p)->name.c_str());
  return 0;
}

int ROSPack::cmd_find()
{
  // todo: obey the search order
  Package *p = get_pkg(g_package);
  printf("%s\n", p->path.c_str());
  return 0;
}

int ROSPack::cmd_deps()
{
  VecPkg d = get_pkg(g_package)->deps(Package::POSTORDER);
  for (VecPkg::iterator i = d.begin(); i != d.end(); ++i)
    printf("%s\n", (*i)->name.c_str());
  return 0;
}

int ROSPack::cmd_deps_manifests()
{
  VecPkg d = get_pkg(g_package)->deps(Package::POSTORDER);
  for (VecPkg::iterator i = d.begin(); i != d.end(); ++i)
    printf("%s/manifest.xml ", (*i)->path.c_str());
  puts("");
  return 0;
}

int ROSPack::cmd_deps1()
{
  VecPkg d = get_pkg(g_package)->deps1();
  for (VecPkg::iterator i = d.begin(); i != d.end(); ++i)
    printf("%s\n", (*i)->name.c_str());
  return 0;
}

int ROSPack::cmd_depsindent(Package* pkg, int indent)
{
  VecPkg d = pkg->deps1();
  
  for (VecPkg::iterator i = d.begin(); i != d.end(); ++i)
  {
    for(int s=0; s<indent; s++)
      printf(" ");
    printf("%s\n", (*i)->name.c_str());
    cmd_depsindent(*i, indent+2);
  }
  return 0;
}

/*
int ROSPack::cmd_predeps(char **args, int args_len)
{
  if (args_len != 1)
    fprintf(stderr,"[rospack] usage: rospack predeps PACKAGE\n");
  else
  {
    VecPkg d = get_pkg(args[0])->deps(Package::PREORDER);
    for (VecPkg::iterator i = d.begin(); i != d.end(); ++i)
      printf("%s\n", (*i)->name.c_str());
  }
  return 0;
}
*/

static bool space(char c) { return isspace(c); }
static bool not_space(char c) { return !isspace(c); }
static vector<string> split_space(const string& str)
{
  typedef string::const_iterator iter;
  vector<string> ret;
  iter i = str.begin();
  while (i != str.end())
  {
    i = find_if(i, str.end(), not_space);
    iter j = find_if(i, str.end(), space);
    if (i != str.end())
      while (j != str.end() && *(j-1) == '\\')
        j = find_if(j+1, str.end(), space);
      ret.push_back(string(i, j));
    i = j;
  }
  return ret;
}

string ROSPack::snarf_libs(string flags, bool invert)
{
  vector<string> tokens = split_space(flags);
  string snarfed;
  for (size_t i = 0; i < tokens.size(); ++i)
  {
    //fprintf(stderr, "token = %s, len=%d, f=%c last=%s\n", tokens[i].c_str(), tokens[i].length(), tokens[i][0], tokens[i].substr(tokens[i].length()-2).c_str());
    if (invert)
    {
      if ((tokens[i].substr(0, 2) != "-l") &&
          (tokens[i].length() < 2 || tokens[i][0] != '/' || tokens[i].substr(tokens[i].length()-2) != ".a"))
        snarfed += (snarfed.length() ? " " : "" ) + tokens[i];
    }
    else
    {
      if (tokens[i].substr(0, 2) == "-l")
        snarfed += (snarfed.length() ? " " : "" ) + tokens[i].substr(2);
      else if (tokens[i].length() > 2 && tokens[i][0] == '/' && tokens[i].substr(tokens[i].length()-2) == ".a")
        snarfed += (snarfed.length() ? " " : "" ) + tokens[i];
    }
  }
  return snarfed;
}

string ROSPack::snarf_flags(string flags, string prefix, bool invert)
{
  vector<string> tokens = split_space(flags);
  string snarfed;
  for (size_t i = 0; i < tokens.size(); ++i)
  {
    if ((tokens[i].substr(0, prefix.length()) == prefix) ^ invert)
    {
      snarfed += (snarfed.length() ? " " : "" ) + tokens[i].substr(invert ? 0 : prefix.length());
    }
  }
  return snarfed;
}

int ROSPack::cmd_libs_only(string token)
{
  string lflags = get_pkg(g_package)->flags("cpp", "lflags");;
  if(!token.compare("-other"))
  {
    lflags = snarf_libs(lflags, true);
    lflags = snarf_flags(lflags, "-L", true);
  }
  else if(!token.compare("-l"))
  {
    lflags = snarf_libs(lflags);
  }
  else
  {
    lflags = snarf_flags(lflags, token);
    // tack on the bindeps path if it appears to be a good time to do so
    // note this may be superfluous since rosboost-cfg is likely bringing
    // the flags into the string already. perhaps at some point I should
    // skim through the lflags and see if getBinDepPath() is already in
    // there. It doesn't seem to hurt to duplicate it, though.
    // (also: may need to set the rpath if rosboost-cfg hasn't already done it)
    if (useBinDepPath())
      lflags += string(" ") + getBinDepPath() + string("/lib");
    lflags = deduplicate_tokens(lflags);
  }
  printf("%s\n", lflags.c_str());
  return 0;
}

int ROSPack::cmd_cflags_only(string token)
{
  string cflags = get_pkg(g_package)->flags("cpp", "cflags");
  if(!token.compare("-other"))
    cflags = snarf_flags(cflags, "-I", true);
  else
  {
    cflags = snarf_flags(cflags, token);
    // tack on the bindeps path if it appears to be a good time to do so
    if (useBinDepPath())
      cflags += string(" ") + getBinDepPath() + string("/include");
    cflags = deduplicate_tokens(cflags);
  }
  printf("%s\n", cflags.c_str());
  return 0;
}

void ROSPack::export_flags(string pkg, string lang, string attrib)
{
  string flags = get_pkg(pkg)->flags(lang, attrib);
  // hack up to add the /opt/ros flags for C++ system dependencies
  if (useBinDepPath() && lang == string("cpp"))
  {
    if (attrib == string("cflags"))
      flags += string(" -I") + getBinDepPath() + string("/include");
    else if (attrib == string("lflags"))
    {
      flags += string(" -L") + getBinDepPath() + string("/lib");
      flags += string(" -Wl,-rpath,") + getBinDepPath() + string("/lib");
    }
  }
  printf("%s\n", flags.c_str());
}

int ROSPack::cmd_versioncontrol(int depth)
{
  string sds;

  sds += get_pkg(g_package)->versioncontrol();

  if(depth < 0)
  {
    VecPkg descs = get_pkg(g_package)->deps(Package::POSTORDER);
    for(VecPkg::iterator dit = descs.begin();
        dit != descs.end();
        dit++)
    {
      sds += (*dit)->versioncontrol();
    }
  }

  printf("%s", sds.c_str());
  return 0;
}

int ROSPack::cmd_rosdep(int depth)
{
  string sds;
  sds += get_pkg(g_package)->rosdep();

  if(depth < 0)
  {
    VecPkg descs = get_pkg(g_package)->deps(Package::POSTORDER);
    for(VecPkg::iterator dit = descs.begin();
        dit != descs.end();
        dit++)
    {
      sds += (*dit)->rosdep();
    }
  }

  printf("%s", sds.c_str());
  return 0;
}

int ROSPack::cmd_export()
{
  export_flags(g_package, g_lang, g_attrib);
  return 0;
}

int ROSPack::cmd_plugins()
{
  Package* p = get_pkg(g_package);

  vector<pair<string, string> > plugins = p->plugins();
  vector<pair<string, string> >::iterator it = plugins.begin();
  vector<pair<string, string> >::iterator end = plugins.end();
  for (; it != end; ++it)
  {
    printf("%s %s\n", it->first.c_str(), it->second.c_str());
  }

  return 0;
}


int ROSPack::run(int argc, char **argv)
{
  assert(argc >= 2);
  int i;
  const char* opt_deps    = "--deps-only";
  const char* opt_zombie  = "--zombie-only";
  const char* opt_lang    = "--lang=";
  const char* opt_attrib  = "--attrib=";
  const char* opt_length  = "--length=";
  const char* opt_top     = "--top=";

  string errmsg = string(usage());

  i=1;
  const char* cmd = argv[i++];

  for(;i<argc;i++)
  {
    if(!strcmp(argv[i], opt_deps))
      g_deps_only=true;
    else if(!strcmp(argv[i], opt_zombie))
      g_profile_zombie_only=true;
    else if(!strncmp(argv[i], opt_lang, strlen(opt_lang)))
    {
      if(g_lang.size())
        throw runtime_error(errmsg);
      else if(strlen(argv[i]) > strlen(opt_lang))
        g_lang = string(argv[i]+strlen(opt_lang));
      else
        throw runtime_error(errmsg);
    }
    else if(!strncmp(argv[i], opt_attrib, strlen(opt_attrib)))
    {
      if(g_attrib.size())
        throw runtime_error(errmsg);
      else if(strlen(argv[i]) > strlen(opt_attrib))
        g_attrib = string(argv[i]+strlen(opt_attrib));
      else
        throw runtime_error(errmsg);
    }
    else if(!strncmp(argv[i], opt_length, strlen(opt_length)))
    {
      if(strlen(argv[i]) > strlen(opt_length))
        g_length = string(argv[i]+strlen(opt_length));
      else
        throw runtime_error(errmsg);
    }
    else if(!strncmp(argv[i], opt_top, strlen(opt_top)))
    {
      if(strlen(argv[i]) > strlen(opt_top))
        g_top = string(argv[i]+strlen(opt_top));
      else
        throw runtime_error(errmsg);
    }
    else
      break;
  }
  
  if(strcmp(cmd, "profile") && (g_length.size() || g_profile_zombie_only))
    throw runtime_error(errmsg);
  
  // --top= is only valid for plugins
  if(strcmp(cmd, "plugins") && g_top.size())
    throw runtime_error(errmsg);

  // --attrib= is only valid for export and plugins
  if((strcmp(cmd, "export") && strcmp(cmd, "plugins")) && 
     g_attrib.size())
    throw runtime_error(errmsg);

  // --lang= is only valid for export
  if((strcmp(cmd, "export") && g_lang.size()))
    throw runtime_error(errmsg);
  
  // export requires both --lang and --attrib
  if(!strcmp(cmd, "export") && (!g_lang.size() || !g_attrib.size()))
    throw runtime_error(errmsg);
    
  // plugins requires --attrib
  if(!strcmp(cmd, "plugins") && !g_attrib.size())
    throw runtime_error(errmsg);

  if(g_deps_only && 
     strcmp(cmd, "export") &&
     strcmp(cmd, "cflags-only-I") &&
     strcmp(cmd, "cflags-only-other") &&
     strcmp(cmd, "libs-only-L") &&
     strcmp(cmd, "libs-only-l") &&
     strcmp(cmd, "libs-only-other"))
    throw runtime_error(errmsg);

  if(i < argc)
  {
    if(!strcmp(cmd, "help") ||
       !strcmp(cmd, "list") ||
       !strcmp(cmd, "list-names") ||
       !strcmp(cmd, "langs") ||
       !strcmp(cmd, "profile"))
      throw runtime_error(errmsg);

    g_package = string(argv[i++]);
  }
  // Are we sitting in a package?
  else if(Package::is_package("."))
  {
    char buf[1024];
    if(!getcwd(buf,sizeof(buf)))
      throw runtime_error(errmsg);
    g_package = string(basename(buf));
  }

  if (i != argc)
    throw runtime_error(errmsg);

  if (!strcmp(cmd, "profile"))
  {
    if (g_length.size())
      g_profile_length = atoi(g_length.c_str());
    else
    {
      if(g_profile_zombie_only)
        g_profile_length = -1; // default is infinite
      else
        g_profile_length = 20; // default is about a screenful or so
    }
#ifdef VERBOSE_DEBUG
    printf("profile_length = %d\n", g_profile_length);
#endif
    // re-crawl with profiling enabled
    crawl_for_packages(true);
    return 0;
  }
  else if (!strcmp(cmd, "find"))
    return cmd_find();
  else if (!strcmp(cmd, "list"))
    return cmd_print_package_list(true);
  else if (!strcmp(cmd, "list-names"))
    return cmd_print_package_list(false);
  else if (!strcmp(cmd, "langs"))
    return cmd_print_langs_list();
  else if (!strcmp(cmd, "depends") || !strcmp(cmd, "deps"))
    return cmd_deps();
  else if (!strcmp(cmd, "depends-manifests") || !strcmp(cmd, "deps-manifests"))
    return cmd_deps_manifests();
  else if (!strcmp(cmd, "depends1") || !strcmp(cmd, "deps1"))
    return cmd_deps1();
  else if (!strcmp(cmd, "depends-indent") || !strcmp(cmd, "deps-indent"))
    return cmd_depsindent(get_pkg(g_package), 0);
  else if (!strcmp(cmd, "depends-on"))
    return cmd_depends_on(true);
  else if (!strcmp(cmd, "depends-on1"))
    return cmd_depends_on(false);
  /*
  else if (!strcmp(argv[i], "predeps"))
    return cmd_predeps(argv+i+1, argc-i-1);
    */
  else if (!strcmp(cmd, "export"))
    return cmd_export();
  else if (!strcmp(cmd, "plugins"))
    return cmd_plugins();
  else if (!strcmp(cmd, "rosdep") || !strcmp(cmd, "rosdeps"))
    return cmd_rosdep(-1);
  else if (!strcmp(cmd, "rosdep0") || !strcmp(cmd, "rosdeps0"))
    return cmd_rosdep(0);
  else if (!strcmp(cmd, "vcs"))
    return cmd_versioncontrol(-1);
  else if (!strcmp(cmd, "vcs0"))
    return cmd_versioncontrol(0);
  else if (!strcmp(cmd, "libs-only-l"))
    return cmd_libs_only("-l");
  else if (!strcmp(cmd, "libs-only-L"))
    return cmd_libs_only("-L");
  else if (!strcmp(cmd, "libs-only-other"))
    return cmd_libs_only("-other");
  else if (!strcmp(cmd, "cflags-only-I"))
    return cmd_cflags_only("-I");
  else if (!strcmp(cmd, "cflags-only-other"))
    return cmd_cflags_only("-other");
  else if (!strcmp(cmd, "help"))
    fputs(usage(), stderr);
  else
  {
    throw runtime_error(errmsg);
  }
  return 0;
}

int ROSPack::cmd_print_package_list(bool print_path)
{
  for (VecPkg::iterator i = Package::pkgs.begin(); 
       i != Package::pkgs.end(); ++i)
    if (print_path)
      printf("%s %s\n", (*i)->name.c_str(), (*i)->path.c_str());
    else
      printf("%s\n", (*i)->name.c_str());
  return 0;
}
  
int ROSPack::cmd_print_langs_list()
{
  // Check for packages that depend directly on roslang
  VecPkg lang_pkgs;
  Package* roslang;
  
  roslang = get_pkg("roslang");
  assert(roslang);

  lang_pkgs = roslang->descendants1();
  
  // Filter out packages mentioned in ROS_LANG_DISABLE
  char *disable = getenv("ROS_LANG_DISABLE");
  vector<string> disable_list;
  if(disable)
    string_split(disable, disable_list, ":");

  for(VecPkg::const_iterator i = lang_pkgs.begin();
      i != lang_pkgs.end();
      ++i)
  {
    vector<string>::const_iterator j;
    for(j = disable_list.begin();
        j != disable_list.end();
        ++j)
    {
      if((*j) == (*i)->name)
        break;
    }
    if(j == disable_list.end())
      printf("%s ", (*i)->name.c_str());
  }
  printf("\n");
  return 0;
}

void ROSPack::createROSHomeDirectory()
{
  char *homedir = getenv("HOME");
  if (!homedir) {
    //fprintf(stderr, "[rospack] WARNING: cannot create ~/.ros directory.\n");
  } 
  else 
  {
    string path = string(homedir) + "/.ros";
    if (!access(path.c_str(), R_OK) == 0) {
      if(mkdir(path.c_str(), 0700) != 0) {
        fprintf(stderr, "[rospack] WARNING: cannot create ~/.ros directory.\n");
      }
    }
  }
}

string ROSPack::getCachePath()
{
  string path;
  path = string(ros_root) + "/.rospack_cache";
  if (access(ros_root, W_OK) == 0) {
    return path;
  }

  // if we cannot write into the ros_root, then let's try to
  // write into the user's .ros directory.

  createROSHomeDirectory();

  path = string(getenv("HOME")) + "/.ros/rospack_cache";
  return path;
}

bool ROSPack::cache_is_good()
{
  string cache_path = getCachePath();
  // first see if it's new enough
  double cache_max_age = DEFAULT_MAX_CACHE_AGE;
  const char *user_cache_time_str = getenv("ROS_CACHE_TIMEOUT");
  if(user_cache_time_str)
    cache_max_age = atof(user_cache_time_str);
  if(cache_max_age == 0.0)
    return false;
  struct stat s;
  if (stat(cache_path.c_str(), &s) == 0)
  {
    double dt = difftime(time(NULL), s.st_mtime);
#ifdef VERBOSE_DEBUG
    printf("cache age: %f\n", dt);
#endif
    // Negative cache_max_age means it's always new enough.  It's dangerous
    // for the user to set this, but rosbash uses it.
    if ((cache_max_age > 0.0) && (dt > cache_max_age))
      return false;
  }
  // try to open it 
  FILE *cache = fopen(cache_path.c_str(), "r");
  if (!cache)
    return false; // it's not readable by us. sad.

  // see if ROS_ROOT and ROS_PACKAGE_PATH are identical
  char linebuf[30000];
  bool ros_root_ok = false, ros_package_path_ok = false;
  const char *ros_package_path = getenv("ROS_PACKAGE_PATH");
  while (!feof(cache))
  {
    linebuf[0] = 0;
    if (!fgets(linebuf, sizeof(linebuf), cache))
      break;
    if (!linebuf[0])
      continue;
    linebuf[strlen(linebuf)-1] = 0; // get rid of trailing newline
    if (linebuf[0] == '#')
    {
      if (!strncmp("#ROS_ROOT=", linebuf, 10))
      {
        if (!strcmp(linebuf+10, ros_root))
          ros_root_ok = true;
      }
      else if (!strncmp("#ROS_PACKAGE_PATH=", linebuf, 18))
      {
        if (!ros_package_path)
        {
          if (!strlen(linebuf+18))
            ros_package_path_ok = true;
        }
        else if (!strcmp(linebuf+18, getenv("ROS_PACKAGE_PATH")))
          ros_package_path_ok = true;
      }
    }
    else
      break; // we're out of the header. nothing more matters to this check.
  }
  fclose(cache);
  return ros_root_ok && ros_package_path_ok;
}

class CrawlQueueEntry
{
public:
  string path;
  double start_time, elapsed_time;
  size_t start_num_pkgs;
  bool has_manifest;
  CrawlQueueEntry(string _path) 
  : path(_path), start_time(0), elapsed_time(0), 
        start_num_pkgs(0), has_manifest(false){ }
  bool operator>(const CrawlQueueEntry &rhs) const
  {
    return elapsed_time > rhs.elapsed_time;
  }
};
  
double ROSPack::time_since_epoch()
{
  struct timeval tod;
  gettimeofday(&tod, NULL);
  return tod.tv_sec + 1e-6 * tod.tv_usec;
}

bool ROSPack::useBinDepPath()
{
  const char *bdp_env = getenv("ROS_BINDEPS_PATH");
  if (bdp_env)
    return file_exists(string(bdp_env));
  else
    return file_exists("/opt/ros");
}

string ROSPack::getBinDepPath()
{
  if (!useBinDepPath())
    return string();
  const char *bdp_env = getenv("ROS_BINDEPS_PATH");
  if (bdp_env)
    return string(bdp_env);
  else
    return string("/opt/ros");
}

void ROSPack::crawl_for_packages(bool force_crawl)
{
  for (VecPkg::iterator p = Package::pkgs.begin(); 
       p != Package::pkgs.end(); ++p)
    Package::deleted_pkgs.push_back(*p);
  Package::pkgs.clear();

  if(!force_crawl && cache_is_good())
  {
    string cache_path = getCachePath();
    FILE *cache = fopen(cache_path.c_str(), "r");
    if (cache) // one last check just in case nutty stuff happened in between
    {
#ifdef VERBOSE_DEBUG
      printf("trying to use cache...\n");
#endif
      char linebuf[30000];
      while (!feof(cache))
      {
        linebuf[0] = 0;
        if (!fgets(linebuf, sizeof(linebuf), cache))
          break; // error in read operation
        if (!linebuf[0] || linebuf[0] == '#')
          continue;
        char *newline_pos = strchr(linebuf, '\n');
        if (newline_pos)
          *newline_pos = 0;
        Package::pkgs.push_back(new Package(linebuf));
      }
      fclose(cache);
      return; // cache load went OK; we're done here.
    }
  }
  // if we get here, this means the cache either bogus or we've been
  // instructed to rebuild it.
#ifdef VERBOSE_DEBUG
  printf("building cache\n");
#endif
  deque<CrawlQueueEntry> q;
  q.push_back(CrawlQueueEntry(ros_root));
  if (char *rpp = getenv("ROS_PACKAGE_PATH"))
  {
    vector<string> rppvec;
    string_split(rpp, rppvec, ":");
    sanitize_rppvec(rppvec);
    for (vector<string>::iterator i = rppvec.begin(); i != rppvec.end(); ++i)
    {
      if(!i->size())
        continue;
      // Check whether this part of ROS_PACKAGE_PATH is itself a package
      if (Package::is_package(*i))
        Package::pkgs.push_back(new Package(*i));
      else if (Package::is_no_subdirs(*i))
        fprintf(stderr, "[rospack] WARNING: non-package directory in "
                        "ROS_PACKAGE_PATH marked rospack_nosubdirs:\n\t%s\n",
                i->c_str());
     else
        q.push_back(CrawlQueueEntry(*i));
    }
  }
  const double crawl_start_time = time_since_epoch();
  priority_queue<CrawlQueueEntry, vector<CrawlQueueEntry>, 
                 greater<CrawlQueueEntry> > profile;
  while (!q.empty())
  {
    CrawlQueueEntry cqe = q.front();
    q.pop_front();
    //printf("crawling %s\n", cqe.path.c_str());
    if (g_profile_length != 0)
    {
      if (cqe.start_time != 0)
      {
        // this stack symbol means we've already crawled its children, and it's
        // just here for timing purposes. 

        // save the traversal time 
        cqe.elapsed_time = time_since_epoch() - cqe.start_time;

        // Did the number of packages increase since we started crawling
        // this directory's children?  If not, then this is likely a zombie
        // directory that should probably be deleted.  We'll mark it as
        // such in the profile console output.
        if(cqe.start_num_pkgs < Package::pkgs.size())
          cqe.has_manifest = true;
        if(!g_profile_zombie_only || !cqe.has_manifest)
        {
          profile.push(cqe);
          if ((g_profile_length > 0) && (profile.size() > g_profile_length)) // only save the worst guys
            profile.pop();
        }
        continue;
      }
      cqe.start_time = time_since_epoch();
      cqe.start_num_pkgs = Package::pkgs.size();
      q.push_front(cqe);
    }
    DIR *d = opendir(cqe.path.c_str());
    if (!d)
    {
      fprintf(stderr, "[rospack] opendir error [%s] while crawling %s\n", 
              strerror(errno), cqe.path.c_str());
      continue;
    }
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL)
    {
      struct stat s;
      string child_path = cqe.path + fs_delim + string(ent->d_name);
      if (stat(child_path.c_str(), &s) != 0) 
        continue;
      if (!S_ISDIR(s.st_mode)) 
        continue;
      if (ent->d_name[0] == '.')
        continue; // ignore hidden dirs
      if (Package::is_package(child_path))
      {
        // Filter out duplicates; first encountered takes precedence
        Package* newp = new Package(child_path);
        // TODO: make this check more efficient
        bool dup = false;
        for(std::vector<Package *>::const_iterator it = Package::pkgs.begin();
            it != Package::pkgs.end();
            it++)
        {
          if((*it)->name == newp->name)
          {
            dup=true;
            break;
          }
        }
        if(dup)
          delete newp;
        else
          Package::pkgs.push_back(newp);
      }
      //check to make sure we're allowed to descend
      else if (!Package::is_no_subdirs(child_path)) 
        q.push_front(CrawlQueueEntry(child_path));
    }
    closedir(d);
  }
  crawled = true; // don't try to re-crawl if we can't find something
  const double crawl_elapsed_time = time_since_epoch() - crawl_start_time;
  // write the results of this crawl to the cache file
  string cache_path(getCachePath());
  char tmp_cache_dir[PATH_MAX];
  char tmp_cache_path[PATH_MAX];
  strncpy(tmp_cache_dir, cache_path.c_str(), sizeof(tmp_cache_dir));
  snprintf(tmp_cache_path, sizeof(tmp_cache_path), "%s/.rospack_cache.XXXXXX", dirname(tmp_cache_dir));
  int fd = mkstemp(tmp_cache_path);
  if (fd < 0)
  {
    fprintf(stderr, "Unable to create temporary cache file: %s\n", tmp_cache_path);
    throw runtime_error(string("failed to create tmp cache file"));
  }
  FILE *cache = fdopen(fd, "w");
  if (!cache)
  {
    fprintf(stderr, "woah! couldn't create the cache file. Please check "
            "ROS_ROOT to make sure it's a writeable directory.\n");
    throw runtime_error(string("failed to create tmp cache file"));
  }
  char *rpp = getenv("ROS_PACKAGE_PATH");
  fprintf(cache, "#ROS_ROOT=%s\n#ROS_PACKAGE_PATH=%s\n", ros_root,
          (rpp ? rpp : ""));
  for (VecPkg::iterator pkg = Package::pkgs.begin();
       pkg != Package::pkgs.end(); ++pkg)
    fprintf(cache, "%s\n", (*pkg)->path.c_str());
  if(rename(tmp_cache_path, cache_path.c_str()) < 0)
  {
    fprintf(stderr, "[rospack] Error: failed rename cache file %s to %s\n", tmp_cache_path, cache_path.c_str());
perror("rename");
    throw runtime_error(string("failed to rename cache file"));
  }
  fclose(cache);

  if (g_profile_length)
  {
    // dump it into a stack to reverse it (so slowest guys are first)
    stack<CrawlQueueEntry> reverse_profile;
    while (!profile.empty())
    {
      reverse_profile.push(profile.top());
      profile.pop();
    }
    if(!g_profile_zombie_only)
    {
      printf("\nFull tree crawl took %.6f seconds.\n", crawl_elapsed_time);
      printf("Directories marked with (*) contain no manifest.  You may\n");
      printf("want to delete these directories.\n");
      printf("-------------------------------------------------------------\n");
    }
    while (!reverse_profile.empty())
    {
      CrawlQueueEntry cqe = reverse_profile.top();
      reverse_profile.pop();
      if(!g_profile_zombie_only)
        printf("%.6f %s %s\n", 
               cqe.elapsed_time, 
               cqe.has_manifest ? " " : "*",
               cqe.path.c_str());
      else
        printf("%s\n", cqe.path.c_str());
    }
    if(!g_profile_zombie_only)
      printf("\n");
  }
}

VecPkg ROSPack::partial_crawl(const string &path)
{
  deque<CrawlQueueEntry> q;
  q.push_back(CrawlQueueEntry(path));
  VecPkg partial_pkgs;
  while (!q.empty())
  {
    CrawlQueueEntry cqe = q.front();
    //printf("crawling %s\n", cqe.path.c_str());
    q.pop_front();
    DIR *d = opendir(cqe.path.c_str());
    if (!d)
    {
      fprintf(stderr, "[rospack] opendir error [%s] while crawling %s\n", 
              strerror(errno), cqe.path.c_str());
      continue;
    }
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL)
    {
      struct stat s;
      string child_path = cqe.path + fs_delim + string(ent->d_name);
      if (stat(child_path.c_str(), &s) != 0) 
        continue;
      if (!S_ISDIR(s.st_mode)) 
        continue;
      if (ent->d_name[0] == '.')
        continue; // ignore hidden dirs
      if (Package::is_package(child_path))
      {
        // Filter out duplicates; first encountered takes precedence
        Package* newp = new Package(child_path);
        // TODO: make this check more efficient
        bool dup = false;
        for(std::vector<Package *>::const_iterator it = partial_pkgs.begin();
            it != partial_pkgs.end();
            it++)
        {
          if((*it)->name == newp->name)
          {
            dup=true;
            break;
          }
        }
        if(dup)
          delete newp;
        else
          partial_pkgs.push_back(newp);
      }
      //check to make sure we're allowed to descend
      else if (!Package::is_no_subdirs(child_path)) 
        q.push_front(CrawlQueueEntry(child_path));
    }
    closedir(d);
  }
  return partial_pkgs; 
}

//////////////////////////////////////////////////////////////////////////////

void string_split(const string &s, vector<string> &t, const string &d)
{
  t.clear();
  size_t start = 0, end;
  while ((end = s.find_first_of(d, start)) != string::npos)
  {
    t.push_back(s.substr(start, end-start));
    start = end + 1;
  }
  t.push_back(s.substr(start));
}

// Produce a new string by keeping only the first of each repeated token in
// the input string, where tokens are space-separated.  I'm sure that Rob
// could point me at the Boost/STL one-liner that does the same thing.
string deduplicate_tokens(const string& s)
{
  vector<string> in;
  vector<string> out;
  string_split(s, in, " ");
  for(int i=0; i<in.size(); i++)
  {
    bool dup = false;
    for(int j=0; j<out.size(); j++)
    {
      if(!out[j].compare(in[i]))
      {
        dup = true;
        break;
      }
    }
    if(!dup)
      out.push_back(in[i]);
  }

  string res;
  for(int j=0; j<out.size(); j++)
  {
    if(!j)
      res += out[j];
    else
      res += string(" ") + out[j];
  }

  return res;
}

bool file_exists(const string &fname)
{
  // this will be different in windows
  return (access(fname.c_str(), F_OK) == 0);
}

Package *g_get_pkg(const string &name)
{
  // a hack... but I'm lazy and love single-file programs
  return g_rospack->get_pkg(name);
}

void ROSPack::sanitize_rppvec(std::vector<std::string> &rppvec)
{
  // drop any trailing slashes
  for (size_t i = 0; i < rppvec.size(); i++)
  {
    size_t last_slash_pos = rppvec[i].find_last_of("/");
    if (last_slash_pos != string::npos &&
        last_slash_pos == rppvec[i].length()-1)
    {
      fprintf(stderr, "[rospack] warning: trailing slash found in "
                      "ROS_PACKAGE_PATH\n");
      rppvec[i].erase(last_slash_pos);
    }
  }
}

}
