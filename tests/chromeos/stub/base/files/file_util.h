#pragma once
#include <cstdio>
#include <cstdlib>
#include <string>
#include <unistd.h>
#include "base/files/scoped_file.h"
namespace base {
class FilePath { public: FilePath() = default; explicit FilePath(const std::string& s):p_(s){} const std::string& value() const {return p_;} private: std::string p_; };
inline bool GetTempDir(FilePath* p){ const char* t=getenv("TMPDIR"); *p=FilePath(t?t:"/tmp"); return true; }
inline bool ReadStreamToStringWithMaxSize(FILE* f, size_t max, std::string* out){ out->clear(); rewind(f); int c; while((c=fgetc(f))!=EOF){ if(out->size()>=max) return false; out->push_back((char)c);} return true; }
inline bool DeleteFile(const FilePath& p){ return unlink(p.value().c_str())==0; }
}
inline base::ScopedFD CreateAndOpenFdForTemporaryFileInDir(const base::FilePath& dir, const std::string&, base::FilePath* out){
  std::string t = dir.value() + "/fsXXXXXX"; std::vector<char> b(t.begin(), t.end()); b.push_back(0);
  int fd = mkstemp(b.data()); *out = base::FilePath(b.data()); return base::ScopedFD(fd); }
using base::DeleteFile;
#include <vector>
