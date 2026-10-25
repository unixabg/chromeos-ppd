#pragma once
#include <utility>
#include <initializer_list>
namespace base { template<class T> class NoDestructor { public:
 template<class U> NoDestructor(std::initializer_list<U> l){ p=new T(l.begin(), l.end());} 
 template<class... A> explicit NoDestructor(A&&... a){ p=new T(std::forward<A>(a)...);} 
 T& operator*() const {return *p;} T* operator->() const {return p;} private: T* p; }; }
