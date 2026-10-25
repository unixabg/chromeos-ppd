#pragma once
#include <cassert>
#include <iostream>
struct NullStream { template<class T> NullStream& operator<<(const T&){return *this;} };
#define DCHECK(c) (c) ? (void)0 : (void)(std::cerr<<"DCHECK failed: " #c "\n")
#define CHECK(c) DCHECK(c)
#define NOTREACHED() NullStream()
