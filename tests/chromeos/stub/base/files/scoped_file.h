#pragma once
#include <unistd.h>
namespace base { class ScopedFD { public: ScopedFD() = default; explicit ScopedFD(int f):fd_(f){}
 ScopedFD(ScopedFD&& o):fd_(o.fd_){o.fd_=-1;} ScopedFD& operator=(ScopedFD&& o){reset(); fd_=o.fd_; o.fd_=-1; return *this;}
 ~ScopedFD(){reset();} int get() const {return fd_;} bool is_valid() const {return fd_>=0;}
 void reset(){ if(fd_>=0) close(fd_); fd_=-1;} private: int fd_=-1; }; }
