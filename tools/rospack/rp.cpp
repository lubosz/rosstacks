/*
 * Copyright (C) 2008, Willow Garage, Inc., Morgan Quigley
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

#include "rp.h"
#include "tinyxml-2.5.3/tinyxml.h"

#include <boost/filesystem.hpp>
#include <boost/algorithm/string.hpp>

#if defined(WIN32)
  #include <direct.h>
  #define getcwd _getcwd
#else //!defined(WIN32)
  #include <sys/types.h>
  #include <libgen.h>
  #include <limits.h>
  #include <pwd.h>
  #include <unistd.h>
  #include <sys/time.h>
#endif

#include <sys/stat.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>
#include <errno.h>

// TODO:
//   recrawl on:
//     package not found in cache
//     package found in cache, but no manifest.xml present in filesystem

namespace fs = boost::filesystem;

namespace rospack
{

static const char* ROSPACK_MANIFEST_NAME = "manifest.xml";
static const char* ROSSTACK_MANIFEST_NAME = "stack.xml";
static const char* ROSPACK_CACHE_NAME = "rospack_cache";
static const char* ROSSTACK_CACHE_NAME = "rosstack_cache";
static const char* ROSPACK_NOSUBDIRS = "rospack_nosubdirs";
static const char* DOTROS_NAME = ".ros";
static const char* MSG_GEN_GENERATED_DIR = "msg_gen";
static const char* MSG_GEN_GENERATED_FILE = "generated";
static const char* SRV_GEN_GENERATED_DIR = "srv_gen";
static const char* SRV_GEN_GENERATED_FILE = "generated";
static const char* MANIFEST_TAG_PACKAGE = "package";
static const char* MANIFEST_TAG_ROSDEP = "rosdep";
static const char* MANIFEST_TAG_VERSIONCONTROL = "versioncontrol";
static const char* MANIFEST_TAG_EXPORT = "export";
static const char* MANIFEST_ATTR_NAME = "name";
static const char* MANIFEST_ATTR_TYPE = "type";
static const char* MANIFEST_ATTR_URL = "url";
static const char* MANIFEST_PREFIX = "${prefix}";
static const int MAX_CRAWL_DEPTH = 1000;
static const int MAX_DEPENDENCY_DEPTH = 1000;
static const double DEFAULT_MAX_CACHE_AGE = 60.0;

// Allow ourselves one global, to avoid having to tie the log_* methods
// into the Rosstackage class.
static bool QUIET = false;

rospack_tinyxml::TiXmlElement* get_manifest_root(Stackage* stackage);
double time_since_epoch();

class Exception : public std::runtime_error
{
  public:
    Exception(const std::string& what)
            : std::runtime_error(what)
    {}
};

class Stackage
{
  public:
    // \brief name of the stackage
    std::string name_;
    // \brief absolute path to the stackage
    std::string path_;
    // \brief absolute path to the stackage manifest
    std::string manifest_path_;
    // \brief have we already loaded the manifest?
    bool manifest_loaded_;
    // \brief TinyXML structure, filled in during parsing
    rospack_tinyxml::TiXmlDocument manifest_;
    std::vector<Stackage*> deps_;
    bool deps_computed_;

    Stackage(const std::string& name,
             const std::string& path,
             const std::string& manifest_path) :
            name_(name),
            path_(path),
            manifest_path_(manifest_path),
            manifest_loaded_(false),
            deps_computed_(false)
  {
  }

};

class DirectoryCrawlRecord
{
  public:
    std::string path_;
    bool zombie_;
    double start_time_;
    double crawl_time_;
    size_t start_num_pkgs_;
    DirectoryCrawlRecord(std::string path, 
                         double start_time, 
                         size_t start_num_pkgs) :
            path_(path),
            zombie_(false),
            start_time_(start_time),
            crawl_time_(0.0),
            start_num_pkgs_(start_num_pkgs) {}
};
bool cmpDirectoryCrawlRecord(DirectoryCrawlRecord* i,
                             DirectoryCrawlRecord* j)
{
  return (i->crawl_time_ < j->crawl_time_);
}

/////////////////////////////////////////////////////////////
// Rosstackage methods (public/protected)
/////////////////////////////////////////////////////////////
Rosstackage::Rosstackage(std::string manifest_name,
                         std::string cache_name,
                         crawl_direction_t crawl_dir,
                         bool quiet):
        manifest_name_(manifest_name),
        cache_name_(cache_name),
        crawl_dir_(crawl_dir),
        crawled_(false)
{
  QUIET = quiet;
}

bool
Rosstackage::isStackage(const std::string& path)
{
  if(!fs::is_directory(path))
    return false;

  for(fs::directory_iterator dit = fs::directory_iterator(path);
      dit != fs::directory_iterator();
      ++dit)
  {
    if(!fs::is_regular_file(dit->path()))
      continue;
    
    if(dit->path().filename() == manifest_name_)
      return true;
  }
  return false;
}

void
Rosstackage::crawl(const std::vector<std::string>& search_path,
                   bool force)
{
  if(crawled_)
    return;
  if(!force)
  {
    if(readCache())
       return;
  }

  std::vector<DirectoryCrawlRecord*> dummy;
  std::tr1::unordered_set<std::string> dummy2;
  for(std::vector<std::string>::const_iterator p = search_path.begin();
      p != search_path.end();
      ++p)
  {
    crawlDetail(*p, force, 1, false, dummy, dummy2);
  }
  
  crawled_ = true;

  writeCache();
}

bool 
Rosstackage::inStackage(std::string& name)
{
  char path[PATH_MAX];
  if(getcwd(path,sizeof(path)))
  {
    if(Rosstackage::isStackage(path))
    {
#if !defined(BOOST_FILESYSTEM_VERSION) || (BOOST_FILESYSTEM_VERSION == 2)
      name = fs::path(path).filename();
#else
      // in boostfs3, filename() returns a path, which needs to be stringified
      name = fs::path(path).filename().string();
#endif
      return true;
    }
  }
  return false;
}


bool
Rosstackage::find(const std::string& name, std::string& path)
{
  std::tr1::unordered_map<std::string, Stackage*>::const_iterator it = stackages_.find(name);
  if(it != stackages_.end())
  {
    path = it->second->path_;
    return true;
  }
  else
  {
    log_error("librospack", std::string("package ") + name + " not found");
    return false;
  }
}

void 
Rosstackage::list(std::vector<std::pair<std::string, std::string> >& list)
{
  list.resize(stackages_.size());
  int i = 0;
  for(std::tr1::unordered_map<std::string, Stackage*>::const_iterator it = stackages_.begin();
      it != stackages_.end();
      ++it)
  {
    list[i].first = it->first;
    list[i].second = it->second->path_;
    i++;
  }
}

void 
Rosstackage::listDuplicates(std::vector<std::string>& dups)
{
  dups.resize(dups_.size());
  int i = 0;
  for(std::tr1::unordered_set<std::string>::const_iterator it = dups_.begin();
      it != dups_.end();
      ++it)
  {
    dups[i] = (*it);
    i++;
  }
}

bool
Rosstackage::deps(const std::string& name, bool direct,
                  std::vector<std::string>& deps)
{
  std::vector<Stackage*> stackages;
  if(!depsDetail(name, direct, stackages))
    return false;
  for(std::vector<Stackage*>::const_iterator it = stackages.begin();
      it != stackages.end();
      ++it)
    deps.push_back((*it)->name_);
  return true;
}

bool
Rosstackage::dependsOn(const std::string& name, bool direct,
                       std::vector<std::string>& deps)
{
  std::vector<Stackage*> stackages;
  if(!dependsOnDetail(name, direct, stackages))
    return false;
  for(std::vector<Stackage*>::const_iterator it = stackages.begin();
      it != stackages.end();
      ++it)
    deps.push_back((*it)->name_);
  return true;
}

bool
Rosstackage::depsIndent(const std::string& name, bool direct,
                        std::vector<std::string>& deps)
{
  if(!stackages_.count(name))
  {
    log_error("librospack", std::string("no such package ") + name);
    return false;
  }
  Stackage* stackage = stackages_[name];
  try
  {
    computeDeps(stackage);
    std::vector<Stackage*> deps_vec;
    std::tr1::unordered_set<Stackage*> deps_hash;
    std::vector<std::string> indented_deps;
    gatherDepsFull(stackage, direct, POSTORDER, 0, deps_hash, deps_vec, true, indented_deps);
    for(std::vector<std::string>::const_iterator it = indented_deps.begin();
        it != indented_deps.end();
        ++it)
      deps.push_back(*it);
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

bool
Rosstackage::depsManifests(const std::string& name, bool direct, 
                           std::vector<std::string>& manifests)
{
  if(!stackages_.count(name))
  {
    log_error("librospack", std::string("no such package ") + name);
    return false;
  }
  Stackage* stackage = stackages_[name];
  try
  {
    computeDeps(stackage);
    std::vector<Stackage*> deps_vec;
    gatherDeps(stackage, direct, POSTORDER, deps_vec);
    for(std::vector<Stackage*>::const_iterator it = deps_vec.begin();
        it != deps_vec.end();
        ++it)
      manifests.push_back((*it)->manifest_path_);
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

bool
Rosstackage::rosdeps(const std::string& name, bool direct, 
                     std::vector<std::string>& rosdeps)
{
  if(!stackages_.count(name))
  {
    log_error("librospack", std::string("no such package ") + name);
    return false;
  }
  Stackage* stackage = stackages_[name];
  try
  {
    computeDeps(stackage);
    std::vector<Stackage*> deps_vec;
    // rosdeps include the current package
    deps_vec.push_back(stackage);
    if(!direct)
      gatherDeps(stackage, direct, POSTORDER, deps_vec);
    for(std::vector<Stackage*>::const_iterator it = deps_vec.begin();
        it != deps_vec.end();
        ++it)
    {
      rospack_tinyxml::TiXmlElement* root = get_manifest_root(*it);
      for(rospack_tinyxml::TiXmlElement* ele = root->FirstChildElement(MANIFEST_TAG_ROSDEP);
          ele;
          ele = ele->NextSiblingElement(MANIFEST_TAG_ROSDEP))
      {
        const char *att_str;
        if((att_str = ele->Attribute(MANIFEST_ATTR_NAME)))
        {
          rosdeps.push_back(std::string("name: ") + att_str);
        }
      }
    }
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

bool
Rosstackage::vcs(const std::string& name, bool direct, 
                 std::vector<std::string>& vcs)
{
  if(!stackages_.count(name))
  {
    log_error("librospack", std::string("no such package ") + name);
    return false;
  }
  Stackage* stackage = stackages_[name];
  try
  {
    computeDeps(stackage);
    std::vector<Stackage*> deps_vec;
    // vcs include the current package
    deps_vec.push_back(stackage);
    if(!direct)
      gatherDeps(stackage, direct, POSTORDER, deps_vec);
    for(std::vector<Stackage*>::const_iterator it = deps_vec.begin();
        it != deps_vec.end();
        ++it)
    {
      rospack_tinyxml::TiXmlElement* root = get_manifest_root(*it);
      for(rospack_tinyxml::TiXmlElement* ele = root->FirstChildElement(MANIFEST_TAG_VERSIONCONTROL);
          ele;
          ele = ele->NextSiblingElement(MANIFEST_TAG_VERSIONCONTROL))
      {
        std::string result;
        const char *att_str;
        if((att_str = ele->Attribute(MANIFEST_ATTR_TYPE)))
        {
          result.append("type: ");
          result.append(att_str);
        }
        if((att_str = ele->Attribute(MANIFEST_ATTR_URL)))
        {
          result.append("\turl: ");
          result.append(att_str);
        }
        vcs.push_back(result);
      }
    }
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

bool 
Rosstackage::exports(const std::string& name, const std::string& lang,
                     const std::string& attrib, bool deps_only,
                     std::vector<std::string>& flags)
{
  if(!stackages_.count(name))
  {
    log_error("librospack", std::string("no such package ") + name);
    return false;
  }
  Stackage* stackage = stackages_[name];
  try
  {
    computeDeps(stackage);
    std::vector<Stackage*> deps_vec;
    if(!deps_only)
      deps_vec.push_back(stackage);
    gatherDeps(stackage, false, PREORDER, deps_vec);
    for(std::vector<Stackage*>::const_iterator it = deps_vec.begin();
        it != deps_vec.end();
        ++it)
    {
      rospack_tinyxml::TiXmlElement* root = get_manifest_root(*it);
      for(rospack_tinyxml::TiXmlElement* ele = root->FirstChildElement(MANIFEST_TAG_EXPORT);
          ele;
          ele = ele->NextSiblingElement(MANIFEST_TAG_EXPORT))
      {
        for(rospack_tinyxml::TiXmlElement* ele2 = ele->FirstChildElement(lang);
            ele2;
            ele2 = ele2->NextSiblingElement(lang))
        {
          const char *att_str;
          if((att_str = ele2->Attribute(attrib.c_str())))
          {
            std::string expanded_str;
            if(!expandExportString(*it, att_str, expanded_str))
              return false;
            flags.push_back(expanded_str);
          }
        }
      }

      // We automatically point to msg_gen and msg_srv directories if
      // certain files are present
      fs::path msg_gen = fs::path((*it)->path_) / MSG_GEN_GENERATED_DIR;
      fs::path srv_gen = fs::path((*it)->path_) / SRV_GEN_GENERATED_DIR;
      if(fs::is_regular_file(msg_gen / MSG_GEN_GENERATED_FILE))
      {
        msg_gen /= fs::path("cpp") / "include";
        flags.push_back(std::string("-I" + msg_gen.string()));
      }
      if(fs::is_regular_file(srv_gen / SRV_GEN_GENERATED_FILE))
      {
        srv_gen /= fs::path("cpp") / "include";
        flags.push_back(std::string("-I" + srv_gen.string()));
      }
    }
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

bool 
Rosstackage::plugins(const std::string& name, const std::string& attrib, 
                     const std::string& top,
                     std::vector<std::string>& flags)
{
  // Find everybody who depends directly on the package in question
  std::vector<Stackage*> stackages;
  if(!dependsOnDetail(name, true, stackages))
    return false;
  // If top was given, filter to include only those package on which top
  // depends.
  if(top.size())
  {
    std::vector<Stackage*> top_deps;
    if(!depsDetail(top, false, top_deps))
      return false;
    std::tr1::unordered_set<Stackage*> top_deps_set;
    for(std::vector<Stackage*>::iterator it = top_deps.begin();
        it != top_deps.end();
        ++it)
      top_deps_set.insert(*it);
    std::vector<Stackage*>::iterator it = stackages.begin();
    while(it != stackages.end())
    {
      if((*it)->name_ != top &&
         (top_deps_set.find(*it) == top_deps_set.end()))
        it = stackages.erase(it);
      else
        ++it;
    }
  }
  // Now go looking for the manifest data
  for(std::vector<Stackage*>::const_iterator it = stackages.begin();
      it != stackages.end();
      ++it)
  {
    rospack_tinyxml::TiXmlElement* root = get_manifest_root(*it);
    for(rospack_tinyxml::TiXmlElement* ele = root->FirstChildElement(MANIFEST_TAG_EXPORT);
        ele;
        ele = ele->NextSiblingElement(MANIFEST_TAG_EXPORT))
    {
      for(rospack_tinyxml::TiXmlElement* ele2 = ele->FirstChildElement(name);
          ele2;
          ele2 = ele2->NextSiblingElement(name))
      {
        const char *att_str;
        if((att_str = ele2->Attribute(attrib.c_str())))
        {
          std::string expanded_str;
          if(!expandExportString(*it, att_str, expanded_str))
            return false;
          flags.push_back((*it)->name_ + " " + expanded_str);
        }
      }
    }
  }
  return true;
}

bool
Rosstackage::depsMsgSrv(const std::string& name, bool direct, 
                        std::vector<std::string>& gens)
{
  if(!stackages_.count(name))
  {
    log_error("librospack", std::string("no such package ") + name);
    return false;
  }
  Stackage* stackage = stackages_[name];
  try
  {
    computeDeps(stackage);
    std::vector<Stackage*> deps_vec;
    gatherDeps(stackage, direct, POSTORDER, deps_vec);
    for(std::vector<Stackage*>::const_iterator it = deps_vec.begin();
        it != deps_vec.end();
        ++it)
    {
      fs::path msg_gen = fs::path((*it)->path_) / 
              MSG_GEN_GENERATED_DIR / 
              MSG_GEN_GENERATED_FILE;
      fs::path srv_gen = fs::path((*it)->path_) / 
              SRV_GEN_GENERATED_DIR / 
              SRV_GEN_GENERATED_FILE;
      if(fs::is_regular_file(msg_gen))
        gens.push_back(msg_gen.string());
      if(fs::is_regular_file(srv_gen))
        gens.push_back(srv_gen.string());
    }
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

/////////////////////////////////////////////////////////////
// Rosstackage methods (private)
/////////////////////////////////////////////////////////////
bool
Rosstackage::depsDetail(const std::string& name, bool direct,
                        std::vector<Stackage*>& deps)
{
  if(!stackages_.count(name))
  {
    log_error("librospack", std::string("no such package ") + name);
    return false;
  }
  Stackage* stackage = stackages_[name];
  try
  {
    computeDeps(stackage);
    std::vector<Stackage*> deps_vec;
    gatherDeps(stackage, direct, POSTORDER, deps_vec);
    for(std::vector<Stackage*>::const_iterator it = deps_vec.begin();
        it != deps_vec.end();
        ++it)
      deps.push_back(*it);
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

bool
Rosstackage::dependsOnDetail(const std::string& name, bool direct,
                             std::vector<Stackage*>& deps)
{
  if(!stackages_.count(name))
    log_warn("librospack", std::string("no such package ") + name);
  try
  {
    for(std::tr1::unordered_map<std::string, Stackage*>::const_iterator it = stackages_.begin();
        it != stackages_.end();
        ++it)
    {
      computeDeps(it->second, true);
      std::vector<Stackage*> deps_vec;
      gatherDeps(it->second, direct, POSTORDER, deps_vec);
      for(std::vector<Stackage*>::const_iterator iit = deps_vec.begin();
          iit != deps_vec.end();
          ++iit)
      {
        if((*iit)->name_ == name)
        {
          deps.push_back(it->second);
          break;
        }
      }
    }
  }
  catch(Exception& e)
  {
    log_error("librospack", e.what());
    return false;
  }
  return true;
}

bool
Rosstackage::profile(const std::vector<std::string>& search_path,
                     bool zombie_only,
                     int length,
                     std::vector<std::string>& dirs)
{
  double start = time_since_epoch();
  std::vector<DirectoryCrawlRecord*> dcrs;
  std::tr1::unordered_set<std::string> dcrs_hash;
  for(std::vector<std::string>::const_iterator p = search_path.begin();
      p != search_path.end();
      ++p)
  {
    crawlDetail(*p, true, 1, true, dcrs, dcrs_hash);
  }
  if(!zombie_only)
  {
    double total = time_since_epoch() - start;
    char buf[16];
    snprintf(buf, sizeof(buf), "%.6f", total);
    dirs.push_back(std::string("Full tree crawl took ") + buf + " seconds.");
    dirs.push_back("Directories marked with (*) contain no manifest.  You may");
    dirs.push_back("want to delete these directories.");
    dirs.push_back("To get just of list of directories without manifests,");
    dirs.push_back("re-run the profile with --zombie-only");
    dirs.push_back("-------------------------------------------------------------");
  }
  std::sort(dcrs.begin(), dcrs.end(), cmpDirectoryCrawlRecord);
  std::reverse(dcrs.begin(), dcrs.end());
  int i=0;
  for(std::vector<DirectoryCrawlRecord*>::const_iterator it = dcrs.begin();
      it != dcrs.end();
      ++it)
  {
    if(zombie_only)
    {
      if((*it)->zombie_)
      {
        if(length < 0 || i < length)
          dirs.push_back((*it)->path_);
        i++;
      }
    }
    else
    {
      char buf[16];
      snprintf(buf, sizeof(buf), "%.6f", (*it)->crawl_time_);
      if(length < 0 || i < length)
        dirs.push_back(std::string(buf) + " " + 
                       ((*it)->zombie_ ? "* " : "  ") +
                       (*it)->path_);
      i++;
    }
    delete *it;
  }

  writeCache();
  return 0;
}

void
Rosstackage::addStackage(const std::string& path)
{
#if !defined(BOOST_FILESYSTEM_VERSION) || (BOOST_FILESYSTEM_VERSION == 2)
  std::string name = fs::path(path).filename();
#else
  // in boostfs3, filename() returns a path, which needs to be stringified
  std::string name = fs::path(path).filename().string();
#endif

  if(stackages_.find(name) != stackages_.end())
  {
    dups_.insert(name);
    return;
  }
  fs::path manifest_path = fs::path(path) / manifest_name_;
  stackages_[name] = new Stackage(name, path, manifest_path.string());
}

void
Rosstackage::crawlDetail(const std::string& path,
                         bool force,
                         int depth,
                         bool collect_profile_data,
                         std::vector<DirectoryCrawlRecord*>& profile_data,
                         std::tr1::unordered_set<std::string>& profile_hash)
{
  if(depth > MAX_CRAWL_DEPTH)
    throw Exception("maximum depth exceeded during crawl");

  if(!fs::is_directory(path))
    return;

  if(isStackage(path))
  {
    addStackage(path);
    return;
  }

  fs::path nosubdirs = fs::path(path) / ROSPACK_NOSUBDIRS;
  if(fs::is_regular_file(nosubdirs))
    return;

  DirectoryCrawlRecord* dcr = NULL;
  if(collect_profile_data)
  {
    if(profile_hash.find(path) == profile_hash.end())
    {
      dcr = new DirectoryCrawlRecord(path,
                                     time_since_epoch(),
                                     stackages_.size());
      profile_data.push_back(dcr);
      profile_hash.insert(path);
    }
  }

  if(crawl_dir_ == CRAWL_DOWN)
  {
    for(fs::directory_iterator dit = fs::directory_iterator(path);
        dit != fs::directory_iterator();
        ++dit)
    {
      if(fs::is_directory(dit->path()))
      {
#if !defined(BOOST_FILESYSTEM_VERSION) || (BOOST_FILESYSTEM_VERSION == 2)
        std::string name = dit->path().filename();
#else
        // in boostfs3, filename() returns a path, which needs to be stringified
        std::string name = dit->path().filename().string();
#endif
        // Ignore directories starting with '.'
        if(name.size() == 0 || name[0] == '.')
          continue;

        crawlDetail(dit->path().string(), force, depth+1,
                    collect_profile_data, profile_data, profile_hash);
      }
    }
  }
  else // dir == CRAWL_UP
  {
    std::string parent = boost::filesystem::path(path).parent_path().string();
    if(parent.size())
      crawlDetail(parent, force, depth+1,
                  collect_profile_data, profile_data, profile_hash);
  }

  if(collect_profile_data && dcr != NULL)
  {
    // Measure the elapsed time
    dcr->crawl_time_ = time_since_epoch() - dcr->start_time_;
    // If the number of packages didn't change while crawling, 
    // then this directory is a zombie
    if(stackages_.size() == dcr->start_num_pkgs_)
      dcr->zombie_ = true;
  }
}

void
Rosstackage::loadManifest(Stackage* stackage)
{
  if(stackage->manifest_loaded_)
    return;

  if(!stackage->manifest_.LoadFile(stackage->manifest_path_))
  {
    std::string errmsg = std::string("error parsing manifest of package ") + 
            stackage->name_ + " at " + stackage->manifest_path_;
    throw Exception(errmsg);
  }
  stackage->manifest_loaded_ = true;
}

void
Rosstackage::computeDeps(Stackage* stackage, bool ignore_errors)
{
  if(stackage->deps_computed_)
    return;

  stackage->deps_computed_ = true;

  rospack_tinyxml::TiXmlElement* root;
  try
  {
    loadManifest(stackage);
    root = get_manifest_root(stackage);
  }
  catch(Exception& e)
  {
    if(ignore_errors)
      return;
    else
      throw e;
  }
  rospack_tinyxml::TiXmlNode *dep_node = NULL;
  while((dep_node = root->IterateChildren("depend", dep_node)))
  {
    rospack_tinyxml::TiXmlElement *dep_ele = dep_node->ToElement();
    const char* dep_pkgname = dep_ele->Attribute(MANIFEST_TAG_PACKAGE);
    if(!dep_pkgname)
    {
      if(!ignore_errors)
      {
        std::string errmsg = std::string("bad depend syntax (no 'package' attribute) in manifest ") + stackage->name_ + " at " + stackage->manifest_path_;
        throw Exception(errmsg);
      }
    }
    else if(dep_pkgname == stackage->name_)
    {
      if(!ignore_errors)
      {
        std::string errmsg = std::string("package ") + stackage->name_ + " depends on itself";
        throw Exception(errmsg);
      }
    }
    else if(!stackages_.count(dep_pkgname))
    {
      if(ignore_errors)
      {
        Stackage* dep =  new Stackage(dep_pkgname, "", "");
        stackage->deps_.push_back(dep);
      }
      else
      {
        std::string errmsg = std::string("package ") + stackage->name_ + " depends on non-existent package " + dep_pkgname;
        throw Exception(errmsg);
      }
    }
    else
    {
      Stackage* dep = stackages_[dep_pkgname];
      stackage->deps_.push_back(dep);
      computeDeps(dep, ignore_errors);
    }
  }
}

void
Rosstackage::gatherDeps(Stackage* stackage, bool direct, 
                        traversal_order_t order,
                        std::vector<Stackage*>& deps)
{
  std::tr1::unordered_set<Stackage*> deps_hash;
  std::vector<std::string> indented_deps;
  gatherDepsFull(stackage, direct, order, 0, 
                 deps_hash, deps, false, indented_deps);
}

// Pre-condition: computeDeps(stackage) succeeded
void
Rosstackage::gatherDepsFull(Stackage* stackage, bool direct, 
                            traversal_order_t order, int depth, 
                            std::tr1::unordered_set<Stackage*>& deps_hash,
                            std::vector<Stackage*>& deps,
                            bool get_indented_deps,
                            std::vector<std::string>& indented_deps)
{
  if(depth > MAX_DEPENDENCY_DEPTH)
    throw Exception("maximum dependency depth exceeded (likely circular dependency)");

  for(std::vector<Stackage*>::const_iterator it = stackage->deps_.begin();
      it != stackage->deps_.end();
      ++it)
  {
    bool first = (deps_hash.find(*it) == deps_hash.end());
    if(get_indented_deps || first)
    {
      if(get_indented_deps)
      {
        std::string indented_dep;
        for(int i=0; i<depth; i++)
          indented_dep.append("  ");
        indented_dep.append((*it)->name_);
        indented_deps.push_back(indented_dep);
      }

      if(first)
      {
        deps_hash.insert(*it);
        // We maintain the vector because the original rospack guaranteed
        // ordering in dep reporting.
        if(order == PREORDER)
          deps.push_back(*it);
        if(!direct)
          gatherDepsFull(*it, direct, order, depth+1, deps_hash, deps,
                         get_indented_deps, indented_deps);
        if(order == POSTORDER)
          deps.push_back(*it);
      }
    }
  }
}

std::string
Rosstackage::getCachePath()
{
  fs::path cache_path;

  char* ros_home = getenv("ROS_HOME");
  if(ros_home)
    cache_path = ros_home;
  else
  {
    // Get the user's home directory by looking up the password entry based
    // on UID.  If that doesn't work, we fall back on examining $HOME,
    // knowing that that can cause trouble when mixed with sudo (#2884).  
#if defined(WIN32)
    char* home_drive = getenv("HOMEDRIVE");
    char* home_path = getenv("HOMEPATH");
    if(home_drive && home_path) 
      cache_path = fs::path(home_drive) / fs::path(home_path) / fs::path(DOTROS_NAME);
#else // UNIX
    char* home_path;
    struct passwd* passwd_ent;
    // Look up based on effective UID, just in case we got here by set-uid
    if((passwd_ent = getpwuid(geteuid())))
      home_path = passwd_ent->pw_dir;
    else
      home_path = getenv("HOME");
    if(home_path)
      cache_path = fs::path(home_path) / fs::path(DOTROS_NAME);
#endif
  }

  // If it doesn't exist, create the directory that will hold the cache
  if(!fs::is_directory(cache_path))
  {
    try
    {
      fs::create_directory(cache_path);
    }
    catch(fs::filesystem_error& e)
    {
      log_warn("librospack",
                   std::string("cannot create rospack cache directory ") +
                   cache_path.string() + ": " + e.what());
    }
  }
  cache_path /= cache_name_;
  return cache_path.string();
}

bool
Rosstackage::readCache()
{
  if(!validateCache())
    return false;

  std::string cache_path = getCachePath();
  FILE *cache = fopen(cache_path.c_str(), "r");
  if(cache)
  {
    char linebuf[30000];
    for(;;)
    {
      if (!fgets(linebuf, sizeof(linebuf), cache))
        break; // error in read operation
      if (linebuf[0] == '#')
        continue;
      char* newline_pos = strchr(linebuf, '\n');
      if(newline_pos)
        *newline_pos = 0;
      addStackage(linebuf);
    }
    fclose(cache);
    return true;
  }
  else
    return false;
}

// TODO: replace the contents of the method with some fancy cross-platform
// boost thing.
void
Rosstackage::writeCache()
{
  // Write the results of this crawl to the cache file.  At each step, give
  // up on error, printing a warning to stderr.
  std::string cache_path = getCachePath();
  if(!cache_path.size())
  {
    log_warn("librospack",
                 "no location available to write cache file. Try setting ROS_HOME or HOME.");
  }
  else
  {
    char tmp_cache_dir[PATH_MAX];
    char tmp_cache_path[PATH_MAX];
    strncpy(tmp_cache_dir, cache_path.c_str(), sizeof(tmp_cache_dir));
#if defined(_MSC_VER)
    // No dirname on Windows; use _splitpath_s instead
    char drive[_MAX_DRIVE], dir[_MAX_DIR], fname[_MAX_FNAME], ext[_MAX_EXT];
    _splitpath_s(tmp_cache_dir, drive, _MAX_DRIVE, dir, _MAX_DIR, fname, _MAX_FNAME,
                 ext, _MAX_EXT);
    char full_dir[_MAX_DRIVE + _MAX_DIR];
    _makepath_s(full_dir, _MAX_DRIVE + _MAX_DIR, drive, dir, NULL, NULL);
    snprintf(tmp_cache_path, sizeof(tmp_cache_path), "%s\\.rospack_cache.XXXXXX", full_dir);
#elif defined(__MINGW32__)
    char* temp_name = tempnam(dirname(tmp_cache_dir),".rospack_cache.");
    snprintf(tmp_cache_path, sizeof(tmp_cache_path), temp_name);
    delete temp_name;
#else
    snprintf(tmp_cache_path, sizeof(tmp_cache_path), "%s/.rospack_cache.XXXXXX", dirname(tmp_cache_dir));
#endif
#if defined(__MINGW32__)
    // There is no equivalent of mkstemp or _mktemp_s on mingw, so we resort to a slightly problematic
    // tempnam (above) and mktemp method. This has the miniscule chance of a race condition.
    int fd = open(tmp_cache_path, O_RDWR | O_EXCL | _O_CREAT, 0644);
    if (fd < 0)
    {
      log_warn("librospack",
                   std::string("unable to create temporary cache file ") +
                   tmp_cache_path, true);
    }
    else
    {
      FILE *cache = fdopen(fd, "w");
#elif defined(WIN32)
    if (_mktemp_s(tmp_cache_path, PATH_MAX) != 0)
    {
      fprintf(stderr,
              "[rospack] Unable to generate temporary cache file name: %u",
              GetLastError());
    }
    else
    {
      FILE *cache = fopen(tmp_cache_path, "w");
#else
    int fd = mkstemp(tmp_cache_path);
    if (fd < 0)
    {
      fprintf(stderr, "[rospack] Unable to create temporary cache file %s: %s\n", 
              tmp_cache_path, strerror(errno));
    }
    else
    {
      FILE *cache = fdopen(fd, "w");
#endif
      if (!cache)
      {
        fprintf(stderr, "[rospack] Unable open cache file %s: %s\n", 
                tmp_cache_path, strerror(errno));
      }
      else
      {
        // TODO: remove writing of ROS_ROOT
        char *rr = getenv("ROS_ROOT");
        fprintf(cache, "#ROS_ROOT=%s\n", rr);

        char *rpp = getenv("ROS_PACKAGE_PATH");
        fprintf(cache, "#ROS_PACKAGE_PATH=%s\n", (rpp ? rpp : ""));
        for(std::tr1::unordered_map<std::string, Stackage*>::const_iterator it = stackages_.begin();
            it != stackages_.end();
            ++it)
          fprintf(cache, "%s\n", it->second->path_.c_str());
        fclose(cache);
        if(fs::exists(cache_path))
          remove(cache_path.c_str());
        if(rename(tmp_cache_path, cache_path.c_str()) < 0)
        {
          fprintf(stderr, "[rospack] Error: failed to rename cache file %s to %s: %s\n", 
                  tmp_cache_path, cache_path.c_str(), strerror(errno));
        }
      }
    }
  }
}

bool
Rosstackage::validateCache()
{
  std::string cache_path = getCachePath();
  // first see if it's new enough
  double cache_max_age = DEFAULT_MAX_CACHE_AGE;
  const char *user_cache_time_str = getenv("ROS_CACHE_TIMEOUT");
  if(user_cache_time_str)
    cache_max_age = atof(user_cache_time_str);
  if(cache_max_age == 0.0)
    return false;
  struct stat s;
  if(stat(cache_path.c_str(), &s) == 0)
  {
    double dt = difftime(time(NULL), s.st_mtime);
    // Negative cache_max_age means it's always new enough.  It's dangerous
    // for the user to set this, but rosbash uses it.
    if ((cache_max_age > 0.0) && (dt > cache_max_age))
      return false;
  }
  // try to open it 
  FILE* cache = fopen(cache_path.c_str(), "r");
  if(!cache)
    return false; // it's not readable by us. sad.

  // see if ROS_PACKAGE_PATH matches
  char linebuf[30000];
  bool ros_root_ok = false;
  bool ros_package_path_ok = false;
  // TODO: remove ROS_ROOT
  const char* ros_root = getenv("ROS_ROOT");
  const char* ros_package_path = getenv("ROS_PACKAGE_PATH");
  for(;;)
  {
    if(!fgets(linebuf, sizeof(linebuf), cache))
      break;
    linebuf[strlen(linebuf)-1] = 0; // get rid of trailing newline
    if (linebuf[0] == '#')
    {
      if (!strncmp("#ROS_ROOT=", linebuf, 10))
      {
        if (!strcmp(linebuf+10, ros_root))
          ros_root_ok = true;
      }
      else if(!strncmp("#ROS_PACKAGE_PATH=", linebuf, 18))
      {
        if(!ros_package_path)
        {
          if(!strlen(linebuf+18))
            ros_package_path_ok = true;
        }
        else if(!strcmp(linebuf+18, getenv("ROS_PACKAGE_PATH")))
          ros_package_path_ok = true;
      }
    }
    else
      break; // we're out of the header. nothing more matters to this check.
  }
  fclose(cache);
  return ros_root_ok && ros_package_path_ok;
}

bool
Rosstackage::expandExportString(Stackage* stackage,
                                const std::string& instring,
                                std::string& outstring)
{
  outstring = instring;
  for(std::string::size_type i = outstring.find(MANIFEST_PREFIX);
      i != std::string::npos;
      i = outstring.find(MANIFEST_PREFIX))
  {
    outstring.replace(i, std::string(MANIFEST_PREFIX).length(), 
                      stackage->path_);
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
  std::string cmd = std::string("ret=\"") + outstring + "\" && echo $ret";

  // Remove embedded newlines
  std::string token("\n");
  for (std::string::size_type s = cmd.find(token); 
       s != std::string::npos;
       s = cmd.find(token, s))
    cmd.replace(s,token.length(),std::string(" "));

  FILE* p;
  if(!(p = popen(cmd.c_str(), "r")))
  {
    std::string errmsg = 
            std::string("failed to execute backquote expression ") +
            cmd + " in " +
            stackage->manifest_path_;
    log_warn("librospack", errmsg, true);
    return false;
  }
  else
  {
    char buf[8192];
    memset(buf,0,sizeof(buf));
    // Read the command's output
    do
    {
      clearerr(p);
      while(fgets(buf + strlen(buf),sizeof(buf)-strlen(buf)-1,p));
    } while(ferror(p) && errno == EINTR);
    // Close the subprocess, checking exit status
    if(pclose(p) != 0)
    {
      std::string errmsg = 
              std::string("got non-zero exit status from executing backquote expression ") +
              cmd + " in " +
              stackage->manifest_path_;
      return false;
    }
    else
    {
      // Strip trailing newline, which was added by our call to echo
      buf[strlen(buf)-1] = '\0';
      // Replace the backquote expression with the new text
      outstring = buf;
    }
  }

  return true;
}

/////////////////////////////////////////////////////////////
// Rospack methods
/////////////////////////////////////////////////////////////
Rospack::Rospack(bool quiet) :
        Rosstackage(ROSPACK_MANIFEST_NAME,
                    ROSPACK_CACHE_NAME,
                    CRAWL_DOWN,
                    quiet)
{
}

Rosstackage::~Rosstackage()
{
  for(std::tr1::unordered_map<std::string, Stackage*>::const_iterator it = stackages_.begin();
      it != stackages_.end();
      ++it)
  {
    delete it->second;
  }
}

void 
Rospack::crawl(const std::vector<std::string>& search_path,
               bool force)
{
  Rosstackage::crawl(search_path, force);
}

bool
Rospack::inPackage(std::string& name)
{
  return inStackage(name);
}

/////////////////////////////////////////////////////////////
// Rosstack methods
/////////////////////////////////////////////////////////////
Rosstack::Rosstack(bool quiet) :
        Rosstackage(ROSSTACK_MANIFEST_NAME,
                    ROSSTACK_CACHE_NAME,
                    CRAWL_UP, 
                    quiet)
{
}

void Rosstack::crawl(const std::vector<std::string>& search_path,
                     bool force)
{
  Rosstackage::crawl(search_path, force);
}

bool
Rosstack::inStack(std::string& name)
{
  return inStackage(name);
}

rospack_tinyxml::TiXmlElement*
get_manifest_root(Stackage* stackage)
{
  rospack_tinyxml::TiXmlElement* ele = stackage->manifest_.RootElement();
  if(!ele)
  {
    std::string errmsg = std::string("error parsing manifest of package ") + 
            stackage->name_ + " at " + stackage->manifest_path_;
    throw Exception(errmsg);
  }
  return ele;
}

double 
time_since_epoch()
{
#if defined(WIN32)
  #if defined(_MSC_VER) || defined(_MSC_EXTENSIONS)
    #define DELTA_EPOCH_IN_MICROSECS  11644473600000000Ui64
  #else
    #define DELTA_EPOCH_IN_MICROSECS  11644473600000000ULL
  #endif
  FILETIME ft;
  unsigned __int64 tmpres = 0;

  GetSystemTimeAsFileTime(&ft);
  tmpres |= ft.dwHighDateTime;
  tmpres <<= 32;
  tmpres |= ft.dwLowDateTime;
  tmpres /= 10;
  tmpres -= DELTA_EPOCH_IN_MICROSECS;
  return static_cast<double>(tmpres) / 1e6;
#else
  struct timeval tod;
  gettimeofday(&tod, NULL);
  return tod.tv_sec + 1e-6 * tod.tv_usec;
#endif
}


bool
get_search_path_from_env(std::vector<std::string>& sp)
{
  char* rr = getenv("ROS_ROOT");
  char* rpp = getenv("ROS_PACKAGE_PATH");

  if(!rr || !fs::is_directory(rr))
  {
    // Test suite checks that we return non-zero on bad ROS_ROOT.  This'll
    // probably be removed when we get rid of ROS_ROOT.
    log_error("librospack", "bad / non-existent ROS_ROOT");
    return false;
  }
  else
  {
    sp.push_back(rr);
  }
  if(rpp)
  {
    std::vector<std::string> rpp_strings;
    boost::split(rpp_strings, rpp, 
                 boost::is_any_of(":"),
                 boost::token_compress_on);
    for(std::vector<std::string>::const_iterator it = rpp_strings.begin();
        it != rpp_strings.end();
        ++it)
    {
      sp.push_back(*it);
    }
  }
  return true;
}

// Simple console output helpers
void log(const std::string& name, 
         const std::string& level,
         const std::string& msg,
         bool append_errno)
{
  if(QUIET)
    return;
  fprintf(stderr, "[%s] %s: %s",
          name.c_str(), level.c_str(), msg.c_str());
  if(append_errno)
    fprintf(stderr, ": %s", strerror(errno));
  fprintf(stderr, "\n");
}

void log_warn(const std::string& name, 
              const std::string& msg,
              bool append_errno)
{
  log(name, "Warning", msg, append_errno);
}
void log_error(const std::string& name, 
               const std::string& msg,
               bool append_errno)
{
  log(name, "Error", msg, append_errno);
}

} // namespace rospack
